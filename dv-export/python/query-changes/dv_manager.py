import io
import logging
import os
import time
from typing import Any

import pandas as pd
from visier.api import DVExportApiClient
from visier.connector import VisierSession

from constants import *

logger = logging.getLogger(__name__)


class DVManager:
    """ Manages retrieves data versions (DV), executes DV export jobs, reads changes. """

    def __init__(self, session: VisierSession,
                 save_export_files_on_disk: bool,
                 export_files_path: str,
                 job_status_poll_interval_sec: int = 30,
                 job_timeout_sec: int = 1200):
        self.dv_client = DVExportApiClient(session, raise_on_error=True)
        self.save_export_files_on_disk = save_export_files_on_disk
        self.export_files_path = export_files_path
        self.job_status_poll_interval_sec = job_status_poll_interval_sec
        self.job_timeout_sec = job_timeout_sec

    def get_data_versions(self):
        """Get the list of data versions available for export."""
        return self.dv_client.get_data_versions_available_for_export().json()[DATA_VERSIONS]

    def get_export_data_version_times(self, export_uuid: str) -> (int, int):
        """Get the of data versions available for export."""
        export_metadata = self.dv_client.get_data_version_export_metadata(export_uuid).json()
        data_versions = self.get_data_versions()

        base_data_version = next(
            (dv for dv in data_versions if dv[DATA_VERSION] == export_metadata[BASE_DATA_VERSION_NUMBER]), None)
        data_version = next(
            (dv for dv in data_versions if dv[DATA_VERSION] == export_metadata[DATA_VERSION_NUMBER]), None)
        base_dv_time = int(base_data_version[CREATED])
        dv_time = int(data_version[CREATED])
        logger.info(f"Export data versions time period: {base_dv_time} - {dv_time}.")
        return base_dv_time, dv_time

    def execute_export_job(self, base_data_version: int, data_version: int) -> str:
        """Execute a DV export job, wait for it to complete, and return the export UUID."""
        if base_data_version is None:
            schedule_response = self.dv_client.schedule_initial_data_version_export_job(data_version).json()
        else:
            schedule_response = self.dv_client.schedule_delta_data_version_export_job(data_version,
                                                                                      base_data_version).json()
        job_id = schedule_response[JOB_UUID]
        logger.info(f"DV export job {job_id} was scheduled, base dv {base_data_version}, dv {data_version}.")

        start_time = time.time()
        while True:
            status_response = self.dv_client.get_data_version_export_job_status(job_id).json()
            logger.info(f"Job status: {status_response}")
            if status_response[COMPLETED]:
                failed = status_response[FAILED]
                if failed:
                    raise RuntimeError(f"Job failed: {status_response}.")
                export_uuid = status_response[EXPORT_UUID]
                logger.info(f"Job {job_id} complete with export_uuid {export_uuid}")
                return export_uuid
            else:
                elapsed_time = time.time() - start_time
                if elapsed_time > self.job_timeout_sec:
                    raise TimeoutError(f"Job {job_id} timed out after {self.job_timeout_sec} seconds.")
                time.sleep(self.job_status_poll_interval_sec)

    def read_property_values(self,
                             export_uuid: str,
                             analytic_object: str,
                             property_name: str) -> list[str]:
        """Read property changed values from the export files."""
        table_metadata = self._get_table_metadata(export_uuid, analytic_object)
        file_infos = table_metadata[COMMON_COLUMNS][FILES] + table_metadata[NEW_COLUMNS][FILES]
        all_values = []
        for file_info in file_infos:
            file_id = file_info[FILE_ID]
            file_name = file_info[FILENAME]
            logger.info(f"Downloading export file for {analytic_object} file_id: {file_id}, file_name: {file_name}")
            get_file_response = self.dv_client.get_export_file(export_uuid, file_id)
            if self.save_export_files_on_disk:
                dir_path = os.path.join(self.export_files_path, export_uuid)
                os.makedirs(dir_path, exist_ok=True)
                file_path = os.path.join(dir_path, file_info[FILENAME])
                with open(file_path, 'wb+') as f:
                    f.write(get_file_response.content)
                    f.flush()
                    f.seek(0)
                    df = pd.read_csv(f, usecols=[property_name])
            else:
                df = pd.read_csv(io.StringIO(get_file_response.content.decode('utf-8')),
                                 usecols=[property_name])
            all_values.extend(df[property_name])
        logger.info(f"Fetched {len(all_values)} records with property {property_name}.")
        return all_values

    def _get_table_metadata(self, export_uuid: str, table_name: str) -> dict[str, Any]:
        """Get the metadata for a table in a DV export."""
        metadata_response = self.dv_client.get_data_version_export_metadata(export_uuid).json()
        table = next((x for x in metadata_response[TABLES] if x[NAME] == table_name), None)
        if table is None:
            raise ValueError(f"Table {table_name} not found in export metadata.")
        return table

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

    def get_table_metadata(self, export_uuid: str, table_name: str) -> dict[str, Any]:
        """Get the metadata for a table in a DV export."""
        metadata_response = self.dv_client.get_data_version_export_metadata(export_uuid).json()
        table = next((x for x in metadata_response[TABLES] if x[NAME] == table_name), None)
        if table is None:
            raise ValueError(f"Table {table_name} not found in export metadata.")
        return table

    def execute_export_job(self, base_data_version: int, end_data_version: int) -> str:
        """Execute a DV export job, wait for it to complete, and return the export UUID."""
        if base_data_version is None:
            schedule_response = self.dv_client.schedule_initial_data_version_export_job(end_data_version).json()
        else:
            schedule_response = self.dv_client.schedule_delta_data_version_export_job(end_data_version,
                                                                                      base_data_version).json()
        job_id = schedule_response[JOB_UUID]
        logger.info(f"DV export job {job_id} was scheduled, base dv {base_data_version}, dv {end_data_version}.")

        start_time = time.time()
        while True:
            logger.info(f"Checking for dv export job {job_id} completion.")
            status_response = self.dv_client.get_data_version_export_job_status(job_id).json()
            if status_response[COMPLETED]:
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
                             file_infos: list[dict[str, Any]],
                             property_name: str) -> list[str]:
        """Read property changed values from the export files."""
        all_values = []
        for file_info in file_infos:
            file_id = file_info[FILE_ID]
            logger.info(f"Downloading export file with file_id: {file_id}.")
            get_file_response = self.dv_client.get_export_file(export_uuid, file_id)
            if self.save_export_files_on_disk:
                dir_path = os.path.join(self.export_files_path, export_uuid)
                os.makedirs(dir_path, exist_ok=True)
                file_path = os.path.join(dir_path, file_info[FILE_NAME])
                with open(file_path, 'wb+') as f:  # 'wb+' mode for both writing and reading
                    f.write(get_file_response.content)
                    f.flush()
                    f.seek(0)  # reset file pointer to the beginning
                    df = pd.read_csv(f, usecols=[property_name])
            else:
                df = pd.read_csv(io.StringIO(get_file_response.content.decode('utf-8')),
                                 usecols=[property_name])
            all_values.extend(df[property_name])
        logger.info(f"Fetched {len(all_values)} records with property {property_name}.")
        return all_values

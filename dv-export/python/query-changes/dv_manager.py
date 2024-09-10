import io
import logging
import os
import time
from typing import Tuple

import pandas as pd
from visier_api_data_out import DataVersionExportApi, DataVersionExportDataVersionsDTO, \
    DataVersionExportScheduleJobRequestDTO, DataVersionExportTableDTO, DataVersionExportDTO

logger = logging.getLogger(__name__)


class DVManager:
    """ Retrieves DVs, executes DV export jobs, and reads changes. """

    def __init__(self,
                 dv_api: DataVersionExportApi,
                 save_export_files_on_disk: bool,
                 export_files_path: str,
                 job_status_poll_interval_sec: int = 30,
                 job_timeout_sec: int = 1200):
        self.dv_api = dv_api
        self.save_export_files_on_disk = save_export_files_on_disk
        self.export_files_path = export_files_path
        self.job_status_poll_interval_sec = job_status_poll_interval_sec
        self.job_timeout_sec = job_timeout_sec

    def get_data_versions(self) -> DataVersionExportDataVersionsDTO:
        """Retrieve a list of DVs available to export."""

        return self.dv_api.get_available_data_versions()

    def get_export_data_version_times(self, export_uuid: str) -> Tuple[int, int]:
        """Retrieve a list of the data versions available to export."""

        export_metadata = self.dv_api.get_export(export_uuid)
        base_dv_meta = export_metadata.data_version_exports[0].base_data_version_number
        dv_meta = export_metadata.data_version_exports[0].data_version_number
        dv_dto = self.get_data_versions()

        base_data_version = None
        data_version = None
        for dv in dv_dto.data_versions:
            if dv.data_version == base_dv_meta:
                base_data_version = dv
            if dv.data_version == dv_meta:
                data_version = dv
            if base_data_version and data_version:
                break

        base_dv_time = int(base_data_version.created)
        dv_time = int(data_version.created)
        logger.info(f"Export data versions time period: {base_dv_time} - {dv_time}.")
        return base_dv_time, dv_time

    def execute_export_job(self, base_data_version: int, data_version: int) -> str:
        """Run a DV export job, wait for it to complete, and then return the export UUID."""

        schedule_request = DataVersionExportScheduleJobRequestDTO(
            data_version_number=str(data_version),
            base_data_version_number=str(base_data_version)
        )
        schedule_response = self.dv_api.schedule_export_job(schedule_request)
        job_uuid = schedule_response.job_uuid
        logger.info(f"Scheduled DV export job {job_uuid} for base DV {base_data_version} and DV {data_version}.")

        start_time = time.time()
        while True:
            status_response = self.dv_api.get_export_job_status(job_uuid)
            logger.info(f"Job status: {status_response}")
            if status_response.completed:
                if status_response.failed:
                    raise RuntimeError(f"Job failed: {status_response.model_dump()}.")
                logger.info(f"Job {job_uuid} complete with export UUID {status_response.export_uuid}")
                return status_response.export_uuid
            else:
                elapsed_time = time.time() - start_time
                if elapsed_time > self.job_timeout_sec:
                    raise TimeoutError(f"Job {job_uuid} timed out after {self.job_timeout_sec} seconds.")
                time.sleep(self.job_status_poll_interval_sec)

    def read_property_values(self,
                             export_uuid: str,
                             analytic_object: str,
                             property_name: str) -> list[str]:
        """Read the changed values from the export files."""
        export_table = self._get_table_metadata(export_uuid, analytic_object)
        export_files = export_table.common_columns.files + export_table.new_columns.files
        all_values: list[str] = []
        for export_file in export_files:
            file_id = export_file.file_id
            file_name = export_file.filename
            logger.info(f"Downloading export file for {analytic_object} file_id: {file_id}, file_name: {file_name}")
            file_content = self.dv_api.call_1_alpha_download_file(export_uuid, file_id)
            if self.save_export_files_on_disk:
                dir_path = os.path.join(self.export_files_path, export_uuid)
                os.makedirs(dir_path, exist_ok=True)
                file_path = os.path.join(dir_path, file_name)
                with open(file_path, 'wb+') as f:
                    f.write(file_content)
                    f.flush()
                    f.seek(0)
                    df = pd.read_csv(f, usecols=[property_name])
            else:
                df = pd.read_csv(io.StringIO(file_content.decode('utf-8')),
                                 usecols=[property_name])
            all_values.extend(df[property_name])
        logger.info(f"Fetched {len(all_values)} records with property {property_name}.")
        return all_values

    def _get_table_metadata(self, export_uuid: str, table_name: str) -> DataVersionExportTableDTO:
        """Retrieve information about a table in a DV export."""

        # TODO replace with get_export() when the API is fixed
        response = self.dv_api.get_export_without_preload_content(export_uuid)
        if response.status != 200:
            raise Exception(f"Failed to get export {export_uuid}: {response}.")

        dv_export_dto = DataVersionExportDTO.from_json(response.data.decode('utf-8'))
        tables = dv_export_dto.tables
        table = next((t for t in tables if t.name == table_name), None)
        if table is None:
            raise Exception(f"Table {table_name} not found in export.")
        return table

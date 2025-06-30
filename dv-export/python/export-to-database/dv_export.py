import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from visier_platform_sdk import ApiClient, DataVersionExportApi, DataVersionExportScheduleJobRequestDTO, \
    DataVersionExportDTO, ApiException

from constants import *
from data_store import DataStore
from dv_export_model import FileInfo, TableInfo, ColumnInfoAndFileInfo, convert_table_metadata_into_table_infos

logger = logging.getLogger('dv_export')


@dataclass
class DataVersions:
    data_version_number: int
    base_data_version_number: Optional[int]


class DVExport:
    """
    Orchestrates interactions between the ``DVExportApiClient`` and the output ``DataStore``
    """
    def __init__(self, client: ApiClient, data_store: DataStore, base_download_dir: str):
        self.client = DataVersionExportApi(client)
        self.data_store = data_store
        self.base_download_dir = base_download_dir

    def generate_data_version_export(self,
                                     dv_export_schedule_job_request_dto: DataVersionExportScheduleJobRequestDTO,
                                     mx_num_polls: int,
                                     poll_interval_secs: int
                                     ) -> DataVersionExportDTO:
        job_id = self._schedule_export_job(dv_export_schedule_job_request_dto)
        export_id = self._get_export_id_when_job_finishes(job_id, mx_num_polls, poll_interval_secs)
        return self.get_export_metadata(export_id)

    def _schedule_export_job(self,
                             dv_export_schedule_job_request_dto: DataVersionExportScheduleJobRequestDTO
                             ) -> str:
        logger.info(f"Scheduling a data version export job for data_version_number={dv_export_schedule_job_request_dto.data_version_number} "
                    f"base_data_version_number={dv_export_schedule_job_request_dto.base_data_version_number}")
        try:
            response = self.client.schedule_export_job(dv_export_schedule_job_request_dto)
            job_id = response.job_uuid
            logger.info(f"Scheduled data version export job with {job_id=}")
            return job_id
        except ApiException as e:
            raise Exception(f"Failed to schedule data version export job with {dv_export_schedule_job_request_dto=}\n{e.body}", e)

    def _get_export_id_when_job_finishes(self,
                                         job_id: str,
                                         mx_num_polls: int,
                                         poll_interval_secs: int) -> str:
        export_id = None
        counter = 1
        while counter <= mx_num_polls:
            try:
                job_status = self.client.get_export_job_status(job_id)

                if job_status.failed:
                    raise Exception(f"Data version export {job_id=} failed")

                if job_status.completed:
                    export_id = job_status.export_uuid
                    logger.info(f"Export {job_id=} completed with {export_id=}")
                    break

                repeat_msg = f"Trying again in {poll_interval_secs} seconds" if counter <= mx_num_polls else ""
                logger.info(f"(Attempt {counter} out of {mx_num_polls}) {job_id=} is still running. {repeat_msg}")
                if repeat_msg:
                    time.sleep(poll_interval_secs)

            except ApiException as e:
                raise Exception(f"Failed to get export job status for {job_id=} response={repr(job_status)}\n{e.body}", e)

            finally:
                counter += 1

        if export_id is None:
            raise Exception(f"Failed to retrieve export_id after {mx_num_polls} attempts")
        return export_id

    def get_export_metadata(self, export_id: str) -> DataVersionExportDTO:
        try:
            response = self.client.get_export(export_id)
            logger.info(f"Successfully retrieved export metadata for {export_id=}")
            return response
        except ApiException as e:
            raise Exception(f"Failed to get export metadata for {export_id=}\n{e.body}", e)

    def _download_table_files_to_dir(self,
                                     export_uuid: str,
                                     tbl_name: str,
                                     file_infos: list[FileInfo],
                                     download_directory: str) -> list[str]:
        file_paths = []
        for file_info in file_infos:
            logger.info(f"Downloading file={file_info.name} with id={file_info.file_id} for table={tbl_name}")

            # There are three possible functions to call to download an individual file from the export; in this
            # case, we're using the first one, but the methods to call the others are provided as examples

            # Method 1: Returns the bytearray of the file
            r = self.client.call_1_alpha_download_file(export_uuid=export_uuid, file_id=file_info.file_id)

            # Method 2: Returns an ApiResponse with the bytearray as the data
            #r = self.client.call_1_alpha_download_file_with_http_info(export_uuid=export_uuid, file_id=file_info.file_id).data

            # Method 3: Return the response through a HTTPResponse
            #r = self.client.call_1_alpha_download_file_without_preload_content(export_uuid=export_uuid, file_id=file_info.file_id).data

            file_path = download_directory + file_info.name
            with open(file_path, 'wb') as f:
                f.write(r)
            file_paths.append(file_path)
            logger.info(f"Downloaded file={file_info.name} with id={file_info.file_id} "
                        f"for table={tbl_name} to file={file_path}")
        return file_paths

    def _create_and_populate_new_table(self,
                                       table: TableInfo,
                                       column_and_file_info: ColumnInfoAndFileInfo,
                                       download_directory: str,
                                       export_id: str):
        self.data_store.create_initial_table_definition(table)
        self._download_files_and_insert_into_table(table.name,
                                                   column_and_file_info,
                                                   download_directory,
                                                   export_id)

    def _download_files_and_insert_into_table(self,
                                              table_name: str,
                                              column_and_file_info: ColumnInfoAndFileInfo,
                                              download_directory: str,
                                              export_id: str):
        local_files_for_table = self._download_table_files_to_dir(export_id,
                                                                  table_name,
                                                                  column_and_file_info.file_infos,
                                                                  download_directory)

        self.data_store.insert_from_files_into_table(table_name,
                                                     column_and_file_info.column_infos,
                                                     local_files_for_table)

    def _create_and_populate_new_tables(self, tables: list[TableInfo], export_id: str):
        """
        Handle an initial export or adding new tables, where it is assumed all tables
        need to be created for the first time.

        :param tables: List of ``TableInfo`` to create and populate tables for
        :param export_id: UUID of the export metadata from a DV export job
        """
        itr = 1
        for table in tables:
            logger.info(f"Starting storage of table={table.name} ({itr} out of {len(tables)} tables) in data_store")
            download_directory = self.base_download_dir + export_id + "/new-columns/" + table.name + "/"
            Path(download_directory).mkdir(parents=True, exist_ok=True)
            self._create_and_populate_new_table(table,
                                                table.columns.new_columns,
                                                download_directory,
                                                export_id)
            itr += 1

    def _handle_delta_export(self,
                             tables: list[TableInfo],
                             metadata: DataVersionExportDTO,
                             export_id: str):
        """
        Handle a delta export, where there could be new, existing, and/or deleted tables to operate on.
        :param tables: List of ``TableInfo`` to create or update tables for
        :param metadata: Full DV export metadata to retrieve deleted and new tables
        :param export_id: UUID of the export metadata from a DV export job
        """
        logger.info(f"Performing delta export")

        deleted_tables = metadata.deleted_tables
        for deleted_table in deleted_tables:
            logger.info(f"Dropping table={deleted_table}")
            self.data_store.drop_table(deleted_table)

        new_tables = metadata.new_tables
        new_table_infos = [tbl_info for tbl_info in tables if tbl_info.name in new_tables]

        self._create_and_populate_new_tables(new_table_infos, export_id)

        existing_tables = [tbl_info for tbl_info in tables if tbl_info not in new_tables]
        itr = 1
        for existing_tbl in existing_tables:
            logger.info(f"Processing existing table={existing_tbl.name} "
                        f"({itr} out of {len(existing_tables)} tables)")
            new_column_and_file_info = existing_tbl.columns.new_columns
            deleted_columns = existing_tbl.columns.deleted_columns

            if len(new_column_and_file_info.column_infos) == 0 and len(deleted_columns) == 0:
                logger.info(f"There are no schema changes for table={existing_tbl.name}.")
                download_directory = self.base_download_dir + export_id + "/common-columns/" + existing_tbl.name + "/"
                Path(download_directory).mkdir(parents=True, exist_ok=True)
                self._download_files_and_insert_into_table(existing_tbl.name,
                                                           existing_tbl.columns.common_columns,
                                                           download_directory,
                                                           export_id)
            itr += 1

    def process_metadata(self,
                         metadata: DataVersionExportDTO):
        """
        Use the DV export metadata to create or update table definitions in output data store, download files for
        those tables, then insert records from those files into output data store.

        :param metadata: Full export metadata returned from a DV export job
        """
        export_id = metadata.uuid
        tables = convert_table_metadata_into_table_infos(metadata.tables)

        is_initial_export = (len(metadata.tables) if metadata.tables else 0) == (len(metadata.new_tables) if metadata.new_tables else 0)

        if is_initial_export:
            self._create_and_populate_new_tables(tables, export_id)
        else:
            self._handle_delta_export(tables, metadata, export_id)

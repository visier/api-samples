import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from visier.api import DVExportApiClient
from data_store import DataStore
from dv_export_model import FileInfo, TableInfo, ColumnInfoAndFileInfo, convert_table_metadata_into_table_infos
from constants import *

logger = logging.getLogger('dv_export')


@dataclass
class DataVersions:
    data_version_number: int
    base_data_version_number: Optional[int]


class DVExport:
    """
    Orchestrates interactions between the ``DVExportApiClient`` and the output ``DataStore``
    """
    def __init__(self, client: DVExportApiClient, data_store: DataStore, base_download_dir: str):
        self.client = client
        self.data_store = data_store
        self.base_download_dir = base_download_dir

    def generate_data_version_export(self,
                                     dv_info: DataVersions,
                                     mx_num_polls: int,
                                     poll_interval_secs: int) -> dict[str, any]:
        job_id = self._schedule_export_job(dv_info)
        export_id = self._get_export_id_when_job_finishes(job_id, mx_num_polls, poll_interval_secs)
        metadata: dict[str, any] = self.get_export_metadata(export_id)
        return metadata

    def _schedule_export_job(self, dv_info: DataVersions) -> str:
        logger.info(f"Scheduling a data version export job for data_version_number={dv_info.data_version_number} "
                    f"base_data_version_number={dv_info.base_data_version_number}")
        if dv_info.base_data_version_number is None:
            schedule_response = self.client.schedule_initial_data_version_export_job(dv_info.data_version_number)
        else:
            schedule_response = self.client.schedule_delta_data_version_export_job(dv_info.data_version_number,
                                                                                   dv_info.base_data_version_number)
        job_id: str = schedule_response.json()[JOB_UUID_KEY]
        logger.info(f'Scheduled data version export job with job_id={job_id}')
        return job_id

    def _get_export_id_when_job_finishes(self,
                                         job_id: str,
                                         mx_num_polls: int,
                                         poll_interval_secs: int) -> str:
        curr_poll = 0
        export_id = ""
        while curr_poll < mx_num_polls:
            status_response = self.client.get_data_version_export_job_status(job_id)
            if not status_response:
                raise Exception(f"Failed to get export job status for job_id={job_id} response={repr(status_response)}")

            status_response_json = status_response.json()
            if status_response_json[EXPORT_JOB_FAILED_KEY]:
                raise Exception(f"Data version export job_id={job_id} failed")

            if status_response_json[EXPORT_JOB_COMPLETED_KEY]:
                export_id = status_response_json[EXPORT_UUID_KEY]
                logger.info(f"Export job_id={job_id} completed with export_id={export_id}")
                break

            repeat_msg = f"Trying again in {poll_interval_secs} seconds" if curr_poll != mx_num_polls - 1 else ""
            logger.info(
                f"(Attempt {curr_poll + 1} out of {mx_num_polls}) job_id={job_id} is still running. {repeat_msg}")
            if curr_poll != mx_num_polls - 1:
                time.sleep(poll_interval_secs)
            curr_poll = curr_poll + 1

        if export_id == "":
            raise Exception(f"Failed to retrieve export_id after {curr_poll} polls")
        return export_id

    def get_export_metadata(self, export_id: str) -> dict[str, any]:
        metadata_response = self.client.get_data_version_export_metadata(export_id)
        if not metadata_response:
            raise Exception(f"Failed to get export metadata for export_id={export_id}")
        logger.info(f"Successfully retrieved metadata for export_id={export_id}")
        return metadata_response.json()

    def _download_table_files_to_dir(self,
                                     export_uuid: str,
                                     tbl_name: str,
                                     file_infos: list[FileInfo],
                                     download_directory: str) -> list[str]:
        file_paths = []
        for file_info in file_infos:
            logger.info(f"Downloading file={file_info.name} with id={file_info.file_id} for table={tbl_name}")
            with self.client.get_export_file(export_uuid, file_id=file_info.file_id) as r:
                r.raise_for_status()
                file_path = download_directory + file_info.name
                with open(file_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=None):
                        if chunk:
                            f.write(chunk)
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
                             metadata: dict[str, any],
                             export_id: str):
        """
        Handle a delta export, where there could be new, existing, and/or deleted tables to operate on.
        :param tables: List of ``TableInfo`` to create or update tables for
        :param metadata: Full DV export metadata to retrieve deleted and new tables
        :param export_id: UUID of the export metadata from a DV export job
        """
        logger.info(f"Performing delta export")

        deleted_tables = metadata[DELETED_TABLES_KEY]
        for deleted_table in deleted_tables:
            logger.info(f"Dropping table={deleted_table}")
            self.data_store.drop_table(deleted_table)

        new_tables = metadata[NEW_TABLES_KEY]
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
                         metadata: dict[str, any]):
        """
        Use the DV export metadata to create or update table definitions in output data store, download files for
        those tables, then insert records from those files into output data store.

        :param metadata: Full export metadata returned from a DV export job
        """
        tables = convert_table_metadata_into_table_infos(metadata[TABLES_KEY])
        export_id = metadata[UUID_KEY]

        is_initial_export = len(metadata[TABLES_KEY]) == len(metadata[NEW_TABLES_KEY])

        if is_initial_export:
            self._create_and_populate_new_tables(tables, export_id)
        else:
            self._handle_delta_export(tables, metadata, export_id)

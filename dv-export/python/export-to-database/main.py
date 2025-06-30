import argparse
import shutil
import time

from dotenv import dotenv_values
from visier_platform_sdk import ApiClient, Configuration, DataVersionExportApi, DataVersionExportScheduleJobRequestDTO, \
    DataVersionExportDTO
from visier.connector import VisierSession, make_auth
from visier.api import DVExportApiClient
from visier_platform_sdk.exceptions import ServiceException, ApiException

from data_store import *
from dv_export import DVExport, DataVersions
from constants import *

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    filename='app.log',
    filemode='w',
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
logger = logging.getLogger()
logger.addHandler(console_handler)

config_dict = {
    **dotenv_values('.env.dv-export'),
    **dotenv_values('.env.visier-auth')
}

parser = argparse.ArgumentParser(description='DV Export API example script.')
parser.add_argument('-d', '--data_version', type=int,
                    help='Data Version number the script should export.', required=False)
parser.add_argument('-b', '--base_data_version', type=int,
                    help='Base Data Version number to compute a diff from.', required=False)
parser.add_argument('-e', '--export_uuid', required=False, type=str,
                    help='Optional export UUID to retrieve export metadata for. '
                         'If provided, a DV export job will not be scheduled.')
parser.add_argument('-m', '--mode', choices=['legacy', 'sdk'], default='legacy',
                    help='Run the DV Export using the legacy methods or through the SDK.')

args = parser.parse_args()
if args.data_version is None and args.export_uuid is None:
    raise Exception(f"At least one of data_version or export_uuid must be provided")

# Set up some parameters/objects from config used in the operation
max_num_polls = int(config_dict[JOB_STATUS_NUM_POLLS])
poll_interval_seconds = int(config_dict[JOB_STATUS_POLL_INTERVAL_SECONDS])
delete_downloaded_files = True if config_dict[DELETE_BASE_DOWNLOAD_DIRECTORY_AFTER_EXPORT].upper() == 'TRUE' else False
base_download_directory = config_dict[BASE_DOWNLOAD_DIRECTORY]
#store = SQLAlchemyDataStore(config_dict[DB_URL])

if args.mode == 'legacy':


    logger.info("Running DV Export in legacy mode...")
    store = SQLAlchemyDataStore(config_dict[DB_URL])

    auth = make_auth(env_values=config_dict)
    with VisierSession(auth) as s:
        dv_export_client = DVExportApiClient(s, raise_on_error=True)
        dv_export = DVExport(dv_export_client, store, base_download_directory)

        if args.export_uuid is None:
            data_version_info = DataVersions(
                int(args.data_version),
                int(args.base_data_version) if args.base_data_version is not None else None
            )
            export_metadata = dv_export.generate_data_version_export(data_version_info,
                                                                     max_num_polls,
                                                                     poll_interval_seconds)
        else:
            export_metadata = dv_export.get_export_metadata(args.export_uuid)

        dv_export.process_metadata(export_metadata)

        if delete_downloaded_files:
            shutil.rmtree(base_download_directory)

elif args.mode == 'sdk':
    from dv_export_model import convert_table_metadata_into_table_infos, FileInfo

    logger.info("Running DV Export using the SDK...")
    config_dict[DB_URL] = 'sqlite:///j1r-export-sdk-7000001.db'
    store = SQLAlchemyDataStore(config_dict[DB_URL])

    config = Configuration.from_dict(config_dict)
    client = ApiClient(config)

    class DVExportNew(DVExport):
        """ Wrapper class that interacts with the data version export APIs through the SDK."""

        def __init__(self, client: ApiClient, data_store: DataStore, base_download_directory: str):
            self.client = DataVersionExportApi(client)
            self.data_store = data_store
            self.base_download_dir = base_download_directory

        def generate_data_version_export(self,
                                         dv_export_schedule_job_request_dto: DataVersionExportScheduleJobRequestDTO,
                                         max_num_polls: int,
                                         poll_interval_secs: int
                                         ):
            job_id = self._schedule_export_job(dv_export_schedule_job_request_dto)
            export_id = self._get_export_id_when_job_finishes(job_id, max_num_polls, poll_interval_secs)
            return self.get_export_metadata(export_id)

        def _schedule_export_job(self,
                                 dv_export_schedule_job_request_dto: DataVersionExportScheduleJobRequestDTO):
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
                                             max_num_polls: int,
                                             poll_interval_seconds: int) -> str:
            export_id = None

            counter = 1
            while counter <= max_num_polls:
                try:
                    job_status = self.client.get_export_job_status(job_id)

                    if job_status.failed:
                        raise Exception(f"Data version export {job_id=} failed")

                    if job_status.completed:
                        export_id = job_status.export_uuid
                        logger.info(f"Export {job_id=} completed with {export_id=}")
                        break

                    repeat_msg = f"Trying again in {poll_interval_seconds} seconds" if counter <= max_num_polls else ""
                    logger.info(f"(Attempt {counter} out of {max_num_polls}) {job_id=} is still running. {repeat_msg}")
                    if repeat_msg:
                        time.sleep(poll_interval_seconds)

                except ApiException as e:
                    raise Exception(f"Failed to get export job status for {job_id=} response={repr(job_status)}\n{e.body}", e)

                finally:
                    counter += 1

            if export_id is None:
                raise Exception(f"Failed to retrieve export_id after {max_num_polls} attempts")
            return export_id

        def get_export_metadata(self, export_id: str) -> DataVersionExportDTO:
            try:
                response = self.client.get_export(export_id)
                logger.info(f"Successfully retrieved export metadata for {export_id=}")
                return response
            except ApiException as e:
                raise Exception(f"Failed to get export metadata for {export_id=}\n{e.body}", e)

        def process_metadata(self, metadata: DataVersionExportDTO):
            export_id = metadata.uuid
            tables = convert_table_metadata_into_table_infos(metadata.to_dict()['tables'])

            is_initial_export = (len(metadata.tables) if metadata.tables else 0) == (len(metadata.new_tables) if metadata.new_tables else 0)

            if is_initial_export:
                self._create_and_populate_new_tables(tables, export_id)
            else:
                self._handle_delta_export(tables, metadata, export_id)

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

    dv_export = DVExportNew(client, store, base_download_directory)

    if args.export_uuid is None:

        # Schedule a new export job
        dv_export_schedule_job_request_dto = DataVersionExportScheduleJobRequestDTO(
            data_version_number=str(args.data_version),
            base_data_version_number=str(args.base_data_version) if args.base_data_version is not None else None
        )

        export_metadata = dv_export.generate_data_version_export(dv_export_schedule_job_request_dto, max_num_polls, poll_interval_seconds)

    else:
        export_metadata = dv_export.get_export_metadata(args.export_uuid)

    dv_export.process_metadata(export_metadata)

    if delete_downloaded_files:
        shutil.rmtree(base_download_directory)

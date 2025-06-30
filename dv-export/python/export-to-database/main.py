import argparse
import shutil

from dotenv import dotenv_values
from visier_platform_sdk import ApiClient, Configuration, DataVersionExportScheduleJobRequestDTO

from data_store import *
from dv_export import DVExport

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

args = parser.parse_args()
if args.data_version is None and args.export_uuid is None:
    raise Exception(f"At least one of data_version or export_uuid must be provided")

# Set up some parameters/objects from config used in the operation
max_num_polls = int(config_dict[JOB_STATUS_NUM_POLLS])
poll_interval_seconds = int(config_dict[JOB_STATUS_POLL_INTERVAL_SECONDS])
delete_downloaded_files = True if config_dict[DELETE_BASE_DOWNLOAD_DIRECTORY_AFTER_EXPORT].upper() == 'TRUE' else False
base_download_directory = config_dict[BASE_DOWNLOAD_DIRECTORY]
store = SQLAlchemyDataStore(config_dict[DB_URL])

config = Configuration.from_dict(config_dict)
client = ApiClient(config)

dv_export = DVExport(client, store, base_download_directory)

if args.export_uuid is None:

    # Schedule a new export job
    dv_export_schedule_job_request_dto = DataVersionExportScheduleJobRequestDTO(
        data_version_number=str(args.data_version),
        base_data_version_number=str(args.base_data_version) if args.base_data_version is not None else None
    )

    export_metadata = dv_export.generate_data_version_export(dv_export_schedule_job_request_dto, max_num_polls, poll_interval_seconds)
    logger.info(f"Export metadata generated with export_uuid={export_metadata.uuid}")

else:
    export_metadata = dv_export.get_export_metadata(args.export_uuid)

dv_export.process_metadata(export_metadata)

if delete_downloaded_files:
    shutil.rmtree(base_download_directory)

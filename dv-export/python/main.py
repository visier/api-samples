import argparse
import shutil

from dotenv import dotenv_values
from visier.connector import VisierSession, make_auth
from visier.api import DVExportApiClient
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

config = {
    **dotenv_values('.env.dv-export'),
    **dotenv_values('.env.visier-auth')
}

auth = make_auth(env_values=config)

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


with VisierSession(auth) as s:
    dv_export_client = DVExportApiClient(s, raise_on_error=True)

    max_num_polls = int(config[JOB_STATUS_NUM_POLLS])
    poll_interval_seconds = int(config[JOB_STATUS_POLL_INTERVAL_SECONDS])
    delete_downloaded_files = bool(config[DELETE_DOWNLOADED_FILES])
    base_download_directory = config[BASE_DOWNLOAD_DIRECTORY]

    store = SQLAlchemyDataStore(config[DB_URL])
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

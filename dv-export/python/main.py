import shutil

from dotenv import dotenv_values
from visier.connector import VisierSession, make_auth
from visier.api import DVExportApiClient
from data_store import *
from dv_export import DVExport, DataVersions

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

env_variables = dotenv_values()

auth_keys = ['VISIER_HOST', 'VISIER_USERNAME', 'VISIER_PASSWORD', 'VISIER_APIKEY', 'VISIER_CLIENT_ID', 'VISIER_VANITY']
auth_variables = {auth_key: env_variables[auth_key] for auth_key in auth_keys}
auth = make_auth(env_values=auth_variables)

dv_export_variables = {
    export_key: env_variables[export_key] for export_key in env_variables.keys() if export_key not in auth_keys
}

with VisierSession(auth) as s:
    dv_export_client = DVExportApiClient(s, raise_on_error=True)

    data_version_number_raw = dv_export_variables['DATA_VERSION_NUMBER']
    base_data_version_number_raw = dv_export_variables['BASE_DATA_VERSION_NUMBER']
    export_uuid = dv_export_variables['EXPORT_UUID']
    max_num_polls = int(dv_export_variables['JOB_STATUS_NUM_POLLS'])
    poll_interval_seconds = int(dv_export_variables['JOB_STATUS_POLL_INTERVAL_SECONDS'])
    delete_downloaded_files = bool(dv_export_variables['DELETE_DOWNLOADED_FILES'])
    base_download_directory = dv_export_variables['BASE_DOWNLOAD_DIRECTORY']

    store = SQLAlchemyDataStore(dv_export_variables['DB_URL'])
    dv_export = DVExport(dv_export_client, store)

    if export_uuid == "":
        data_version_info = DataVersions(
            int(data_version_number_raw),
            int(base_data_version_number_raw) if base_data_version_number_raw != '' else None
        )
        export_metadata = dv_export.generate_data_version_export(data_version_info,
                                                                 max_num_polls,
                                                                 poll_interval_seconds)
    else:
        export_metadata = dv_export.get_export_metadata(export_uuid)

    dv_export.process_metadata(export_metadata, store, base_download_directory)

    if delete_downloaded_files:
        shutil.rmtree(base_download_directory)

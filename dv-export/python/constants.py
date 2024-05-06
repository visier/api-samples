# Script related constants
JOB_STATUS_NUM_POLLS = 'JOB_STATUS_NUM_POLLS'
JOB_STATUS_POLL_INTERVAL_SECONDS = 'JOB_STATUS_POLL_INTERVAL_SECONDS'
DELETE_DOWNLOADED_FILES = 'DELETE_DOWNLOADED_FILES'
BASE_DOWNLOAD_DIRECTORY = 'BASE_DOWNLOAD_DIRECTORY'
DB_URL = 'DB_URL'

# Export job related constants
JOB_UUID_KEY = 'jobUuid'
EXPORT_UUID_KEY = 'exportUuid'
EXPORT_JOB_FAILED_KEY = 'failed'
EXPORT_JOB_COMPLETED_KEY = 'completed'

# Export metadata related constants
LOCATION_LEVEL_COLUMN_NAME = 'Location_LEVEL'
DIFF_ACTION_COLUMN_NAME = '_DiffAction_'
DIFF_ACTION_INSERT = '+'
UUID_KEY = 'uuid'
TABLES_KEY = 'tables'
NEW_TABLES_KEY = 'newTables'
DELETED_TABLES_KEY = 'deletedTables'
NAME_KEY = 'name'
COLUMNS_KEY = 'columns'
COMMON_COLUMNS_KEY = 'commonColumns'
NEW_COLUMNS_KEY = 'newColumns'
DELETED_COLUMNS_KEY = 'deletedColumns'
FILES_KEY = 'files'
FILE_ID_KEY = 'fileId'
FILENAME_KEY = 'filename'
DATA_TYPE_KEY = 'dataType'
ALLOWS_NULL_KEY = 'allowsNull'
IS_PRIMARY_KEY_COMPONENT_KEY = 'isPrimaryKeyComponent'

# Pandas DataFrame Dtype constants (see https://pandas.pydata.org/pandas-docs/stable/user_guide/basics.html#dtypes)
PANDAS_DF_NULLABLE_INTEGER_INT64_DTYPE = 'Int64'
PANDAS_DF_MIXED_DTYPE = 'object'
PANDAS_DF_FLOAT64_DTYPE = 'float64'
PANDAS_DF_BOOLEAN_DTYPE = 'boolean'

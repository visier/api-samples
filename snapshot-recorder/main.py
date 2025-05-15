import argparse
import logging
import os
import sys
from datetime import datetime

from dotenv import load_dotenv
from visier_api_core import Configuration, ApiClient
from visier_api_data_in import DataUploadApi
from visier_api_data_out import DataQueryApi, AggregationQueryExecutionDTO
from visier_api_analytic_model import DataModelApi


def setup_logger() -> logging.Logger:
    urllib3_logger = logging.getLogger("urllib3")
    urllib3_logger.setLevel(logging.WARNING)

    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s')

    file_handler = logging.FileHandler('app.log', mode='a')
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


logger = setup_logger()


def load_api_configuration() -> Configuration:
    logger.info("Loading API configuration.")  # Reduced message
    config = Configuration(
        host=os.getenv('VISIER_HOST'),
        api_key=os.getenv('VISIER_APIKEY'),
        username=os.getenv('VISIER_USERNAME'),
        password=os.getenv('VISIER_PASSWORD'),
        client_id=os.getenv('VISIER_CLIENT_ID'),
        client_secret=os.getenv('VISIER_CLIENT_SECRET'),
        redirect_uri=os.getenv('VISIER_REDIRECT_URI'),
        vanity=os.getenv('VISIER_VANITY'))
    return config


def parse_args() -> argparse.Namespace:
    logger.info(f"Parsing command line arguments: {sys.argv[1:]}.")  # Add arguments to log
    parser = argparse.ArgumentParser(description="Snapshot recorder sample.")
    parser.add_argument('-q', '--query_file_path', type=str, required=True,
                        help="File path to aggregate query definition.")
    parsed_args = parser.parse_args()
    return parsed_args


def ensure_temp_dir_exists(temp_dir: str) -> bool:
    """Ensures the specified temporary directory exists, creating it if necessary.

    Args:
        temp_dir: The directory to ensure exists.

    Returns:
        A boolean indicating whether the `temp_dir` was created.
    """

    temp_dir_created = False
    if not os.path.isdir(temp_dir):
        os.makedirs(temp_dir)
        temp_dir_created = True
    return temp_dir_created


def get_temp_file_path(temp_dir: str, query_file_path: str) -> str:
    """Generates a temporary file path within the specified directory.

    Args:
        temp_dir: The directory where the temporary file should be located.
        query_file_path: The path to the original query file, used for naming.

    Returns:
        The full path to the temporary file (the file itself is not created).
    """

    file_name, _ = os.path.splitext(os.path.basename(query_file_path))
    date_timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    temp_file_path = os.path.join(temp_dir, f'{file_name}_{date_timestamp}.csv')
    return temp_file_path


def download_data(config: Configuration,
                  query_file_path: str,
                  data_file_path: str) -> None:
    """
    Downloads metrics data and saves it to a file.
    Args:
        config: The API configuration object.
        query_file_path: The file path to the aggregate query definition.
        data_file_path: The file path to save the downloaded data.
    """
    with open(query_file_path) as f:
        headcount_json = f.read()
    query_dto = AggregationQueryExecutionDTO.from_json(headcount_json)

    api_client = ApiClient(config)
    query_api = DataQueryApi(api_client)

    logger.info(f"Executing query: {query_file_path}")  # Combined messages
    response = query_api.aggregate_without_preload_content(query_dto, _headers={'Accept': 'text/csv'})
    if not 200 <= response.status <= 299:
        raise Exception(f"API request failed with status code {response.status}: {response.data.decode()}")

    with open(data_file_path, mode='w') as f:
        f.write(response.data.decode())
    logger.info(f"Data saved to temp file: {data_file_path}")  # Combined messages


def upload_data(config: Configuration, data_file_path: str) -> None:
    """
    Uploads data using the Data API.
    Args:
        config: The API configuration object.
        data_file_path: The file path to the data to be uploaded.
    """
    api_client = ApiClient(config, 'Content-Type', 'application/octet-stream')
    upload_api = DataUploadApi(api_client)

    with open(data_file_path, 'rb') as f:
        data = f.read()

    filename = os.path.basename(data_file_path)
    logger.info(f"Uploading data: {data_file_path}")
    upload_api.v1_data_upload_files_filename_put(filename=filename, body=data)


def clean_temp_dir(temp_dir: str, temp_dir_created: bool, temp_data_file_path: str) -> None:
    """Deletes the temporary file and directory (if created).

    Args:
        temp_dir: The directory where the temporary file is located.
        temp_dir_created: A boolean indicating whether `temp_dir` was created.
        temp_data_file_path: The full path to the temporary file.
    """
    if os.getenv('KEEP_TEMP_FILE', '').lower() == 'true':
        return

    os.remove(temp_data_file_path)
    logger.info(f"Temporary file {temp_data_file_path} removed.")
    if temp_dir_created:
        os.rmdir(temp_dir)
        logger.info(f"Temporary directory {temp_dir} removed.")


def main() -> None:
    try:
        logger.info("Snapshot recorder started.")

        args = parse_args()
        load_dotenv(dotenv_path='.env.snapshot-recorder', override=True)
        load_dotenv(dotenv_path='.env', override=True)
        api_config = load_api_configuration()

        model_api: DataModelApi = DataModelApi()

        # This one should be working
        response = model_api.dimensions("Employee")

        # you don't need another part
        return

        temp_dir = os.getenv('TEMP_STORAGE_PATH', default='tmp_storage')
        temp_dir_created = ensure_temp_dir_exists(temp_dir)
        temp_data_file_path = get_temp_file_path(temp_dir, args.query_file_path)

        download_data(api_config, args.query_file_path, temp_data_file_path)

        upload_data(api_config, temp_data_file_path)

        clean_temp_dir(temp_dir, temp_dir_created, temp_data_file_path)

        logger.info("Snapshot recorder finished.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")


if __name__ == '__main__':
    main()

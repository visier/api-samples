import argparse
import logging
import os
import sys

from dotenv import load_dotenv
from visier.sdk.api.data_in import DataUploadApi
from visier.sdk.api.data_out import DataQueryApi, Configuration, ApiClient, AggregationQueryExecutionDTO


def setup_logger() -> logging.Logger:
    # turning off info logs for urllib3
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


def parse_args():
    logger.info(f"Parsing command line arguments: {sys.argv[1:]}.")  # Add arguments to log
    parser = argparse.ArgumentParser(description="Time Machine sample.")
    parser.add_argument('-q', '--query_file_path', type=str, required=True,
                        help="File path to aggregate query definition.")
    parsed_args = parser.parse_args()
    return parsed_args


def download_data(config: Configuration,
                  query_file_path: str,
                  data_file_path: str):
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

    api_client = ApiClient(config, 'Accept', 'text/csv')
    query_api = DataQueryApi(api_client)

    logger.info(f"Executing query: {query_file_path}")  # Combined messages
    response = query_api.aggregate_without_preload_content(query_dto,
                                                           _headers={'Accept': 'text/csv'})

    with open(data_file_path, mode='w') as f:
        f.write(response.data.decode())
    logger.info(f"Data saved to: {data_file_path}")  # Combined messages


def upload_data(config: Configuration, data_file_path: str):
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
    logger.info(f"Uploading data: {filename}")  # Kept for visibility
    upload_api.v1_data_upload_files_filename_put(filename=filename, body=data)


def main():
    try:
        logger.info("Application started.")
        args = parse_args()
        load_dotenv(override=True)
        api_config = load_api_configuration()

        file_name, _ = os.path.splitext(os.path.basename(args.query_file_path))
        storage_path = os.getenv('STORAGE_PATH', default='tmp_storage')
        temp_data_file = os.path.join(storage_path, f'{file_name}.csv')

        download_data(api_config, args.query_file_path, temp_data_file)

        if os.getenv('UPLOAD_DATA'):
            upload_data(api_config, temp_data_file)

        if not os.getenv('KEEP_TEMP'):
            os.remove(temp_data_file)
            logger.info(f"Temporary file removed.")  # Added for clarity

        logger.info("Application completed.")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}")


if __name__ == '__main__':
    main()

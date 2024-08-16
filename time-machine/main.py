import argparse
import logging
import os
import sys
from enum import Enum
from typing import Type, TypeVar

import requests
from visier.sdk.api.data_in import DataUploadApi

T = TypeVar('T')

from datetime import date
from dotenv import load_dotenv
from visier.sdk.api.analytic_model import DataModelApi
from visier.sdk.api.data_out import DataQueryApi, Configuration, ApiClient, AggregationQueryExecutionDTO


def setup_logger() -> logging.Logger:
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


def create_data_query_api(config: Configuration, default_headers: dict = None) -> DataQueryApi:
    api_client = ApiClient(configuration=config)
    if default_headers:
        for key, value in default_headers.items():
            api_client.set_default_header(key, value)
    return DataQueryApi(api_client)


def create_data_model_api(config: Configuration, default_headers: dict = None) -> DataModelApi:
    api_client = ApiClient(configuration=config)
    if default_headers:
        for key, value in default_headers.items():
            api_client.set_default_header(key, value)
    return DataModelApi(api_client)


def create_data_upload_api(config: Configuration, default_headers: dict = None) -> DataUploadApi:
    api_client = ApiClient(configuration=config)
    if default_headers:
        for key, value in default_headers.items():
            api_client.set_default_header(key, value)
    return DataUploadApi(api_client)


def load_api_configuration() -> Configuration:
    load_dotenv(override=True)
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


def create_aggr_query_exec_dto(file_path: str) -> AggregationQueryExecutionDTO:
    with open(file_path) as f:
        headcount_json = f.read()
    return AggregationQueryExecutionDTO.from_json(headcount_json)


def create_dto_from_json(file_path: str, dto_class: Type[T]) -> T:
    with open(file_path) as f:
        json_content = f.read()
    return dto_class.from_json(json_content)


def save_data(file_path: str, text: str):
    if os.path.exists(file_path):
        raise FileExistsError(f"File {file_path} already exists. "
                              "Couldn't save downloaded data.")
    with open(file_path, mode='w') as f:
        f.write(text)


class Command(Enum):
    DOWNLOAD = 'download'
    UPLOAD = 'upload'


def parse_args():
    logger.info("Parsing command line arguments: %s", " ".join(sys.argv))

    parser = argparse.ArgumentParser(description="Time Machine sample.")
    parser.add_argument('-q', '--query_path', type=str, help="File path to aggregate query definition.")
    parser.add_argument('-s', '--storage_path', type=str, help="File path to save downloaded data.")
    parser.add_argument('-c', '--command', type=Command, required=True,
                        help="Command type:\n"
                             "download: download data using aggregate query definition.\n"
                             "upload: upload data to overlay.")

    parser.add_argument('-d', '--date', type=str, default=date.today().strftime('%Y-%m-%d'),
                        help="Date to get snapshot in aggregate query (YYYY-MM-DD format). "
                             "Defaults to today's date if not set.")

    parsed_args = parser.parse_args()
    logger.info("Arguments parsed. %s",
                ", ".join(f"{arg}: {value}" for arg, value in vars(parsed_args).items()))
    # TODO add arguments validation
    return parsed_args


def download_data(args, config):
    query_api = create_data_query_api(config)
    query_dto = create_dto_from_json(args.query_path, AggregationQueryExecutionDTO)

    query_dto.query.time_intervals.from_date_time = args.date
    query_dto.query.time_intervals.interval_count = 6
    # using method without converting data to CellSetDTO and adding Accept header to return in csv
    response = query_api.aggregate_without_preload_content(query_dto, _headers={"Accept": "text/csv"})

    file_prefix, _ = os.path.splitext(os.path.basename(args.query_path))
    storage_file = os.path.join(args.storage_path, f'{file_prefix}_{args.date}.csv')
    save_data(storage_file, response.data.decode())


def upload_data(args, config):
    upload_api = create_data_upload_api(config, {'Content-Type': 'application/octet-stream'})
    with open(args.storage_path, 'rb') as f:
        data = f.read()

    filename = os.path.basename(args.storage_path)
    upload_api.v1_data_upload_files_filename_put(filename=filename,
                                                 body=data)


# TODO debug method
def upload_file_to_visier(config: Configuration, url: str, filename: str):
    with open(filename, 'rb') as f:
        data = f.read()

    resp = requests.put(
        os.path.join(url, filename),
        data=data,
        allow_redirects=True,
        headers={
            'apikey': os.getenv('VISIER_APIKEY'),
            'cookie': f'VisierASIDToken={config.asid_token}'}
    )
    print(resp.status_code)


def main():
    args = parse_args()
    config = load_api_configuration()

    if args.command == Command.DOWNLOAD:
        download_data(args, config)
    elif args.command == Command.UPLOAD:
        upload_data(args, config)


if __name__ == '__main__':
    main()

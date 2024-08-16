import argparse
import logging
import os
import sys
from datetime import date
from enum import Enum

from dotenv import load_dotenv
from visier.sdk.api.data_out import Configuration

from data_downloader import DataDownloader
from data_uploader import DataUploader


class Command(Enum):
    DOWNLOAD = 'download'
    UPLOAD = 'upload'


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


def load_api_configuration() -> Configuration:
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
    logger.info("Parsing command line arguments: %s", " ".join(sys.argv))

    parser = argparse.ArgumentParser(description="Time Machine sample.")
    parser.add_argument('-c', '--command', type=Command, required=True,
                        help="Command type:\n"
                             "download: download data using aggregate query definition.\n"
                             "upload: upload data to overlay.")

    parser.add_argument('-q', '--query_file_path', type=str,
                        help="File path to aggregate query definition.")
    parser.add_argument('-s', '--storage_path', type=str,
                        help="Storage path to save downloaded data files.")
    parser.add_argument('-u', '--upload_file_path', type=str,
                        help="File path to csv data to upload using Date Upload API.")
    parser.add_argument('-d', '--date', type=str, default=date.today().strftime('%Y-%m-%d'),
                        help="Date to get snapshot in aggregate query (YYYY-MM-DD format). "
                             "Defaults to today's date if not set.")

    parsed_args = parser.parse_args()
    logger.info("Arguments parsed. %s",
                ", ".join(f"{arg}: {value}" for arg, value in vars(parsed_args).items()))
    return parsed_args


def main():
    args = parse_args()
    load_dotenv(override=True)
    api_config = load_api_configuration()

    if args.command == Command.DOWNLOAD:
        downloader = DataDownloader(args.storage_path, api_config)
        downloader.download_data(args.query_file_path, args.date)
    elif args.command == Command.UPLOAD:
        uploader = DataUploader(api_config)
        uploader.upload_data(args.upload_file_path)


if __name__ == '__main__':
    main()

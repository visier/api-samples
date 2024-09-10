import argparse
import json
import logging
import os
from typing import Any, Dict, List

from dotenv import dotenv_values
from visier_api_analytic_model import DataModelApi
from visier_api_core import Configuration, ApiClient
from visier_api_data_out import DataVersionExportApi, DataQueryApi

from change_fetcher import ChangeFetcher
from command_handler import CommandHandler, ExtractionMode
from constants.config import *
from data_store import DataStore
from dv_manager import DVManager


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


def parse_args() -> argparse.Namespace:
    logger.info("Parsing command line arguments.")
    parser = argparse.ArgumentParser(description='DV Query History sample.')
    parser.add_argument('-l', '--list_dv', action='store_true', required=False,
                        help="If provided, lists available data versions and then exits.")
    parser.add_argument('-q', '--query_path', type=str, required=False,
                        help="File path to query.")
    parser.add_argument('-b', '--base_data_version', type=int, required=False,
                        help="Base DV number to run a delta export job.")
    parser.add_argument('-d', '--data_version', type=int, required=False,
                        help="DV number to export.")
    parser.add_argument('-e', '--export_uuid', type=str,
                        help="Optional UUID of the DV export to download files from. "
                             "If provided, a DV export job isn't scheduled.",
                        required=False)
    parser.add_argument('-m', '--mode',
                        type=ExtractionMode,
                        help="Extraction mode:\n"
                             "restate: fetch the full history for an analytic object.\n"
                             "last: fetch only the last change for an analytic object.",
                        required=True)

    parsed_args = parser.parse_args()
    logger.info("Arguments parsed. %s", ", ".join(f"{arg}: {value}" for arg, value in vars(parsed_args).items()))

    if parsed_args.list_dv:
        logger.info("Utility was called with list_dv flag. No other arguments are required.")
        return parsed_args

    if not parsed_args.query_path:
        raise Exception("Query path is required.")

    if parsed_args.export_uuid:
        logger.info("Export UUID provided. Will not schedule a DV export job.")
        return parsed_args

    if not parsed_args.data_version:
        raise Exception("At least one of data_version or export_uuid must be provided.")

    return parsed_args


def load_config() -> Dict[str, Any]:
    config = {
        **dotenv_values('.env.query-changes'),
        **dotenv_values('.env.visier-auth'),
        **dotenv_values('.env')
    }
    logger.info("Configuration was loaded.")
    return config


def create_command_handler(config: Dict[str, Any]) -> CommandHandler:
    """Create a CommandHandler instance with the provided session and configuration."""
    api_config = Configuration(
        host=config[VISIER_HOST],
        api_key=config[VISIER_APIKEY],
        username=config[VISIER_USERNAME],
        password=config[VISIER_PASSWORD],
        client_id=config[VISIER_CLIENT_ID],
        client_secret=config[VISIER_CLIENT_SECRET],
        redirect_uri=config[VISIER_REDIRECT_URI],
        vanity=config[VISIER_VANITY])
    api_client = ApiClient(api_config)

    dv_api = DataVersionExportApi(api_client)
    dv_manager = DVManager(dv_api,
                           bool(config[DV_SAVE_EXPORT_FILES_ON_DISK]),
                           config['DV_EXPORT_FILES_PATH'],
                           job_status_poll_interval_sec=int(config[DV_JOB_STATUS_POLL_INTERVAL_SECONDS]),
                           job_timeout_sec=int(config[DV_JOB_TIMEOUT_SECONDS]))

    model_api = DataModelApi(api_client)
    query_api = DataQueryApi(api_client)
    change_fetcher = ChangeFetcher(model_api, query_api)

    data_store = DataStore(config['DB_URL'])

    return CommandHandler(dv_manager, change_fetcher, data_store)


def get_query_files(path: str) -> List[str]:
    if os.path.isfile(path):
        return [path]
    elif os.path.isdir(path):
        return [os.path.join(path, f) for f in os.listdir(path) if f.endswith('.json')]
    else:
        raise ValueError(f"The path {path} is neither a file nor a directory.")


def main() -> None:
    args = parse_args()
    config = load_config()

    command_handler = create_command_handler(config)

    # List available data versions for export
    if args.list_dv:
        data_versions = command_handler.get_data_versions()
        logger.info(f"Data versions fetched successfully:\n {json.dumps(data_versions, indent=2)}")
        return

    # If export_uuid is not provided, execute a DV export job
    export_uuid = args.export_uuid or command_handler.execute_export_job(args.base_data_version, args.data_version)

    # Load one or several query files and process them
    for query_file in get_query_files(args.query_path):
        with open(query_file, 'r') as f:
            query = json.load(f)
        command_handler.process_query(export_uuid, query, args.mode)


if __name__ == "__main__":
    main()

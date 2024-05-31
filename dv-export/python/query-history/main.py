import argparse
import json
import logging
from collections import OrderedDict
from typing import Any

from dotenv import dotenv_values
from visier.connector import make_auth, VisierSession

from constants import *
from data_store import DataStore
from dv_manager import DVManager
from history_fetcher import HistoryFetcher


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
    parser.add_argument('-q', '--query_path', type=str, required=False,
                        help="Filepath to query template.")
    parser.add_argument('-d', '--data_version', type=int, required=False,
                        help="Data Version number the script should export.")
    parser.add_argument('-b', '--base_data_version', type=int, required=False,
                        help="Base Data Version number to compute a diff from.")
    parser.add_argument('-e', '--export_uuid', type=str,
                        help="Optional export UUID to retrieve export metadata for. "
                             "If provided, a DV export job will not be scheduled.",
                        required=False)
    parser.add_argument('-l', '--list_dv', action='store_true', required=False,
                        help="If provided, will show list of available data versions.")

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


def load_config() -> dict[str, Any]:
    config = {
        **dotenv_values('.env.query-history'),
        **dotenv_values('.env.visier-auth'),
        **dotenv_values('.env')
    }
    logger.info("Configuration was loaded.")
    return config


def get_filter_property(query):
    filters = query.get(FILTERS, [{}])
    member_set = filters[0].get(MEMBER_SET, {})
    values = member_set.get(VALUES, {})
    included = values.get(INCLUDED)

    if included is None or not included.startswith('${{') or not included.endswith('}}'):
        logger.warning("Filter property not found in query. History will be fetched without filters.")
        return None
    filter_property = included[3:-2]
    logger.info(f"Filter property is {filter_property}")
    return filter_property


def main() -> None:
    args = parse_args()
    config = load_config()

    auth = make_auth(env_values=OrderedDict(config))
    with VisierSession(auth) as session:
        dv_manager = DVManager(session,
                               bool(config[DV_SAVE_EXPORT_FILES_ON_DISK]),
                               config[DV_EXPORT_FILES_PATH],
                               job_status_poll_interval_sec=int(config[DV_JOB_STATUS_POLL_INTERVAL_SECONDS]),
                               job_timeout_sec=int(config[DV_JOB_TIMEOUT_SECONDS]))

        # List available data versions for export
        if args.list_dv:
            data_versions = dv_manager.get_data_versions()
            logger.info(f"Data versions fetched successfully:\n {json.dumps(data_versions, indent=2)}")
            return

        # Execute export job if export UUID is not provided
        if args.export_uuid is None:
            export_uuid = dv_manager.execute_export_job(args.base_data_version, args.data_version)
        else:
            export_uuid = args.export_uuid

        # Load query from file
        with open(args.query_path, 'r') as query_file:
            query = json.load(query_file)

        analytic_object = query[SOURCE][ANALYTIC_OBJECT]
        logger.info(f"Analytic object to fetch history: {analytic_object}")
        table_metadata = dv_manager.get_table_metadata(export_uuid, analytic_object)

        # Trying to get filter property from query
        filter_property = get_filter_property(query)
        filter_values = None
        if filter_property is not None:
            # Get filter values from export files
            file_infos = table_metadata[COMMON_COLUMNS][FILES]
            property_values = dv_manager.read_property_values(export_uuid, file_infos, filter_property)
            filter_values = set(property_values)

        # Fetch analytic object history
        history_fetcher = HistoryFetcher(session)
        properties, history_rows = history_fetcher.list_changes(query, filter_values)

        # Save history to database
        data_store = DataStore(config[DB_URL])
        data_store.drop_table_if_exists(analytic_object)
        data_store.create_table(analytic_object, query[COLUMNS], properties)
        data_store.save_to_db(analytic_object, history_rows)


if __name__ == "__main__":
    main()

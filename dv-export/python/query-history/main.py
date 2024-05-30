import argparse
import json
import logging
from collections import OrderedDict

from dotenv import dotenv_values
from visier.connector import make_auth, VisierSession

from data_store import DataStore
from dv_manager import DVManager
from history_fetcher import HistoryFetcher

# TODO update setup of logger
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    filename='app.log',
    filemode='a',
)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(name)s: %(message)s'))
logger = logging.getLogger('main')
logger.addHandler(console_handler)


def parse_args() -> argparse.Namespace:
    logger.info("Parsing command line arguments.")
    parser = argparse.ArgumentParser(description='DV Query History sample.')
    parser.add_argument('-q', '--query_path', type=str,
                        help='Filepath to query template.', required=False)
    parser.add_argument('-d', '--data_version', type=int,
                        help='Data Version number the script should export.', required=False)
    parser.add_argument('-b', '--base_data_version', type=int,
                        help='Base Data Version number to compute a diff from.', required=False)
    parser.add_argument('-e', '--export_uuid', required=False, type=str,
                        help='Optional export UUID to retrieve export metadata for. '
                             'If provided, a DV export job will not be scheduled.')
    parser.add_argument('-l', '--list_dv', required=False, action='store_true',
                        help='If provided, will show list of available data versions.')

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


if __name__ == "__main__":
    logger.info("Script started.")
    args = parse_args()

    config = {
        **dotenv_values('.env.query-history'),
        **dotenv_values('.env.visier-auth'),
        **dotenv_values('.env')
    }

    auth = make_auth(env_values=OrderedDict(config))
    with VisierSession(auth) as session:
        list_dv = args.list_dv
        dv_manager = DVManager(session,
                               job_status_poll_interval_sec=config['DV_POLL_INTERVAL_SECS'],
                               job_timeout_sec=config['DV_EXPORT_JOB_TIMEOUT_SECS'])
        if args.list_dv:
            data_versions = dv_manager.get_data_versions()
            logger.info(f"Data versions fetched successfully:\n {json.dumps(data_versions, indent=2)}")
            exit(0)

        with open(args.query_path, 'r') as query_file:
            query = json.load(query_file)

        subject = query['source']['analyticObject']
        filter_property = query['filters'][0]['memberSet']['values']['included'].strip('${}')

        # Fetch property changes between Data Versions
        if args.export_uuid is None:
            export_uuid = dv_manager.execute_export_job(args.base_data_version, args.data_version)
        else:
            export_uuid = args.export_uuid
        table_metadata = dv_manager.get_table_metadata(export_uuid, subject)
        file_infos = table_metadata['commonColumns']['files']
        property_values = dv_manager.read_property_values(export_uuid, file_infos, filter_property)
        logger.info("Fetched subject property changes successfully.")

        # Fetch history and save to database
        filter_values = set(property_values)
        history_fetcher = HistoryFetcher(session)
        history_rows = history_fetcher.list_changes(query, filter_values)

        data_store = DataStore(config['DB_URL'])
        data_store.drop_table(subject)
        query_columns = query['columns']
        table_columns = table_metadata['commonColumns']['columns']
        data_store.create_table(subject, query_columns, table_columns)
        data_store.save_to_db(subject, history_rows)

    logger.info("Script completed.")

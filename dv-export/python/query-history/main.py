import argparse
import json
import logging

from visier.connector import make_auth, VisierSession

from data_store import DataStore
from dv_changes_fetcher import DVChangesFetcher
from history_fetcher import HistoryFetcher

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


def parse_args() -> argparse.Namespace:
    logger.info("Parsing command line arguments.")
    parser = argparse.ArgumentParser(description='DV Query History sample.')
    parser.add_argument('-d', '--data_version', type=int,
                        help='Data Version number the script should export.', required=False)
    parser.add_argument('-b', '--base_data_version', type=int,
                        help='Base Data Version number to compute a diff from.', required=False)
    parser.add_argument('-e', '--export_uuid', required=False, type=str,
                        help='Optional export UUID to retrieve export metadata for. '
                             'If provided, a DV export job will not be scheduled.')
    parsed_args = parser.parse_args()
    if parsed_args.data_version is None and parsed_args.export_uuid is None:
        raise Exception("At least one of data_version or export_uuid must be provided")
    logger.info("Arguments parsed successfully: %s", parsed_args)
    return parsed_args


if __name__ == "__main__":
    logger.info("Script started.")
    args = parse_args()
    with open("settings.json", 'r') as query_file:
        settings = json.load(query_file)

    subject = settings['query']['source']['analyticObject']
    filter_property = settings['query']['filters'][0]['memberSet']['values']['included'].strip('${}')
    logger.info("Settings loaded successfully.")

    auth = make_auth(env_values=settings['server'])
    with VisierSession(auth) as session:
        dv_changes_fetcher = DVChangesFetcher(session)
        property_values = dv_changes_fetcher.fetch_subject_property_changes(
            base_data_version=args.base_data_version,
            data_version=args.data_version,
            export_uuid=args.export_uuid,
            subject_name=subject,
            property_name=filter_property)
        logger.info("Fetched subject property changes successfully.")

        # cleaning filter duplicates
        filter_values = set(property_values)
        history_fetcher = HistoryFetcher(session)
        history_table = history_fetcher.list_changes(settings['query'], filter_values)

        data_store = DataStore(settings['db_url'])
        data_store.save_to_db(history_table, subject)
        logger.info("Data saved to database successfully.")

    logger.info("Script completed.")

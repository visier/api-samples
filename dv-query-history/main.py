import argparse
import json
import logging

from visier.connector import make_auth, VisierSession

from data_store import DataStore
from dv_changes_fetcher import DVChangesFetcher
from history_fetcher import HistoryFetcher

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    # noinspection DuplicatedCode
    parser = argparse.ArgumentParser(description='DV Export API example script.')
    parser.add_argument('-d', '--data_version', type=int,
                        help='Data Version number the script should export.', required=False)
    parser.add_argument('-b', '--base_data_version', type=int,
                        help='Base Data Version number to compute a diff from.', required=False)
    parser.add_argument('-e', '--export_uuid', required=False, type=str,
                        help='Optional export UUID to retrieve export metadata for. '
                             'If provided, a DV export job will not be scheduled.')
    parsed_args = parser.parse_args()
    if parsed_args.data_version is None and parsed_args.export_uuid is None:
        raise Exception(f"At least one of data_version or export_uuid must be provided")
    return parsed_args


if __name__ == "__main__":
    args = parse_args()
    with open("settings.json", 'r') as query_file:
        settings = json.load(query_file)

    subject = settings['query']['source']['analyticObject']
    filter_property = settings['query']['filters'][0]['memberSet']['values']['included'].strip('${}')

    auth = make_auth(env_values=settings['server'])
    with VisierSession(auth) as session:
        dv_changes_fetcher = DVChangesFetcher(session)
        property_values = dv_changes_fetcher.fetch_subject_property_changes(
            base_data_version=args.base_data_version,
            data_version=args.data_version,
            export_uuid=args.export_uuid,
            subject_name=subject,
            property_name=filter_property)

        # remove duplicates
        filter_values = set(property_values)
        history_fetcher = HistoryFetcher(session)
        history_table = history_fetcher.query_changes(settings['query'], filter_values)
        data_store = DataStore(settings['db_url'])
        data_store.save_to_db(history_table, subject)

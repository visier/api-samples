import logging
import typing

from changes_fetcher import ChangesFetcher
from constants import *
from data_store import DataStore
from dv_manager import DVManager

logger = logging.getLogger(__name__)


class CommandHandler:
    """
    Handle commands from the user:
    - Retrieves a list of available data versions for export;
    - Executes a DV export task, waits for its completion, and returns the export UUID;
    - Processes requests using filtering and saves the changes to the database.
    """

    def __init__(self, dv_manager: DVManager, changes_fetcher: ChangesFetcher, data_store: DataStore):
        self.dv_manager = dv_manager
        self.changes_fetcher = changes_fetcher
        self.data_store = data_store

    def get_data_versions(self):
        """Get the list of data versions available for export."""
        return self.dv_manager.get_data_versions()

    def execute_export_job(self, base_data_version: int, data_version: int) -> str:
        """Execute a DV export job, wait for it to complete, and return the export UUID."""
        return self.dv_manager.execute_export_job(base_data_version, data_version)

    def process_query(self, export_uuid: str, query: dict[str, typing.Any]):
        """Process the query using filtering and save changes to the database."""
        analytic_object = query[SOURCE][ANALYTIC_OBJECT]
        logger.info(f"Analytic object to fetch changes: {analytic_object}")

        # Trying to get filter property from query
        filter_values = self._read_filter_values(analytic_object, export_uuid, query)

        # Fetch analytic object changes
        properties, changes_rows = self.changes_fetcher.list_changes(query, filter_values)

        # Save changes to the database
        self._save_to_db(analytic_object, query, properties, changes_rows)

    def _read_filter_values(self, analytic_object_name: str, export_uuid: str, query):
        filter_property_name = self._get_filter_property_name(query)
        filter_values = None
        if filter_property_name is not None:
            # Get filter values from export files
            property_values = self.dv_manager.read_property_values(export_uuid, analytic_object_name,
                                                                   filter_property_name)
            filter_values = set(property_values)
        return filter_values

    @staticmethod
    def _get_filter_property_name(query: dict[str, typing.Any]):
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

    def _save_to_db(self, analytic_object, query, properties, changes_rows):
        """Drop and create a table in the database and save changes to it."""
        self.data_store.drop_table_if_exists(analytic_object)
        self.data_store.create_table(analytic_object, query[COLUMNS], properties)
        self.data_store.save_to_db(analytic_object, changes_rows)
        logger.info(f"Changes for {analytic_object} were saved to the database.")

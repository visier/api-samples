import logging
import time
import typing
from enum import Enum

from changes_fetcher import ChangesFetcher
from constants import *
from data_store import DataStore
from dv_manager import DVManager

logger = logging.getLogger(__name__)


class QueryMode(Enum):
    """
    Query modes.
    RESTATE: fetch full history for analytic object.
    DELTA: fetch only the last change for the analytic object.
    """
    RESTATE = 'restate'
    DELTA = 'delta'


class CommandHandler:
    """
    Handle commands from the user:
    - Retrieves a list of available data versions for export;
    - Executes a DV export task, waits for its completion, and returns the export UUID;
    - Processes requests using filtering and saves the changes to the database.
    """

    record_modes = {
        QueryMode.RESTATE: CHANGES,
        QueryMode.DELTA: NORMAL
    }

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

    def process_query(self, export_uuid: str, query: dict[str, typing.Any], query_mode: QueryMode):
        """Process the query using filtering and save changes to the database."""
        analytic_object = query[SOURCE][ANALYTIC_OBJECT]
        logger.info(f"Analytic object to fetch changes: {analytic_object}")

        # Trying to get filter property from query
        filter_name = self._get_filter_name(query)
        filter_values = self._read_filter_values(export_uuid, analytic_object, filter_name) if filter_name else None

        # Getting metadata and properties for analytic object
        analytic_object_metadata, properties = self.changes_fetcher.get_analytic_object_metadata(analytic_object)

        # Getting start and end for query changes depending on command mode
        start_time_epoch, end_time_epoch = self._get_time_period_borders(export_uuid,
                                                                         analytic_object_metadata,
                                                                         query_mode)

        # Fetch analytic object changes
        changes_rows = self.changes_fetcher.execute_query_list(query, start_time_epoch, end_time_epoch,
                                                               self.record_modes[query_mode], filter_values)

        # Save changes to the database
        self._save_to_db(analytic_object, filter_name, filter_values, query, properties, changes_rows, query_mode)

    def _get_time_period_borders(self, export_uuid: str, analytic_object_metadata: dict[str, typing.Any],
                                 query_mode: QueryMode) -> (int, int):
        if query_mode == QueryMode.DELTA:
            start_time_epoch, end_time_epoch = self.dv_manager.get_export_data_version_times(export_uuid)
        elif query_mode == QueryMode.RESTATE:
            start_time_epoch, end_time_epoch = int(analytic_object_metadata[DATA_START_DATE]), int(time.time() * 1000)
        else:
            raise ValueError(f"Unknown command mode: {query_mode}")
        return start_time_epoch, end_time_epoch

    def _read_filter_values(self, export_uuid: str, analytic_object_name: str, filter_name: str):
        # Get filter values from export files
        property_values = self.dv_manager.read_property_values(export_uuid, analytic_object_name, filter_name)
        filter_values = set(property_values)
        return filter_values

    @staticmethod
    def _get_filter_name(query: dict[str, typing.Any]) -> str | None:
        filters = query.get(FILTERS, [{}])
        member_set = filters[0].get(MEMBER_SET, {})
        values = member_set.get(VALUES, {})
        included = values.get(INCLUDED)

        if included is None or not included.startswith('${{') or not included.endswith('}}'):
            logger.warning("Filter property not found in query. History will be fetched without filters.")
            return None
        filter_name = included[3:-2]
        logger.info(f"Filter name is {filter_name}")
        return filter_name

    def _save_to_db(self, analytic_object,
                    filter_name,
                    filter_values,
                    query,
                    properties,
                    changes_rows,
                    query_mode: QueryMode):
        """Drop and create a table in the database and save changes to it."""
        exists = self.data_store.table_exists(analytic_object)
        if not exists:
            self.data_store.create_table(analytic_object, query[COLUMNS], properties)
        elif query_mode == QueryMode.RESTATE:
            self.data_store.delete_rows(analytic_object, filter_name, filter_values)

        self.data_store.save_to_db(analytic_object, changes_rows)
        logger.info(f"Changes for {analytic_object} were saved to the database.")

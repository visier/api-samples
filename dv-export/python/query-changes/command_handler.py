import logging
import time
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Set, List, Optional

import math
from visier_api_analytic_model import AnalyticObjectDTO, PropertiesDTO
from visier_api_data_out import GoogleProtobufAny, ListQueryExecutionDTO, QueryTimeIntervalDTO, \
    ListQueryExecutionOptionsDTO, DataVersionExportDataVersionsDTO

from change_fetcher import ChangeFetcher
from constants.json import *
from data_store import DataStore
from dv_manager import DVManager

logger = logging.getLogger(__name__)


class ExtractionMode(Enum):
    """
    Extraction modes for fetching analytic object changes:
    - RESTATE: Fetch the full history of a record.
    - LAST: Fetch the most recent change for a record.
    """
    RESTATE = 'restate'
    LAST = 'last'


class CommandHandler:
    """
    Handle commands from the user:
    - Retrieves a list of DVs available to export.
    - Runs a DV export job, waits for the job to complete, and returns the export UUID.
    - Processes requests using filtering and saves the changes to the database.
    """

    # Default query limit for fetching changes
    DEFAULT_QUERY_LIMIT = 100000

    # Record mode for list query
    record_modes = {
        ExtractionMode.RESTATE: CHANGES,
        ExtractionMode.LAST: NORMAL
    }

    def __init__(self, dv_manager: DVManager, change_fetcher: ChangeFetcher, data_store: DataStore):
        self.dv_manager = dv_manager
        self.change_fetcher = change_fetcher
        self.data_store = data_store

    def get_data_versions(self) -> DataVersionExportDataVersionsDTO:
        """Retrieve the list of DVs available to export."""
        return self.dv_manager.get_data_versions()

    def execute_export_job(self, base_data_version: int, data_version: int) -> Optional[str]:
        """Run a DV export job, wait for it to complete, and then return the export UUID."""
        return self.dv_manager.execute_export_job(base_data_version, data_version)

    def process_query(self, export_uuid: str, query: Dict[str, Any], extraction_mode: ExtractionMode) -> None:
        """Process the query using filtering and save changes to the database."""
        analytic_object_name = query[SOURCE][ANALYTIC_OBJECT]
        logger.info(f"Analytic object to fetch changes: {analytic_object_name}")

        # Retrieve filter from query
        filter_name = self._get_filter_name(query)
        filter_values = self._read_filter_values(
            export_uuid, analytic_object_name, filter_name) if filter_name else None
        list_query_dto = self._create_list_query_dto(filter_values, query)

        # Retrieve analytic object changes
        analytic_object_dto, properties_dto = self.change_fetcher.get_analytic_object_metadata(analytic_object_name)

        # Getting start and end for query changes depending on command mode
        time_interval_dto = self._create_time_interval_dto(export_uuid, analytic_object_dto, extraction_mode)

        self._setup_query_options(list_query_dto, extraction_mode, time_interval_dto)

        # Fetch analytic object changes
        protobuf_changes = self.change_fetcher.execute_query_list(list_query_dto)

        # Save changes to the database
        self._save_to_db(list_query_dto, properties_dto, filter_name, filter_values, protobuf_changes, extraction_mode)

    def _setup_query_options(self,
                             list_query_dto: ListQueryExecutionDTO,
                             extraction_mode: ExtractionMode,
                             time_interval_dto: QueryTimeIntervalDTO) -> None:
        list_query_dto.time_interval = time_interval_dto
        if list_query_dto.options is None:
            list_query_dto.options = ListQueryExecutionOptionsDTO()
        list_query_dto.options.record_mode = self.record_modes[extraction_mode]
        if list_query_dto.options.limit is None:
            list_query_dto.options.limit = self.DEFAULT_QUERY_LIMIT

    @staticmethod
    def _create_list_query_dto(filter_values: Set[str], query: Dict[str, Any]) -> ListQueryExecutionDTO:
        if filter_values is not None:
            logger.info(f"List changes for unique filter: {len(filter_values)}.")
            query[FILTERS][0][MEMBER_SET][VALUES][INCLUDED] = [
                {PATH: [filter_value]} for filter_value in filter_values
            ]
        else:
            logger.info(f"List changes without filters.")
        return ListQueryExecutionDTO.from_dict(query)

    def _create_time_interval_dto(self,
                                  export_uuid: str,
                                  analytic_object_dto: AnalyticObjectDTO,
                                  extraction_mode: ExtractionMode) -> QueryTimeIntervalDTO:
        if extraction_mode == ExtractionMode.LAST:
            start_time_epoch, end_time_epoch = self.dv_manager.get_export_data_version_times(export_uuid)
        elif extraction_mode == ExtractionMode.RESTATE:
            start_time_epoch, end_time_epoch = int(analytic_object_dto.data_start_date), int(time.time() * 1000)
        else:
            raise ValueError(f"Unknown command mode: {extraction_mode}")

        start_date = datetime.utcfromtimestamp(start_time_epoch / 1000)
        end_date = datetime.utcfromtimestamp(end_time_epoch / 1000)
        # Calculate the number of days between the start and end dates
        diff_days = math.ceil((end_date - start_date).total_seconds() / 86400)
        logger.info("Time period to fetch: "
                    f"{start_time_epoch} ({start_date}) - {end_time_epoch} ({end_date}). "
                    f"Days: {diff_days}.")

        return QueryTimeIntervalDTO(
            from_instant=str(end_time_epoch),
            interval_period_type=DAY,
            interval_period_count=diff_days,
            direction=BACKWARD
        )

    def _read_filter_values(self, export_uuid: str, analytic_object_name: str, filter_name: str) -> Set[str]:
        # Get filter values from export files
        property_values = self.dv_manager.read_property_values(export_uuid, analytic_object_name, filter_name)
        return set(property_values)

    @staticmethod
    def _get_filter_name(query: Dict[str, Any]) -> Optional[str]:
        filters = query.get(FILTERS, [{}])
        member_set = filters[0].get(MEMBER_SET, {})
        values = member_set.get(VALUES, {})
        included = values.get(INCLUDED)

        if included is None or not included.startswith('${{') or not included.endswith('}}'):
            logger.warning("Filter not found in query. Fetching history without filters.")
            return None
        filter_name = included[3:-2]
        logger.info(f"Filter is {filter_name}")
        return filter_name

    def _save_to_db(self,
                    list_query_dto: ListQueryExecutionDTO,
                    properties_dto: PropertiesDTO,
                    filter_name: str,
                    filter_values: Set[str],
                    protobuf_changes: List[GoogleProtobufAny],
                    extraction_mode: ExtractionMode) -> None:
        """Create table if it does not exist and restate or append changes to the table."""

        analytic_object_name = list_query_dto.source.analytic_object
        if not self.data_store.table_exists(analytic_object_name):
            self.data_store.create_table(analytic_object_name, list_query_dto.columns, properties_dto)
        elif extraction_mode == ExtractionMode.RESTATE:
            self.data_store.delete_rows(analytic_object_name, filter_name, filter_values)

        self.data_store.save_to_db(analytic_object_name, protobuf_changes)

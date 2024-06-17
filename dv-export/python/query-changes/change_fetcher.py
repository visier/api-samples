import copy
import logging
import math
from datetime import datetime
from typing import Optional, Any

from visier.api import ModelApiClient, QueryApiClient
from visier.connector import VisierSession

from constants import *

logger = logging.getLogger(__name__)


class ChangeFetcher:
    """Fetches all changes that are defined for a given analytic object."""

    DEFAULT_QUERY_LIMIT = 100000

    # Additional properties to fetch for different object types.
    additional_properties = {
        "SUBJECT": [
            {
                'id': 'ValidityStart',
                'displayName': 'ValidityStart',
                'description': 'Start time of data validity.',
                'dataType': 'Date',
                'primitiveDataType': 'Date'
            },
            {
                'id': 'ValidityEnd',
                'displayName': 'ValidityEnd',
                'description': 'End time of data validity.',
                'dataType': 'Date',
                'primitiveDataType': 'Date'
            },
        ],
        "EVENT": [
            {
                'id': 'EventDate',
                'displayName': 'EventDate',
                'description': 'Event occurred time.',
                'dataType': 'Date',
                'primitiveDataType': 'Date'
            }
        ]
    }

    def __init__(self, session: VisierSession):
        self.model_client = ModelApiClient(session, raise_on_error=True)
        self.query_client = QueryApiClient(session, raise_on_error=True)

    def execute_query_list(self,
                           query_orig: dict[str, Any],
                           start_date_epoch: int,
                           end_data_epoch: int,
                           record_mode: str,
                           filter_values: Optional[set[str]] = None) -> list[list[str]]:
        """Execute a query to list changes for a given analytic object."""
        time_interval = self._get_time_interval(start_date_epoch, end_data_epoch)
        query_updated = self._prepare_query(query_orig, time_interval, record_mode, filter_values)
        changes = self._fetch_data_with_pagination(query_updated)
        return changes

    def get_analytic_object_metadata(self, analytic_object_name: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        analytic_object_response = self.model_client.get_analytic_objects([analytic_object_name])
        analytic_object_metadata = analytic_object_response.json()[ANALYTIC_OBJECTS][0]
        properties = self.model_client.get_properties(analytic_object_name).json()[PROPERTIES]
        self._append_additional_properties(properties, analytic_object_metadata)
        return analytic_object_metadata, properties

    def _prepare_query(self,
                       query_orig: dict[str, Any],
                       time_interval: dict[str, Any],
                       record_mode: str = NORMAL,
                       filter_values: Optional[set[str]] = None) -> dict[str, Any]:
        query = copy.deepcopy(query_orig)
        if OPTIONS not in query:
            query[OPTIONS] = {}
        query[OPTIONS][RECORD_MODE] = record_mode
        if filter_values is not None:
            logger.info(f"List changes for unique filter: {len(filter_values)}.")
            query[FILTERS][0][MEMBER_SET][VALUES][INCLUDED] = [
                {PATH: [filter_value]} for filter_value in filter_values
            ]
        else:
            logger.info(f"List changes without filters.")
        query[TIME_INTERVAL] = time_interval
        if query[OPTIONS].get(LIMIT) is None:
            query[OPTIONS][LIMIT] = self.DEFAULT_QUERY_LIMIT
        return query

    def _fetch_data_with_pagination(self, query: dict[str, Any]) -> list[list[str]]:
        limit = query[OPTIONS][LIMIT]
        page_num = 0
        all_rows = []
        while True:
            query[OPTIONS][PAGE] = page_num
            result_table = self.query_client.list(query)
            rows = list(result_table.rows())
            logger.info(f"Batch changes for {query[SOURCE]} fetched page: {page_num}, rows: {len(rows)}.")
            all_rows.extend(rows)
            if len(rows) < limit:
                break
            page_num += 1
        logger.info(f"Full changes for {query[SOURCE]} fetched rows: {len(all_rows)}.")
        return all_rows

    def _append_additional_properties(self, properties: list[dict[str, Any]], analytic_object: dict[str, Any]) -> None:
        object_type = analytic_object.get(TYPE)
        additional_props = self.additional_properties.get(object_type, [])
        for prop in additional_props:
            property_updated = prop.copy()
            property_updated[ID] = f"{analytic_object[ID]}.{prop[ID]}"
            properties.append(property_updated)

    @staticmethod
    def _get_time_interval(start_date_epoch: int, end_date_epoch: int) -> dict[str, Any]:
        """Retrieve the time range from timestamp until UTC now."""
        start_date = datetime.utcfromtimestamp(start_date_epoch / 1000)
        end_date = datetime.utcfromtimestamp(end_date_epoch / 1000)

        diff_days = math.ceil((end_date - start_date).total_seconds() / 86400)
        logger.info("Time period to fetch: "
                    f"{start_date_epoch} ({start_date}) - {end_date_epoch} ({end_date}). "
                    f"Days: {diff_days}.")
        return {
            FROM_INSTANT: end_date_epoch,
            INTERVAL_PERIOD_TYPE: DAY,
            INTERVAL_PERIOD_COUNT: diff_days,
            DIRECTION: BACKWARD
        }

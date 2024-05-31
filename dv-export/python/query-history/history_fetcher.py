import copy
import logging
import math
from datetime import datetime

from visier.api import ModelApiClient, QueryApiClient
from visier.connector import VisierSession

from constants import *

logger = logging.getLogger(__name__)


class HistoryFetcher:
    """Fetches values for all history of subject."""
    DEFAULT_QUERY_LIMIT = 1000

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

    def list_changes(self,
                     query_orig: dict[str, any],
                     filters_values: set[str] = None) -> (list[dict[str, any]], list[list[str]]):
        """Query list changes for subject using filters_values."""
        analytic_object, properties = self._get_analytic_object_metadata(query_orig)
        query_updated = self._prepare_query(query_orig, analytic_object, filters_values)
        all_rows = self._fetch_data_with_pagination(query_updated)
        logger.info(f"History for {query_updated[SOURCE]} fetched rows: {len(all_rows)}.")
        return properties, all_rows

    def _get_analytic_object_metadata(self, query: dict[str, any]) -> tuple[dict[str, any], list[dict[str, any]]]:
        analytic_object_response = self.model_client.get_analytic_objects([query[SOURCE][ANALYTIC_OBJECT]])
        analytic_object = analytic_object_response.json()[ANALYTIC_OBJECTS][0]
        properties = self.model_client.get_properties(query[SOURCE][ANALYTIC_OBJECT]).json()[PROPERTIES]
        self._append_additional_properties(properties, analytic_object)
        return analytic_object, properties

    def _prepare_query(self,
                       query_orig: dict[str, any],
                       analytic_object: dict[str, any],
                       filters_values: set[str] = None) -> dict[str, any]:
        query = copy.deepcopy(query_orig)
        if filters_values is not None:
            logger.info(f"List changes for filter_values: {len(filters_values)}.")
            query[FILTERS][0][MEMBER_SET][VALUES][INCLUDED] = [
                {PATH: [filter_value]} for filter_value in filters_values
            ]
        else:
            logger.info(f"List changes without filter_values.")
        query[TIME_INTERVAL] = self._get_time_interval(int(analytic_object[DATA_START_DATE]))
        if query[OPTIONS][LIMIT] is None:
            query[OPTIONS][LIMIT] = self.DEFAULT_QUERY_LIMIT
        return query

    def _fetch_data_with_pagination(self, query: dict[str, any]) -> list[list[str]]:
        limit = query[OPTIONS][LIMIT]
        page_num = 0
        all_rows = []
        while True:
            query[OPTIONS][PAGE] = page_num
            result_table = self.query_client.list(query)
            rows = list(result_table.rows())
            logger.info(f"History for {query[SOURCE]} page: {page_num}, rows: {len(rows)}.")
            all_rows.extend(rows)
            if len(rows) < limit:
                break
            page_num += 1
        return all_rows

    def _append_additional_properties(self, properties: list[dict[str, any]], analytic_object: dict[str, any]) -> None:
        object_type = analytic_object.get(TYPE)
        additional_props = self.additional_properties.get(object_type, [])
        for prop in additional_props:
            property_updated = prop.copy()
            property_updated[ID] = f"{analytic_object[ID]}.{prop[ID]}"
            properties.append(property_updated)

    @staticmethod
    def _get_time_interval(data_start_date: int) -> dict[str, any]:
        """Get the time range until utc now."""
        start_date = datetime.utcfromtimestamp(data_start_date / 1000)
        current_date = datetime.utcnow()
        diff_days = math.ceil((current_date - start_date).total_seconds() / 86400)
        logger.info("History period to fetch: "
                    f"{data_start_date} ({start_date}) - {current_date.timestamp() * 1000} ({current_date}). "
                    f"Days: {diff_days}.")
        return {
            FROM_INSTANT: data_start_date,
            INTERVAL_PERIOD_TYPE: PERIOD_TYPE_DAY,
            INTERVAL_PERIOD_COUNT: diff_days,
            DIRECTION: FORWARD
        }

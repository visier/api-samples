import json
import logging
from datetime import datetime
from typing import Dict, Any, Set

from visier.api import ModelApiClient, QueryApiClient
from visier.connector import VisierSession

from constants import *

logger = logging.getLogger(__name__)


class HistoryFetcher:
    """Fetches values for all history of subject."""

    def __init__(self, session: VisierSession):
        self.model_client = ModelApiClient(session, raise_on_error=True)
        self.query_client = QueryApiClient(session, raise_on_error=True)

    def list_changes(self, query: Dict[str, Any], filters_values: Set[str]) -> []:
        """Query list changes for subject using filters_values."""
        logger.info(f"List changes for unique filter_values: {len(filters_values)}.")

        # Update query with time interval and filter values
        query[TIME_INTERVAL] = self.__get_time_interval(query)
        query[FILTERS][0][MEMBER_SET][VALUES][INCLUDED] = [
            {PATH: [filter_value]} for filter_value in filters_values
        ]

        limit = query[OPTIONS][LIMIT]
        if limit is None:
            limit = 1000
            query[OPTIONS][LIMIT] = limit
        else:
            limit = int(limit)

        # Fetching using pagination
        page_num = 0
        all_rows = []
        while True:
            query[OPTIONS][PAGE] = page_num
            result_table = self.query_client.list(query)
            rows = list(result_table.rows())
            all_rows.extend(rows)
            if len(rows) < limit:
                break
            page_num += 1

        logger.info(f"History for {query[SOURCE]} fetched rows: {len(all_rows)}.")
        return all_rows

    def __get_time_interval(self, query: Dict[str, Any]) -> Dict[str, Any]:
        analytic_object_name = query[SOURCE][ANALYTIC_OBJECT]
        analytic_object_response = self.model_client.get_analytic_objects([analytic_object_name])
        analytic_object = json.loads(analytic_object_response.text)[ANALYTIC_OBJECTS][0]
        data_start_date = int(analytic_object[DATA_START_DATE])

        start_date = datetime.utcfromtimestamp(data_start_date / 1000)
        current_date = datetime.utcnow()
        diff_days = (current_date - start_date).days
        return {
            FROM_INSTANT: data_start_date,
            INTERVAL_PERIOD_TYPE: PERIOD_TYPE_DAY,
            INTERVAL_PERIOD_COUNT: diff_days,
            DIRECTION: FORWARD
        }

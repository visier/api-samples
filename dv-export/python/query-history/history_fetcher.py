import json
import logging
from datetime import datetime
from typing import Dict, Any, Set

from visier.api import ModelApiClient, QueryApiClient
from visier.connector import VisierSession, ResultTable

logger = logging.getLogger(__name__)


class HistoryFetcher:
    """Fetches values for all history of subject."""

    def __init__(self, session: VisierSession):
        self.model_client = ModelApiClient(session, raise_on_error=True)
        self.query_client = QueryApiClient(session, raise_on_error=True)

    def list_changes(self, query: Dict[str, Any], filters_values: Set[str]) -> ResultTable:
        """Query list changes for subject using filters_values."""
        logger.info(f"List changes for {query['source']}.")

        query['timeInterval'] = self.__get_time_interval(query)
        # updating filter with values
        query_filter = query['filters'][0]
        query_filter['memberSet']['values']['included'] = [
            {"path": [filter_value]} for filter_value in filters_values
        ]

        result_table = self.query_client.list(query)
        return result_table

    def __get_time_interval(self, query: Dict[str, Any]) -> Dict[str, Any]:
        analytic_object_name = query['source']['analyticObject']
        analytic_object_response = self.model_client.get_analytic_objects([analytic_object_name])
        analytic_object = json.loads(analytic_object_response.text)['analyticObjects'][0]
        data_start_date = int(analytic_object['dataStartDate'])

        start_date = datetime.utcfromtimestamp(data_start_date / 1000)
        current_date = datetime.utcnow()
        diff_days = (current_date - start_date).days
        return {
            "fromInstant": data_start_date,
            "intervalPeriodType": "DAY",
            "intervalPeriodCount": diff_days,
            "direction": "FORWARD"
        }

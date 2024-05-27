import json
from datetime import datetime

from visier.api import ModelApiClient, QueryApiClient
from visier.connector import VisierSession, ResultTable


class HistoryFetcher:
    """Fetches history for Employee."""

    def __init__(self, session: VisierSession):
        self.model_client = ModelApiClient(session, raise_on_error=True)
        self.query_client = QueryApiClient(session, raise_on_error=True)

    def query_changes(self, query, filters_values) -> ResultTable:
        """Query all changes for Employee using Employee IDs and timestamps."""
        query['timeInterval'] = self.__get_time_interval(query)

        # TODO think about how to handle multiple filters
        query_filter = query['filters'][0]
        query_filter['memberSet']['values']['included'] = []
        for filter_value in filters_values:
            query_filter['memberSet']['values']['included'].append({"path": [filter_value]})

        result_table = self.query_client.list(query)
        return result_table

    def __get_time_interval(self, query):
        analytic_object_name = query['source']['analyticObject']
        analytic_object_response = self.model_client.get_analytic_objects([analytic_object_name])
        analytic_object = json.loads(analytic_object_response.text)['analyticObjects'][0]
        data_start_date = int(analytic_object['dataStartDate'])

        start_date = datetime.utcfromtimestamp(data_start_date / 1000)
        current_date = datetime.utcnow()
        diff_days = (current_date - start_date).days
        time_interval = {
            "fromInstant": data_start_date,
            "intervalPeriodType": "DAY",
            "intervalPeriodCount": diff_days,
            "direction": "FORWARD"
        }
        return time_interval

import os
from typing import TypeVar

from visier.api.direct_intake import Configuration
from visier.sdk.api.data_out import DataQueryApi, ApiClient, AggregationQueryExecutionDTO, QueryTimeIntervalsDTO

T = TypeVar('T')


class DataDownloader:
    def __init__(self, storage_path: str, api_config: Configuration):
        self.storage_path = storage_path
        api_client = ApiClient(configuration=api_config)
        self.query_api = DataQueryApi(api_client)

    def _save_data(self, file_path, text):
        if os.path.exists(file_path):
            raise FileExistsError(f"File {file_path} already exists. "
                                  "Couldn't save downloaded data.")
        with open(file_path, mode='w') as f:
            f.write(text)

    def download_data(self, query_file_path: str, date_str: str):
        """Download data snapshot for custom date and saving it to storage."""

        with open(query_file_path, 'rb') as f:
            query_json = f.read()
        query_dto = AggregationQueryExecutionDTO.from_json(query_json)
        query_dto.query.time_intervals = QueryTimeIntervalsDTO(
            from_date_time=date_str
        )

        # query with header to get data in csv format
        response = self.query_api.aggregate_without_preload_content(query_dto, _headers={"Accept": "text/csv"})

        file_prefix, _ = os.path.splitext(os.path.basename(query_file_path))
        storage_file = os.path.join(self.storage_path, f'{file_prefix}_{date_str}.csv')
        self._save_data(storage_file, response.data.decode())

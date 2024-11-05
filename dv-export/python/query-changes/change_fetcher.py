import logging
from typing import List, Tuple

from visier_api_analytic_model import DataModelApi, AnalyticObjectDTO, PropertiesDTO, PropertyDTO
from visier_api_data_out import DataQueryApi, ListQueryExecutionDTO, GoogleProtobufAny

logger = logging.getLogger(__name__)


class ChangeFetcher:
    """Fetches all changes that are defined for a given analytic object."""

    def __init__(self, model_api: DataModelApi, query_api: DataQueryApi):
        self.model_api = model_api
        self.query_api = query_api

    def execute_query_list(self, list_query_dto: ListQueryExecutionDTO) -> List[GoogleProtobufAny]:
        """Execute a query to list changes for a given analytic object."""
        limit = list_query_dto.options.limit
        page_num = 0
        all_rows: List[GoogleProtobufAny] = []
        while True:
            list_query_dto.options.page = page_num
            list_response = self.query_api.list(list_query_dto)
            if list_response is None:
                logger.info(f"No changes found for source: {list_query_dto.source}.")
                return all_rows

            logger.info(f"Batch changes for source: {list_query_dto.source},"
                        f" fetched page: {page_num}, rows: {len(list_response.rows)}.")
            all_rows.extend(list_response.rows)

            # If the number of rows is less than the limit, then we have fetched all changes.
            if len(list_response.rows) < limit:
                break
            page_num += 1
        logger.info(f"Full changes for {list_query_dto.source} fetched rows: {len(all_rows)}.")
        return all_rows

    def get_analytic_object_metadata(self, analytic_object_name: str) -> Tuple[AnalyticObjectDTO, PropertiesDTO]:
        analytic_object_dto = self.model_api.analytic_object(analytic_object_name)
        properties_dto = self.model_api.properties(analytic_object_name)
        return analytic_object_dto, properties_dto

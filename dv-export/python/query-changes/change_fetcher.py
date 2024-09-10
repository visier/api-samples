import copy
import logging
from datetime import datetime
from typing import Optional, Any

import math
from visier_api_analytic_model import DataModelApi, AnalyticObjectDTO, PropertiesDTO, PropertyDTO
from visier_api_data_out import DataQueryApi, ListQueryExecutionDTO, GoogleProtobufAny, ListResponse

from constants import *

logger = logging.getLogger(__name__)


class ChangeFetcher:
    """Fetches all changes that are defined for a given analytic object."""

    DEFAULT_QUERY_LIMIT = 100000

    # Additional properties to fetch for different object types.
    additional_properties = {
        "SUBJECT": [
            PropertyDTO(
                id='ValidityStart',
                displayName='ValidityStart',
                description='Start time of data validity.',
                dataType='Date', primitiveDataType='Date'
            ),
            PropertyDTO(

                id='ValidityEnd',
                displayName='ValidityEnd',
                description='End time of data validity.',
                dataType='Date',
                primitiveDataType='Date'
            ),
        ],
        "EVENT": [
            PropertyDTO(
                id='EventDate',
                displayName='EventDate',
                description='Event occurred time.',
                dataType='Date',
                primitiveDataType='Date'
            )
        ]
    }

    def __init__(self, model_api: DataModelApi, query_api: DataQueryApi):
        self.model_api = model_api
        self.query_api = query_api

    def execute_query_list(self,
                           query_orig: dict[str, Any],
                           start_date_epoch: int,
                           end_data_epoch: int,
                           record_mode: str,
                           filter_values: Optional[set[str]] = None) -> list[GoogleProtobufAny]:
        """Execute a query to list changes for a given analytic object."""
        time_interval = self._get_time_interval(start_date_epoch, end_data_epoch)
        list_query_dto = self._prepare_list_query_dto(query_orig, time_interval, record_mode, filter_values)
        changes = self._fetch_data_with_pagination(list_query_dto)
        return changes

    def get_analytic_object_metadata(self, analytic_object_name: str) -> tuple[AnalyticObjectDTO, PropertiesDTO]:
        analytic_object_dto = self.model_api.analytic_object(analytic_object_name)
        properties_dto = self.model_api.properties(analytic_object_name)
        self._append_additional_properties(properties_dto, analytic_object_dto)
        return analytic_object_dto, properties_dto

    def _prepare_list_query_dto(self,
                                query_orig: dict[str, Any],
                                time_interval: dict[str, Any],
                                record_mode: str = NORMAL,
                                filter_values: Optional[set[str]] = None) -> ListQueryExecutionDTO:
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
        return ListQueryExecutionDTO.from_dict(query)

    def _fetch_data_with_pagination(self, list_query_dto: ListQueryExecutionDTO) -> list[GoogleProtobufAny]:
        limit = list_query_dto.options.limit
        page_num = 0
        all_rows = []
        while True:
            list_query_dto.options.page = page_num
            response = self.query_api.list_with_http_info(list_query_dto)
            # Check if response is 2xx
            if response.status_code < 200 or response.status_code >= 300:
                raise Exception(
                    f"Failed to fetch changes for {list_query_dto.source}: {response.status_code}, {response.data}")

            if response.status_code == 204:
                logger.info(f"No changes found for source: {list_query_dto.source}.")
                return all_rows

            list_response: ListResponse = response.data
            logger.info(f"Batch changes for source: {list_query_dto.source},"
                        f" fetched page: {page_num}, rows: {len(list_response.rows)}.")
            all_rows.extend(list_response.rows)
            # If the number of rows is less than the limit, then we have fetched all changes.
            if len(list_response.rows) < limit:
                break
            page_num += 1
        logger.info(f"Full changes for {list_query_dto.source} fetched rows: {len(all_rows)}.")
        return all_rows

    def _append_additional_properties(self,
                                      properties_dto: PropertiesDTO,
                                      analytic_object_dto: AnalyticObjectDTO) -> None:
        additional_props = self.additional_properties.get(analytic_object_dto.type, [])

        for additional_prop_orig in additional_props:
            additional_prop = additional_prop_orig.model_copy()
            additional_prop.id = f"{analytic_object_dto.id}.{additional_prop.id}"
            properties_dto.properties.append(additional_prop)

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
            FROM_INSTANT: str(end_date_epoch),
            INTERVAL_PERIOD_TYPE: DAY,
            INTERVAL_PERIOD_COUNT: diff_days,
            DIRECTION: BACKWARD
        }

from io import BytesIO

import pandas as pd
from dotenv import dotenv_values
from visier_api_analytic_model import DataModelApi, PropertiesDTO
from visier_api_core import ApiClient, Configuration
from visier_api_data_in import (
    DirectDataIntakeApi,
    DirectDataJobConfigDTO,
    DirectDataLoadConfigDTO,
    DirectDataSchemaFieldDTO,
)
from visier_api_data_out import (
    DataQueryApi,
    ListQueryExecutionDTO,
    ListQueryExecutionOptionsDTO,
    ListQuerySourceDTO,
    PropertyColumnDTO,
    QueryFilterDTO,
    QueryPropertyDTO,
    QueryTimeIntervalDTO,
)

env_creds = dotenv_values()


class VisierApi:
    """
    The VisierApi class facilitates interactions with the Visier API for tasks such as
    composing queries, downloading data, and uploading datasets. It handles API
    configuration, authentication, and data transactions.

    Key features:
    - Compose and execute analytic queries.
    - Download query results as DataFrames.
    - Upload data and manage transactions.

    For more details, refer to the official Visier API documentation: https://docs.visier.com/developer/apis/apis.htm
    """

    def __init__(self):
        self.env_vars = dotenv_values(dotenv_path=".env.ds-round-trip")
        self.configuration = self.__load_api_configuration__(self.env_vars)
        self.client = ApiClient(self.configuration)
        self.client.default_headers["TargetTenantID"] = self.env_vars.get(
            "VISIER_TARGET_TENANT_ID"
        )
        self.DRAFT_ID = "prod"

    def __load_api_configuration__(self, env_vars: dict) -> Configuration:
        return Configuration(
            vanity=env_vars.get("VISIER_VANITY"),
            host=env_vars.get("VISIER_HOST"),
            api_key=env_vars.get("VISIER_APIKEY"),
            username=env_vars.get("VISIER_USERNAME"),
            password=env_vars.get("VISIER_PASSWORD"),
        )

    def compose_list_query_execution_dto(
        self,
        end_time: str,
        analytic_object: str = "Employee",
        columns: list[dict[str, str]] | None = None,
        filters: list[QueryFilterDTO] | None = None,
    ) -> ListQueryExecutionDTO:
        """
        A function that compose a list execution DTO with provided analytic object, columns, and end time.
        Default is getting 1 month of data backward to the end date.
        """
        _columns = []

        if columns is not None:
            _columns = [
                PropertyColumnDTO(
                    column_name=c["displayName"],
                    column_definition=QueryPropertyDTO(formula=c["attribute"]),
                )
                for c in columns
            ]

        return ListQueryExecutionDTO(
            columns=_columns,
            options=ListQueryExecutionOptionsDTO(calendarType="GREGORIAN_CALENDAR"),
            source=ListQuerySourceDTO(analytic_object=analytic_object),
            timeInterval=QueryTimeIntervalDTO(
                fromDateTime=end_time, intervalPeriodType="DAY", intervalPeriodCount=1
            ),
            filters=filters,
        )

    def list_project_schema(
        self, analytic_object: str = "Employee"
    ) -> list[DirectDataSchemaFieldDTO]:
        ddi_client = DirectDataIntakeApi(self.client)
        # TODO: replace it with `object_schema` to deserialize the response body into DTO natively
        response = ddi_client.object_schema_without_preload_content(
            draft_id=self.DRAFT_ID, object_name=analytic_object
        ).json()
        return [
            DirectDataSchemaFieldDTO.from_dict(field) for field in response["schema"]
        ]

    def list_data_model_properties(self, analytic_object: str) -> PropertiesDTO:
        model_api = DataModelApi(self.client)
        return model_api.properties(analytic_object)

    def download_data(self, execution_dto: ListQueryExecutionDTO) -> pd.DataFrame:
        query_api = DataQueryApi(self.client)
        response = query_api.list_without_preload_content(
            execution_dto, _headers={"Accept": "text/csv"}
        )
        if not 200 <= response.status <= 299:
            raise Exception(
                f"API request failed with status code {response.status}: {response.data.decode()}"
            )
        return pd.read_csv(BytesIO(response.data))

    def upload_data(
        self,
        file_path: str = "data/Employee.csv",
        analytic_object_name: str = "Employee",
    ) -> str:
        ddi_client = DirectDataIntakeApi(self.client)
        ddi_client.put_config(
            draft_id=self.DRAFT_ID,
            direct_data_load_config_dto=DirectDataLoadConfigDTO(
                job=DirectDataJobConfigDTO(
                    extendObjects=[analytic_object_name],
                    supplementalMode="IS_SUPPLEMENTAL",
                )
            ),
        )
        tx_id = ddi_client.start_transaction(draft_id=self.DRAFT_ID).transaction_id
        try:
            upload_resp = ddi_client.upload_file(
                draft_id=self.DRAFT_ID,
                transaction_id=tx_id,
                object_name=analytic_object_name,
                file=file_path,
            )

            if upload_resp.status == "SUCCEEDED":
                commit_resp = ddi_client.commit_transaction(
                    draft_id=self.DRAFT_ID, transaction_id=tx_id
                )
                print(
                    f"Transaction status: {commit_resp.status}, message: {commit_resp.message}"
                )
            else:
                raise Exception("failed to upload file")
        except Exception:
            ddi_client.rollback_transaction(
                draft_id=self.DRAFT_ID, transaction_id=tx_id
            )
            print(f"rolled back transaction: {tx_id}")
            raise
        else:
            return tx_id

    def check_status(self, tx_id: str) -> str:
        ddi_client = DirectDataIntakeApi(self.client)
        response = ddi_client.job_status(draft_id=self.DRAFT_ID, transaction_id=tx_id)
        return response.status

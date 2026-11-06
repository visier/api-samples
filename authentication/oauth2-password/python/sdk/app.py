from visier_platform_sdk import DataModelApi

# Alternative way to read config and create api client explicitly:
# ```python
# from visier_platform_sdk import ApiClient
# from visier_platform_sdk.configuration import *
# api_config = Configuration.from_env()
# api_client = ApiClient(api_config)
# data_model_api = DataModelApi(api_client)
# ```

data_model_api = DataModelApi()
members = data_model_api.members("Employee", "Gender")
print(members.model_dump_json(indent=2))

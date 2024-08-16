import os

from visier.sdk.api.data_in import DataUploadApi, ApiClient


class DataUploader:
    def __init__(self, api_config):
        api_client = ApiClient(configuration=api_config)
        self.upload_api = DataUploadApi(api_client)

    def upload_data(self, data_file_path):
        with open(data_file_path, 'rb') as f:
            data = f.read()

        filename = os.path.basename(data_file_path)
        self.upload_api.v1_data_upload_files_filename_put(filename=filename,
                                                          body=data,
                                                          _headers={'Content-Type': 'application/octet-stream'})

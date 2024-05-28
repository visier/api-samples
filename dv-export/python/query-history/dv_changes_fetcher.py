import io
import logging
import time
from typing import List

import pandas as pd
from visier.api import DVExportApiClient
from visier.connector import VisierSession

logger = logging.getLogger(__name__)


class DVChangesFetcher:
    def __init__(self, session: VisierSession,
                 poll_interval_secs: int = 10,
                 export_job_timeout_sec: int = 1200):
        self.dv_client = DVExportApiClient(session, raise_on_error=True)
        self.poll_interval_secs = poll_interval_secs
        self.export_job_timeout_sec = export_job_timeout_sec

    def fetch_subject_property_changes(self,
                                       base_data_version: int,
                                       data_version: int,
                                       export_uuid: str,
                                       subject_name: str,
                                       property_name: str) -> List[str]:
        """Retrieve changes for a subject property between two data versions."""
        logger.info(f"Fetching changes for {subject_name}.{property_name}.")
        if export_uuid is None:
            export_uuid = self.__run_export_job(base_data_version, data_version)
        return self.__read_subject_property(export_uuid, subject_name, property_name)

    def __run_export_job(self, base_data_version: int, end_data_version: int) -> str:
        schedule_response = self.dv_client.schedule_delta_data_version_export_job(end_data_version,
                                                                                  base_data_version).json()
        job_id = schedule_response['jobUuid']
        logger.info(f"DV export job {job_id} was scheduled, base dv {base_data_version}, dv {end_data_version}.")

        start_time = time.time()
        while True:
            logger.info(f"Checking for dv export job {job_id} completion.")
            status_response = self.dv_client.get_data_version_export_job_status(job_id).json()
            if status_response['completed']:
                export_uuid = status_response['exportUuid']
                logger.info(f"Job {job_id} complete with export_uuid={export_uuid}")
                return export_uuid
            else:
                elapsed_time = time.time() - start_time
                if elapsed_time > self.export_job_timeout_sec:
                    raise TimeoutError(f"Job {job_id} timed out after {self.export_job_timeout_sec} seconds.")
                time.sleep(self.poll_interval_secs)

    def __read_subject_property(self, export_uuid: str, subject_name: str, property_name: str) -> List[str]:
        metadata_response = self.dv_client.get_data_version_export_metadata(export_uuid).json()
        table = list(filter(lambda x: x['name'] == subject_name, metadata_response['tables']))
        file_id = table[0]['commonColumns']['files'][0]['fileId']

        logger.info(f"Get exportUuid {export_uuid} fileId {file_id}.")
        get_file_response = self.dv_client.get_export_file(export_uuid, file_id)
        df = pd.read_csv(io.StringIO(get_file_response.content.decode('utf-8')))
        return df[property_name].tolist()
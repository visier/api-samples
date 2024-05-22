import csv
import logging
import time
from collections import OrderedDict

from dotenv import dotenv_values
from sqlalchemy import create_engine, Column, String, Table, MetaData
from sqlalchemy.orm import sessionmaker
from visier.api import DVExportApiClient, QueryApiClient
from visier.connector import make_auth, VisierSession

# Constants
API_BASE_URI = "https://d3m-dsc.api.visierdev.io/v1"
FILE_PATH = "employee.csv"
DB_PATH = "employee_changes.db"

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


def authenticate():
    """Authenticate with Visier and return a session."""
    env_configs = OrderedDict({
        **dotenv_values('.env.dv-export'),
        **dotenv_values('.env.visier-auth')
    })
    auth = make_auth(env_values=env_configs)
    return VisierSession(auth)


def schedule_export_job(session, base_data_version, end_data_version):
    """Schedule a data version export job and wait for it to complete."""
    dv_export_client = DVExportApiClient(session)
    response = dv_export_client.schedule_delta_data_version_export_job(end_data_version, base_data_version)
    job_id = response.json()['jobUuid']
    logger.info(f"DV Export job scheduled with job_id={job_id}")

    while True:
        logger.info(f"Checking for completion of job_id={job_id}")
        poll_response = dv_export_client.get_data_version_export_job_status(job_id)
        poll_response_json = poll_response.json()
        if poll_response_json['completed']:
            export_id = poll_response_json['exportUuid']
            logger.info(f"job_id={job_id} complete with export_id={export_id}")
            return export_id
        else:
            poll_interval = 5
            logger.info(f"Checking job_id={job_id} status in {poll_interval} seconds")
            time.sleep(poll_interval)


def download_csv_file(session, export_id, table_name, file_path):
    """Download a CSV file from the data version export."""
    dv_export_client = DVExportApiClient(session)
    metadata_response = dv_export_client.get_data_version_export_metadata(export_id).json()
    employee = list(filter(lambda x: x['name'] == 'Employee', metadata_response['tables']))
    employee_file_id = employee[0]['commonColumns']['files'][0]['fileId']
    file_response = dv_export_client.get_export_file(export_id, employee_file_id)
    with open(file_path, 'wb') as f:
        f.write(file_response.content)
    logger.info(f"File downloaded to {file_path}")


def read_employee_ids(file_path):
    """Read Employee IDs from the downloaded CSV file."""
    employee_ids = []
    with open(file_path, mode='r') as file:
        csv_reader = csv.DictReader(file)
        for row in csv_reader:
            employee_ids.append(row['EmployeeID'])
    return employee_ids


def get_data_version_info(session, base_data_version, data_version):
    """Get data version info to retrieve timestamps."""
    dv_export_client = DVExportApiClient(session)
    response = dv_export_client.get_data_versions_available_for_export()
    data_versions = response.json()
    base_time, end_time = None, None
    for dv in data_versions['dataVersions']:
        if dv['dataVersion'] == base_data_version:
            base_time = dv['created']
        elif dv['dataVersion'] == data_version:
            end_time = dv['created']
    return base_time, end_time


def query_employee_changes(session, employee_ids, base_time, end_time, batch_size=100):
    """Query all changes for Employee using Employee IDs and timestamps."""
    query_client = QueryApiClient(session)

    def batcher(seq, size):
        for pos in range(0, len(seq), size):
            yield seq[pos:pos + size]

    all_results = []
    for batch in batcher(employee_ids, batch_size):
        employee_ids_str = ', '.join(f'"{id_}"' for id_ in batch)
        query_def = {
            "source": {
                "analyticObject": "Employee",  # Example ID for the source analytic object
                # Add other required fields for ListQuerySourceDTO
            },
            "columns": [
                {
                    "columnName": "EmployeeID",
                    "columnDefinition": {"property": {"name": "Employee.EmployeeID", "qualifyingPath": "Employee"}}
                },
                {
                    "columnName": "First Name",
                    "columnDefinition": {"property": {"name": "Employee.First_Name", "qualifyingPath": "Employee"}}
                },
                {
                    "columnName": "Last Name",
                    "columnDefinition": {"property": {"name": "Employee.Last_Name", "qualifyingPath": "Employee"}}
                },
                {
                    "columnName": "Organization",
                    "columnDefinition": {"property": {"name": "Employee.Organization_ID", "qualifyingPath": "Employee"}}
                }
            ],
            "sortOptions": [
                {
                    "columnIndex": 0,  # Index of the column in the columns array
                    "sortDirection": "SORT_ASCENDING"
                }
            ],
            # "filters": [
            #     {
            #         "memberSet": {
            #             "dimension": {
            #                 "name": "Employee.EmployeeID",
            #                 "qualifyingPath": "Employee"
            #             },
            #             "values": {"included": f'{employee_ids_str}'}  # Replace with actual Employee IDs
            #         }
            #     }
            # ],
            "filters": [{
                "formula": f'include(Employee.EmployeeID, list({employee_ids_str})))'
            }],
            "timeInterval": {
                "fromInstant": base_time,  # Start from the base time
                "intervalPeriodType": "YEAR",  # Interval type is year
                "intervalPeriodCount": 100,  # Last 10 years
                "direction": "FORWARD"  # Query backward from the current date
            }
        }
        result = query_client.list(query_def)
        if result is not None:
            all_results.extend(result.rows())  # Assuming result.rows() returns a list of rows
    logger.info(f"Query completed for {len(all_results)} employees")
    return all_results


def store_changes_in_db(changes):
    """Store the changes in an SQLite database using SQLAlchemy."""
    # SQLAlchemy setup
    engine = create_engine(f'sqlite:///{DB_PATH}')
    Session = sessionmaker(bind=engine)
    metadata = MetaData()

    # Define the EmployeeChanges table
    employee_changes_table = Table('EmployeeChanges', metadata,
                                   Column('EmployeeId', String, primary_key=True),
                                   Column('ChangeType', String),
                                   Column('ChangeTimestamp', String)
                                   )

    # Create the table if it doesn't exist
    metadata.create_all(engine)

    # Store changes in the database
    session = Session()
    for change in changes:
        insert_stmt = employee_changes_table.insert().values(
            EmployeeId=change['EmployeeId'],
            ChangeType=change['ChangeType'],
            ChangeTimestamp=change['ChangeTimestamp']
        )
        session.execute(insert_stmt)
    session.commit()
    session.close()
    logger.info(f"Changes stored in database at {DB_PATH}")


def main(base_data_version, data_version):
    with authenticate() as session:
        # export_id = schedule_export_job(session, base_data_version, data_version)
        export_id = "b6717a50-17be-11ef-9027-6fa2c7d9d5d2"

        # Assuming file_id is known or retrieved from export metadata
        file_id = "Employee"
        download_csv_file(session, export_id, file_id, FILE_PATH)

        employee_ids = read_employee_ids(FILE_PATH)
        base_time, end_time = get_data_version_info(session, base_data_version, data_version)

        changes = query_employee_changes(session, employee_ids, base_time, end_time)
        store_changes_in_db(changes)


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 3:
        logger.error("Usage: python script.py <baseDataVersion> <endDataVersion>")
        sys.exit(1)
    base_data_version = sys.argv[1]
    end_data_version = sys.argv[2]
    main(base_data_version, end_data_version)

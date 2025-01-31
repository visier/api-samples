from typing import Dict

import pandas as pd
import os
from dotenv import load_dotenv
from pandas import DataFrame
import json

from visier_api_core import ApiClient, Configuration
from visier_api_data_in import PlanningDataLoadApi, PlanDataLoadErrorDTO
from visier_api_analytic_model import DataModelApi, PlanSchemaDTO, PlanSegmentLevelMemberDTO, PlanSegmentLevelMemberListDTO

from plan_schema import *

load_dotenv()

PLAN_ID = os.getenv('PLAN_ID')
SCENARIO_ID = os.getenv('SCENARIO_ID')

METHOD = os.getenv('METHOD')
CALCULATION = os.getenv('CALCULATION')

SOURCE_FILENAME = os.getenv('SOURCE_FILENAME')
MAPPED_DATA_LOAD_FILENAME = os.getenv('MAPPED_DATA_LOAD_FILENAME')
MAPPED_ADD_REMOVE_FILENAME = os.getenv('MAPPED_ADD_REMOVE_FILENAME')

MISSING_ROW_RCIS = ['RCIP980022', 'RCIP980021', 'RCIP972046']

config = Configuration.from_env()
api_client = ApiClient(config)
plan_data_load_api = PlanningDataLoadApi()
data_load_api = DataModelApi()


def load_data_into_visier(filename, method, counter) -> DataLoadResult:
    """
    Uses the Planning Data Load API to load data into a plan.
    :returns: the response and any missing row indices.
    """
    print(f"Loading file: {filename} into Visier using calculation={CALCULATION} and method={method}...")
    data = open(filename, 'rb').read()
    dto = plan_data_load_api.plan_data_load_plan_data_upload(
        PLAN_ID,
        SCENARIO_ID,
        calculation=CALCULATION,
        method=method,
        file=data
    )
    load_errors: List[PlanDataLoadErrorDTO] = dto.errors
    invalid_row_messages: List[PlanDataLoadErrorDTO] = []
    missing_row_errors: List[PlanDataLoadErrorDTO] = []
    if load_errors:
        # The source file may load more than one cell for a missing row. We want to log the error only once.
        missing_row_errors = [invalid_row_messages.append(x.error_message) or x for x in load_errors if
                              (x.rci in MISSING_ROW_RCIS and x.error_message not in invalid_row_messages)]
    else:
        if method != "VALIDATE":
            print(f"No errors during data load! Updated {dto.updated_cells_count} cells")

    missing_row_indices: List[int] = list(map(lambda x: x.row, missing_row_errors))
    print(f"Updated cell count: {dto.updated_cells_count}")
    with open(f"DataLoadLog_{counter}_{PLAN_ID}_{SCENARIO_ID}_{method}.json", "w") as file:
        json.dump(dto.to_json(), file, separators=(',', ':'))
        file.close()
    return DataLoadResult(
        dto,
        missing_row_indices
    )


def send_added_rows_to_visier(filename) -> List[PlanSegmentLevelMemberDTO]:
    """
    Uses the Planning Data Load API to add rows to the configured plan.
    """
    print("Adding rows to plan...")
    data = open(filename, 'rb').read()
    response = plan_data_load_api.plan_data_load_plan_row_data_load(
        PLAN_ID,
        method=METHOD,
        file=data
    )
    print(f"Added & removed rows. Added rows: {response.added_rows_count} Removed rows: {response.removed_rows_count}")
    print(f"Errors encountered: {response.errors}")
    return response.custom_members


def add_missing_rows_to_plan(row_indices_to_add: List[int], schema: PlanSchemaDTO, filename: str) -> List[PlanSegmentLevelMemberDTO]:
    """
    Generates a CSV and then uses the Planning Data Load API to add or remove rows.
    Assumes that a mapped file for data loading has already been created.

    :param row_indices_to_add: The row indices in the existing mapped file to add to the plan.
    :param schema: The schema of the plan.
    :param filename: The name of the CSV file to generate.
    :returns: A list of custom members in the plan that you can use to correct the existing mapped file.
    """
    print("Generating the csv for adding missing rows to plan...")
    data_to_upload = retrieve_visier_data_file().to_dict('index')
    new_row_data = []
    for idx in row_indices_to_add:
        dataUploadRowData = data_to_upload[idx]
        rowData = {}
        for segmentLevel in schema.plan_segment_level_members:
            rowData.update(
                {
                    segmentLevel.segment_level_id: dataUploadRowData[segmentLevel.segment_level_id]
                }
            )
        # Adds the value for the Add/Remove column.
        rowData.update({"Add/Remove": "Add"})
        new_row_data.append(rowData)

    write_to_csv(new_row_data, filename)
    return send_added_rows_to_visier(filename)


def get_schema() -> PlanSchemaDTO:
    """
    Retrieves the schema for the `planId` in the configuration.
    :return: The schema of the plan.
    """
    print(f"Fetching plan schema for plan with id: {PLAN_ID}")
    response = data_load_api.plan_info_with_schema(
        PLAN_ID,
        with_schema=True
    )
    print("Successfully retrieved plan details and schema!")
    return response.var_schema


def get_source_data() -> DataFrame:
    """
    Gets data from the source.
    Modify this function to get it to call your database API.
    For now, we are sourcing from a local CSV file.
    :returns: A data frame of the source file
    """
    print(f"Reading file from {SOURCE_FILENAME}...")
    raw_data = pd.read_csv(SOURCE_FILENAME)
    return raw_data


def map_data(source_data: DataFrame, schema: PlanSchemaDTO):
    """
    Maps the source data into a CSV based on the schema of the plan.

    :param source_data: Data from third-party application.
    :param schema: The schema of the plan.
    """
    print("Mapping source data based on plan schema...")
    data = source_data.to_dict('index')
    nested_member_with_level_list = list(map(process_segment_with_members, schema.plan_segment_level_members))
    flattened_member_list = [item for sublist in nested_member_with_level_list for item in sublist]
    transformed_data_by_row = dict(zip(data.keys(), map(lambda v: map_row_data(v, schema, flattened_member_list), data.values())))
    flattened_rows = []
    for row in transformed_data_by_row:
        changes = transformed_data_by_row[row]
        for change in changes:
            flattened_rows.append(change)
    return flattened_rows


def map_row_data(row_data, schema: PlanSchemaDTO, member_list: List[PlanSegmentMemberWithLevelId]) -> List[Dict[str, str]]:
    """
    Transforms the source data to match the plan schema. Change this function to contain mapping logic appropriate for the source data.
    """

    # Hardcoded headers from the source data.
    source_org_key = "Organization Hierarchy"
    source_loc_key = "Location"
    non_time_period_keys = [source_org_key, source_loc_key]

    # Gets the member for the two dimensions provided in the source data.
    source_org_member = row_data[source_org_key]
    source_loc_member = row_data[source_loc_key]
    leaf_members = [source_org_member, source_loc_member]

    # The source data has a column for each time period. We identify the time periods used in the source file and use the `generate_time_lookup` function to transform the time periods into a format that the API accepts.
    time_period_keys_from_source = []
    for key in row_data.keys():
        if key not in non_time_period_keys:
            time_period_keys_from_source.append(key)
    time_period_lookup = generate_time_lookup(time_period_keys_from_source)

    segment_level_keys = list(map(lambda l: l.segment_level_id, schema.plan_segment_level_members))

    all_paths = {}
    for leafMember in leaf_members:
        member_info = next((member for member in member_list if member.display_name == leafMember), None)
        if member_info is None:
            print("Could not find member: " + leafMember)
            # Assume it's the top level of location.
            all_paths.update(
                {
                    'Location.Location_1': leafMember
                }
            )
        else:
            path = parent_path(member_info, member_list)
            all_paths.update(path)

    formatted_visier_data = []
    for timePeriod in time_period_keys_from_source:
        data_for_visier = {
            'periodId': time_period_lookup[timePeriod],
            'Headcount_And_Cost_Planning.Headcount': row_data[timePeriod]
        }

        for segmentLevelId in segment_level_keys:
            if segmentLevelId in all_paths:
                data_for_visier[segmentLevelId] = all_paths[segmentLevelId]
            else:
                data_for_visier[segmentLevelId] = ""

        formatted_visier_data.append(data_for_visier)
    return formatted_visier_data


def generate_time_lookup(source_time_keys: List[str]) -> Dict[str, str]:
    """
    Creates a map from the source's time keys to the plan schema keys by transforming the source's time keys
    to match the keys used by the plan schema. The source data format is MM/YY
    while the plan schema format is YYYY-MM-DD.

    Modify this function if your source's time format is different from the sample file.
    You might need to do a different kind of mapping in this function.
    For example, if your source data can map to the display name of the time period instead of the date,
    you can pass the schema in this function and match it by the time period display name.
    """
    time_key_dict = {}
    for key in source_time_keys:
        month_and_year = key.split('/')
        month = month_and_year[0]
        if len(month) == 1:
            month = f"0{month}"
        schema_key = f"20{month_and_year[1]}-{month}-01"
        time_key_dict[key] = schema_key
    return time_key_dict


def write_to_csv(data: List[Dict], filename: str):
    data_frame = pd.DataFrame.from_records(data)
    data_frame.to_csv(filename, index=False)



def generate_data_upload_csv(filename: str, raw: DataFrame):
    """
    Writes a CSV file for loading the data into Visier.

    :param filename: The name of the CSV file to generate.
    :param raw: The source data as a DataFrame.
    """
    print(f'Generating CSV for data load filename:{filename}')
    schema = get_schema()
    mapped_data = map_data(raw, schema)
    write_to_csv(mapped_data, filename)
    return schema


def update_data_load_file_with_custom_member_id(custom_members: List[PlanSegmentLevelMemberDTO], schema: PlanSchemaDTO):
    """
    Updates the mapped data load file with the IDs of the custom members generated from a call to the Add or remove plan rows endpoint.
    :param custom_members: The list of custom members in the plan.
    :param schema: The schema of the plan.
    """
    print('Updating data load file...')
    mapped_file = pd.read_csv(MAPPED_DATA_LOAD_FILENAME)
    data = mapped_file.to_dict("index")
    segment_headers: List[str] = list(map(lambda segment_levels: segment_levels.segment_level_id, schema.plan_segment_level_members))
    updated_data = []
    for index in data.keys():
        row = data[index]
        for header in segment_headers:
            curr_row_member = row[header]
            maybe_custom_member = next((member for member in custom_members if member.display_name == curr_row_member), None)
            if maybe_custom_member is not None:
                row[header] = maybe_custom_member.id
        updated_data.append(row)
    write_to_csv(updated_data, MAPPED_DATA_LOAD_FILENAME)


def parent_path(member: PlanSegmentMemberWithLevelId, member_list: List[PlanSegmentMemberWithLevelId]) -> Dict[str, str]:
    if member.parent_id:
        parent = member.parent_id
        # Look for the member info for the parent and recurse.
        parent_member_info = next((x for x in member_list if x.id == parent), None)
        if parent_member_info is None:
            return {
                member.segment_id: member.id
            }
        else:
            path = {
                member.segment_id: member.id
            }
            next_parent_paths = parent_path(parent_member_info, member_list)
            path.update(next_parent_paths)
            return path
    else:
        return {
            member.segment_id: member.id
        }


def add_segment_level_id_to_member(member: PlanSegmentLevelMemberDTO, segment_id: str) -> PlanSegmentMemberWithLevelId:
    return PlanSegmentMemberWithLevelId(
        id=member.id,
        displayName=member.display_name,
        segmentId=segment_id,
        isCustom=member.is_custom,
        parentId=member.parent_id,
    )


def process_segment_with_members(segment_member_list: PlanSegmentLevelMemberListDTO) -> List[PlanSegmentMemberWithLevelId]:
    return list(map(lambda member: add_segment_level_id_to_member(member, segment_member_list.segment_level_id), segment_member_list.members))


def retrieve_visier_data_file():
    """
    Retrieves the already mapped file from disk.
    """
    rawData = pd.read_csv(MAPPED_DATA_LOAD_FILENAME)
    return rawData


def main():
    data_load_report_counter = 1
    source_data = get_source_data()
    schema = generate_data_upload_csv(MAPPED_DATA_LOAD_FILENAME, source_data)
    test = load_data_into_visier(MAPPED_DATA_LOAD_FILENAME, "VALIDATE", data_load_report_counter)
    data_load_report_counter = data_load_report_counter + 1

    # If there are missing rows in the plan, the next section uses the Add or remove plan rows endpoint to add them to the plan.
    if test.missing_row_indices:
        custom_members_in_plan = add_missing_rows_to_plan(test.missing_row_indices, schema, MAPPED_ADD_REMOVE_FILENAME)
        if custom_members_in_plan:
            update_data_load_file_with_custom_member_id(custom_members_in_plan, schema)

    # Load the data after rows have been added to the plan and the CSV file has been updated with the IDs of
    # the newly added rows.
    load_data_into_visier(MAPPED_DATA_LOAD_FILENAME, METHOD, data_load_report_counter)


if __name__ == "__main__":
    main()

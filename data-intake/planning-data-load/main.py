from typing import Dict

import requests
import pandas as pd
import os
from dotenv import load_dotenv
from pandas import DataFrame

from planSchema import *

load_dotenv()
API_KEY = os.getenv('VISIER_API')
VISIER_HOST = os.getenv('VISIER_HOST')
BASE_URI = "v1/planning"

PLAN_ID = os.getenv('PLAN_ID')
SCENARIO_ID = os.getenv('SCENARIO_ID')

METHOD = os.getenv('METHOD')
CALCULATION = os.getenv('CALCULATION')

SOURCE_FILENAME = os.getenv('SOURCE_FILENAME')
MAPPED_DATA_LOAD_FILENAME = os.getenv('MAPPED_DATA_LOAD_FILENAME')
MAPPED_ADD_REMOVE_FILENAME = os.getenv('MAPPED_ADD_REMOVE_FILENAME')

MISSING_ROW_RCIS = ['RCIP972016', 'RCIP980022', 'RCIP980021']


# Authenticates using the Visier API
def authenticate():
    print("Authenticating with Visier...")
    url = f"{VISIER_HOST}/v1/admin/visierSecureToken?vanityname={os.getenv('VISIER_VANITY')}"
    payload = {
        'username': os.getenv('VISIER_USERNAME'),
        'password': os.getenv('VISIER_PASSWORD')
    }
    headers = {
        'Content-Type': 'application/x-www-form-urlencoded'
    }

    response = requests.request("POST", url, headers=headers, data=payload)
    if response.status_code != 200:
        print(response.json())
        print("Error encountered. Exiting from script...")
        exit()
    else:
        return response.text


# Uses the Planning Data Load API to load data into a plan.
# Returns the response and any missing row indices.
def load_data_into_visier(filename, method) -> DataLoadResult:
    print(f"Loading file: {filename} into Visier using calculation={CALCULATION} and method={method}...")
    security_token = authenticate()
    url = f"{VISIER_HOST}/{BASE_URI}/data/plans/{PLAN_ID}/scenarios/{SCENARIO_ID}?calculation={CALCULATION}&method={method}"
    headers = {
        'apiKey': API_KEY,
        'Cookie': f"VisierASIDToken={security_token}"
    }
    payload = {}
    files = [
        ('file', (filename, open(filename, 'rb'), 'text/csv'))
    ]
    response = requests.request("PATCH", url, headers=headers, data=payload, files=files)
    if response.status_code != 200:
        print(response.json())

    data_load_response = PlanDataUploadResponse(**response.json())
    load_errors = data_load_response.errors
    invalidRowMessages: List[PlanDataLoadError] = []
    missingRowErrors: List[PlanDataLoadError] = []
    if load_errors:
        # The source file may load more than one cell for a missing row. We want to log the error only once.
        missingRowErrors = [invalidRowMessages.append(x['errorMessage']) or x for x in load_errors if (x['rci'] in MISSING_ROW_RCIS and x['errorMessage'] not in invalidRowMessages)]
    else:
        if method != "VALIDATE":
            print(f"No errors during data load! Updated {data_load_response.updatedCellsCount} cells")

    missing_row_indices: List[int] = list(map(lambda x: x['row'], missingRowErrors))
    return DataLoadResult(
        response=data_load_response,
        missingRowIndices=missing_row_indices
    )


# Uses the Planning data load API to add rows to the configured plan
def send_added_rows_to_visier(filename) -> List[PlanSegmentLevelMember]:
    print("Adding rows to plan...")
    security_token = authenticate()
    url = f"{VISIER_HOST}/{BASE_URI}/data/plans/{PLAN_ID}/rows?method={METHOD}"
    headers = {
        'apiKey': API_KEY,
        'Cookie': f"VisierASIDToken={security_token}"
    }
    payload = {}
    files = [
        ('file', (filename, open(filename, 'rb'), 'text/csv'))
    ]
    response = requests.request("PATCH", url, headers=headers, data=payload, files=files)
    if response.status_code != 200:
        print(response.json())
        print("Error encountered. Exiting from script...")
        exit()
    else:
        plan_load = PlanRowDataLoadResponse(**response.json())
        if plan_load.addedRowsCount > 0:
            print(f"Successfully added {plan_load.addedRowsCount}rows")

        return plan_load.customMembers


# Generates a csv and then uses the Planning Data Load API to add/remove rows.
# It will return a list of custom members in the plan that can be used for correcting the existing mapped file.
# This function assumes that a mapped file for data loading has already been created.
# Parameters:
#    row_indices_to_add - the row indices in the existing mapped file that need to be added to the plan
#    schema - the schema of the plan
#    filename - the filename for the csv that will be generated
def add_missing_rows_to_plan(row_indices_to_add: List[int], schema: PlanSchema, filename: str) -> List[PlanSegmentLevelMember]:
    data_to_upload = retrieve_visier_data_file().to_dict('index')
    new_row_data = []
    for idx in row_indices_to_add:
        dataUploadRowData = data_to_upload[idx]
        rowData = {}
        for segmentLevel in schema.planSegmentLevels:
            rowData.update(
                {
                    segmentLevel['id']: dataUploadRowData[segmentLevel['id']]
                }
            )
        # Adds the value for the Add/Remove column
        rowData.update({"Add/Remove": "Add"})
        new_row_data.append(rowData)

    write_to_csv(new_row_data, filename)
    return send_added_rows_to_visier(filename)


# Retrieves the schema for the planId in the configuration
def get_schema() -> PlanSchema:
    print("Fetching plan schema...")
    security_token = authenticate()
    url = f"{VISIER_HOST}/{BASE_URI}/model/plans/{PLAN_ID}?withSchema=true"
    cookie = f"VisierASIDToken={security_token}"
    headers = {
        'apiKey': API_KEY,
        'Cookie': cookie
    }
    response = requests.request("GET", url, headers=headers)
    json_obj = response.json()
    if response.status_code != 200:
        print(response.json())
        print("Error encountered. Exiting from script...")
        exit()
    else:
        schema_obj = json_obj['schema']
        return PlanSchema(**schema_obj)


# Getting data from source.
# Modify this function to get it to call your database API.
# For now, we are sourcing from a local csv file.
def get_source_data() -> DataFrame:
    print(f"Reading file from ${SOURCE_FILENAME}...")
    rawData = pd.read_csv(SOURCE_FILENAME)
    return rawData


# This function maps the source data into a csv based on the schema of the plan.
def map_data(source_data: DataFrame, schema: PlanSchema):
    print("Mapping source data based on plan schema...")
    data = source_data.to_dict('index')
    nestedMemberWithLevelList = list(map(process_segment_with_members, schema.planSegmentLevelMembers))
    flattenedMemberList = [item for sublist in nestedMemberWithLevelList for item in sublist]
    transformedDataByRow = dict(zip(data.keys(), map(lambda v: map_row_data(v, schema, flattenedMemberList), data.values())))
    flattenedRows = []
    for row in transformedDataByRow:
        changes = transformedDataByRow[row]
        for change in changes:
            flattenedRows.append(change)
    return flattenedRows


# This helper function transforms the source data to match the plan schema.
# Change this function for mapping logic appropriate for the source data
def map_row_data(row_data, schema: PlanSchema, member_list: List[PlanSegmentMemberWithLevelId]) -> List[Dict[str, str]]:
    # hardcoded headers from source data
    source_org_key = "Organization Hierarchy"
    source_loc_key = "Location"
    non_time_period_keys = [source_org_key, source_loc_key]

    # gets the member for the two dimensions provided in the source data
    source_org_member = row_data[source_org_key]
    source_loc_member = row_data[source_loc_key]
    leaf_members = [source_org_member, source_loc_member]

    # the source data has a column for each time period so here we identify
    time_period_keys_from_source = []
    for key in row_data.keys():
        if key not in non_time_period_keys:
            time_period_keys_from_source.append(key)
    timePeriodLookup = generate_time_lookup(time_period_keys_from_source)

    segment_level_keys = list(map(lambda l: l['id'], schema.planSegmentLevels))

    all_paths = {}
    for leafMember in leaf_members:
        memberInfo = next((member for member in member_list if member.displayName == leafMember), None)
        if memberInfo is None:
            print("Could not find member: " + leafMember)
            # Assume it's the top level of location
            all_paths.update(
                {
                    'Visier_Standard_Location.Country': leafMember
                }
            )
        else:
            path = parent_path(memberInfo, member_list)
            all_paths.update(path)

    formatted_visier_data = []
    for timePeriod in time_period_keys_from_source:
        data_for_visier = {
            'periodId': timePeriodLookup[timePeriod],
            'Headcount_And_Cost_Planning.Headcount': row_data[timePeriod]
        }

        for segmentLevelId in segment_level_keys:
            if segmentLevelId in all_paths:
                data_for_visier[segmentLevelId] = all_paths[segmentLevelId]
            else:
                data_for_visier[segmentLevelId] = ""

        formatted_visier_data.append(data_for_visier)
    return formatted_visier_data


# Creates a map from source's time keys to the plan schema keys by transforming the source's time keys
# to match the keys used by the plan schema. The source data was formatted MM/YY
# while the plan schema uses YYYY-MM-DD.
#
# Modify this function if your source's time format is different from the sample file.
# You might need to do a different kind of mapping in this function.
# For example, if your source data can map to the display name of the time period instead of the date,
# you can pass the schema in this function and match it by the time period display name.
def generate_time_lookup(source_time_keys: List[str]) -> Dict[str, str]:
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
    dataFrame = pd.DataFrame.from_records(data)
    dataFrame.to_csv(filename, index=False)


# Writes a csv file for loading the data into Visier
# Parameters:
#    filename - name of the file we will generate
#    raw - the source data as a DataFrame
def generate_data_upload_csv(filename: str, raw: DataFrame):
    print(f'Generating CSV for data load filename:{filename}')
    schema = get_schema()
    mapped_data = map_data(raw, schema)
    write_to_csv(mapped_data, filename)
    return schema

# Updates the mapped data load file with the ids of the custom members generated from a call to the add/remove rows API
def update_data_load_file_with_custom_member_id(custom_members: List[PlanSegmentLevelMember], schema: PlanSchema):
    print('Updating data load file...')
    mapped_file = pd.read_csv(MAPPED_DATA_LOAD_FILENAME)
    data = mapped_file.to_dict("index")
    segment_headers: List[str] = list(map(lambda segment_levels: segment_levels['id'], schema.planSegmentLevels))
    updated_data = []
    for index in data.keys():
        row = data[index]
        for header in segment_headers:
            curr_row_member = row[header]
            maybe_custom_member = next((member for member in custom_members if member['displayName'] == curr_row_member), None)
            if maybe_custom_member is not None:
                row[header] = maybe_custom_member['id']
        updated_data.append(row)
    write_to_csv(updated_data, MAPPED_DATA_LOAD_FILENAME)


def parent_path(member: PlanSegmentMemberWithLevelId, member_list: List[PlanSegmentMemberWithLevelId]) -> Dict[str, str]:
    if member.parentId:
        parent = member.parentId
        # Look for the member info for the parent and recurse
        parentMemberInfo = next((x for x in member_list if x.id == parent), None)
        if parentMemberInfo is None:
            return {
                member.segmentId: member.id
            }
        else:
            path = {
                member.segmentId: member.id
            }
            next_parent_paths = parent_path(parentMemberInfo, member_list)
            path.update(next_parent_paths)
            return path
    else:
        return {
            member.segmentId: member.id
        }


def add_segment_level_id_to_member(member, segment_id: str) -> PlanSegmentMemberWithLevelId:
    return PlanSegmentMemberWithLevelId(
        id=member['id'],
        displayName=member['displayName'],
        segmentId=segment_id,
        isCustom=member.get('isCustom', False),
        parentId=member.get('parentId', None),
    )


def process_segment_with_members(segment_member_list: PlanSegmentLevelMemberList) -> List[PlanSegmentMemberWithLevelId]:
    return list(map(lambda member: add_segment_level_id_to_member(member, segment_member_list['segmentLevelId']), segment_member_list['members']))


# Retrieves the already mapped file from disk
def retrieve_visier_data_file():
    rawData = pd.read_csv(MAPPED_DATA_LOAD_FILENAME)
    return rawData


def main():
    sourceData = get_source_data()
    schema = generate_data_upload_csv(MAPPED_DATA_LOAD_FILENAME, sourceData)
    test = load_data_into_visier(MAPPED_DATA_LOAD_FILENAME, "VALIDATE")

    # If there are missing rows in the plan, the next section uses the Add/Remove API to add them to the plan
    if test.missingRowIndices:
        custom_members_in_plan = add_missing_rows_to_plan(test.missingRowIndices, schema, MAPPED_ADD_REMOVE_FILENAME)
        if custom_members_in_plan:
            update_data_load_file_with_custom_member_id(custom_members_in_plan, schema)

    # Load the data after rows have been added to the plan and the csv file has been updated with the ids of
    # the newly added rows.
    load_data_into_visier(MAPPED_DATA_LOAD_FILENAME, METHOD)


if __name__ == "__main__":
    main()

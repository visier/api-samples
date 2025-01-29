# Planning Data Load

This is a sample script that pulls data from a source file and loads it into a specific plan and scenario using the [Planning Data Load API](https://docs.visier.com/visier-people/Default.htm#cshid=1053). In this example, the source file is `source.csv`.

# Getting Started

## Environment
Python 3.x installed on your system and have installed all dependencies:
- `pandas`
- `os`
- `visier_api_core`
- `visier-api-analytic-model`
- `visier-api-data-in`

You can install them using pip and the provided `requirements.txt`.

## Configuration
Configure the `.env` file.

Use the following properties for authentication. The `authenticate` function requests a security token from Visier. You may modify this function if you want to use a different authentication method. For more authentication options, see [API Authentication](https://docs.visier.com/visier-people/Default.htm#cshid=1054).
```
VISIER_HOST=https://customer-specific.ai.visier.io
VISIER_API='visier-provided-api-key'
VISIER_USERNAME='visier-username'
VISIER_PASSWORD='visier-password'
VISIER_VANITY='visier-tenant-vanity-name
```

Use the following properties to specify the plan and scenario you want to modify and load data into. The user must have edit access to the plan. If the user is not the owner of the plan, see [How to Share Your Plan](https://docs.visier.com/visier-people/Planning/plan%20sharing/plan%20sharing.htm).
```
PLAN_ID='plan-id'
SCENARIO_ID='scenario-id'
METHOD='loading-method'
CALCULATION='calculation-method'
```
The `METHOD` query parameter determines if the CSV data is loaded into the plan. Use one of the following values for `METHOD`.
- `VALIDATE`: Does not load data into the plan. The response tells you the number of cells that will change and the number of rows that will be added or deleted as a result of the data load.
- `SKIP_ERRORS`: Loads all data without errors into the plan. Any rows with errors are excluded from the update to the plan. The data load fails if the CSV has formatting errors such as missing or duplicate columns.
- `STRICT_UPLOAD`: Loads data into the plan if there are no errors in any row. If there are errors, the load fails. This is the default.

The `CALCULATION` query parameter determines whether the values roll up to the parent value, distribute among child values, or neither. Use one of the following values for `CALCULATION`.
- `ROLLUP`: Roll up children data values to parent data values. If the data provides a parent value and its child value, this method prioritizes the loaded value for the child and and overwrites the parent.
- `DISTRIBUTE`: Distribute parent data values to their children. If the value of the child conflicts with the calculated distribution, this method overrides the loaded child value.
- `NONE`: The loaded values are neither rolled up or distributed. This is the default.

Use the following properties to specify the filenames for the source file and the CSVs that the script will generate for the data load. You may not need to use `SOURCE_FILENAME` if you aren't loading data from a CSV.
```
SOURCE_FILENAME='source-filename'
MAPPED_DATA_LOAD_FILENAME='mapped-source-file-data-load'
MAPPED_ADD_REMOVE_FILENAME='mapped-file-add-rows'
```

# Usage
This script uploads data from a source file into a plan in Visier. The script first attempts a data load using the `VALIDATE` method to identify any errors. This script only handles missing rows. To handle other errors in the script, modify `load_data_into_visier`. If your source file contains rows that are not present in the plan, the script adds these rows to the plan and then loads the data.

You must adjust the following script functions before using the script to load data into a plan.
- `get_source_data`: Hardcoded to look at the `source.csv` sample. Modify this function to fetch data from a different application.
- `map_data`: Logic is based on the sample source data. Change the logic in this function to match the logic of your source file. Also contains helper functions that you must change, such as `map_row_data` and `generate_time_lookup`.








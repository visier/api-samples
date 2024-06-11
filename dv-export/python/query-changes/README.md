# Data Version Query History

The Data Version (DV) Query History sample application uses Visier APIs to fetch and analyze changes in your Visier tenant.

## Overview

Let’s say we want to maintain a database that restates all changes every time an analytic object changes in Visier. We can use the Data Version Export APIs to retrieve the changes between two data versions in a Visier tenant, which allows us to identify objects that changed and the changes that occurred. However, the DV Export API doesn't retrieve changes to calculated fields, like calculated properties. To get the full change history of all attributes including calculated fields, we can use the Data Query APIs to retrieve specific attributes with their full history that weren't retrieved by the DV Export API. After we have all attributes using both APIs, we can then create a table that saves all received data in a database. 

The application performs the following operations:

1. **Load data version changes**: The application uses `DVExportApiClient` to run an export job to retrieve the delta (differences) between two data versions in the `DVManager` class. The application waits for the job to complete. After the job completes successfully, the application downloads a file containing the changes to a specific analytic object (new columns, deleted columns, updated columns).

2. **Select analytic object attributes**: The application selects attributes from the downloaded export file to include in a list query as a filter. 
The filter should be a dimension of the analytic object and should be set in the query file as a memberSet filter using the placeholder `${{DimensionName}}`. 
The application will replace this placeholder with the actual values from the data version export files.
E.g., the `employee.json` query file contains a filter for the `EmployeeID_Hierarchy` dimension with the placeholder `${{EmployeeID}}`: 
    ```json
      "filters": [
        {
          "memberSet": {
            "dimension": {
              "name": "EmployeeID_Hierarchy",
              "qualifyingPath": "Employee"
            },
            "values": {
              "included": "${{EmployeeID}}"
            }
          }
        }
      ]
    ```

3. **Load history for analytic objects**: The application uses the Data Query API to fetch all changes by filtering by the selected attributes.

4. **Save history in database**: The application creates a table and saves all received data in a database. If the table already exists, the applications drops and recreates the table.

## Usage

The application configuration is stored in the `.env.visier-auth` and `.env.query-changes` files.

Command-line arguments include:

- `-l` or `--list_data_versions`: List available data versions for export in the tenant. If passed, the application will
  list available data versions and exit.
- `-b` or `--base_data_version`: The baseline data version number to use to generate a delta export.
- `-d` or `--data_version`: The data version number the script should export.
- `-e` or `--export_uuid`: An optional UUID of the data version export to download files from. If provided, a DV export job isn't scheduled. You can find `export_uuid` in logs after first run a DV export job.
- `-m` or `--mode`: Specifies the query mode. Use `restate` to fetch the full history, or `last` to fetch only the most recent change for data version."
- `-q` or `--query`: An argument that specifies the location of your query files. The query can be a path to a directory or to a specific query.json file. If you provide a directory path, all *.json files in the directory are treated as query files and are processed individually. The application uses the queries to list changes through the Data Query API (`/v1/data/query/list`). A query must contain a filter for changes between data versions. Use the `memberSet` include filter with the `{{PropertyName}}` placeholder. The placeholder is replaced by actual values from the DV export files. For examples, see the `queries` path. For more information about list queries, see [Data Query API Reference](https://docs.visier.com/developer/apis/data-model-query/swagger/current/index.html#/Query/Query_List:~:text=Query%20a%20list%20of%20details).

Command-line argument examples:
- `-b 7000005 -d 7000006 -m restate -q queries/employee.json`: Fetches the full history (restate) for the Employee if the EmployeeID is among the changed values between data versions `7000005` and `7000006`.
- `-e 92edafd0-22aa-11ef-9027-6fa2c7d9d5d2 -m last -q queries/productivity.json`: Fetch the last changes for the `Productivity` analytic object if the `EmployeeID` is among the changed values between data versions, using the existing export with the UUID `92edafd0-22aa-11ef-9027-6fa2c7d9d5d2`.
- `-e 92edafd0-22aa-11ef-9027-6fa2c7d9d5d2 -m restate -q queries`: Fetch the full history (restate) for all queries in the `queries` directory using the existing export with the UUID `92edafd0-22aa-11ef-9027-6fa2c7d9d5d2`.

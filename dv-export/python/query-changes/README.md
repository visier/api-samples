# Query Data Version Changes

The Query Data Version (DV) Changes sample application uses Visier APIs to fetch and analyze changes in your Visier tenant.

## Overview

Let’s say we want to maintain a database that restates all changes every time an analytic object changes in Visier. We can use the Data Version Export APIs to retrieve the changes between two data versions in a Visier tenant, which allows us to identify objects that changed and the changes that occurred. However, the DV Export API doesn't retrieve changes to calculated fields, like calculated properties. To get the full change history of all attributes including calculated fields, we can use the Data Query APIs to retrieve specific attributes with their full history that weren't retrieved by the DV Export API. After we have all attributes using both APIs, we can then create a table that saves all received data in a database. 

Diagram of the application flow:
<img src="/assets/images/data-version-query-history.png" alt="Data Version Query History Diagram" width="700"/>

The application performs the following operations:
1. **Load data version changes**: The application uses `DVExportApiClient` to run an export job to retrieve the delta (differences) between two data versions in the `DVManager` class. The application waits for the job to complete. After the job completes successfully, the application downloads a file containing the changes to a specific analytic object (new columns, deleted columns, updated columns).

2. **Select analytic object attributes**: The application selects attributes from the downloaded export file to include in a list query as a filter. 
The filter must be a dimension on the analytic object. Set the filter in the `memberSet` with the placeholder `${{DimensionName}}`. The sample application replaces the placeholder with the actual value from the DV export files. For example, the `employee.json` query file contains a filter for the `EmployeeID_Hierarchy` dimension with the placeholder `${{EmployeeID}}`: 
    ```json:
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

3. **Load history for analytic objects**: The application uses the Data Query API to fetch changes by filtering by the selected attributes. 
In `restate` mode, it fetches the full change event history for each entity instance that has changed.
In `last` mode, it fetches the last state for each entity instance that has changed.

4. **Save history in database**: The application saves the fetched data in a database.

## Usage

The application stores its configuration in these files:

`.env.visier-auth`: Contains the Visier authentication parameters.

`.env.query-changes`: Contains the query changes script parameters.

Command-line arguments include:

- `-l` or `--list_data_versions`: List available data versions for export in the tenant. If passed, the application will
  list available data versions and exit.
- `-b` or `--base_data_version`: The baseline data version number to use to generate a delta export.
- `-d` or `--data_version`: The data version number the script should export.
- `-e` or `--export_uuid`: An optional UUID of the data version export to download files from. If provided, a DV export job isn't scheduled. You can find `export_uuid` in logs after first run a DV export job.
- `-m` or `--mode`: Specifies the query mode. Use `restate` to fetch the full history or `last` to fetch only the most recent change for data version.
- `-q` or `--query`: An argument that specifies the location of your query files. The query can be a path to a directory or to a specific query.json file. If you provide a directory path, all *.json files in the directory are treated as query files and are processed individually. The application uses the queries to list changes through the Data Query API (`/v1/data/query/list`). A query must contain a filter for changes between data versions. Use the `memberSet` include filter with the `{{PropertyName}}` placeholder.
This placeholder is replaced with actual values from the DV export files. For examples, see the `queries` path. For more information about list queries, see [Data Query API Reference](https://docs.visier.com/developer/apis/data-model-query/swagger/current/index.html#/Query/Query_List:~:text=Query%20a%20list%20of%20details).

Command-line argument examples:
- `-b 7000005 -d 7000006 -m restate -q queries/employee.json`: Fetches the full history (data restatement) for Employee if EmployeeID is among the changed values between data versions `7000005` and `7000006`.
- `-e 92edafd0-22aa-11ef-9027-6fa2c7d9d5d2 -m last -q queries/productivity.json`: Fetches the most recent changes for Productivity if EmployeeID is among the changed values between data versions using the export with UUID `92edafd0-22aa-11ef-9027-6fa2c7d9d5d2`.
- `-e 92edafd0-22aa-11ef-9027-6fa2c7d9d5d2 -m restate -q queries`: Fetches the full history (data restatement) for all queries in the `queries` directory using the export with UUID `92edafd0-22aa-11ef-9027-6fa2c7d9d5d2`.

## Data Samples

Let's consider the timeline for the `Employee` object and the `DataVersion`.

`V#`: Represents different versions of `Employee` data, indicating changes to employees over time.

`DV#`: Represents different data versions in Visier.

```plaintext
Employee1:   --V1------------V2---------------------------------->
Employee2:   --V1---------------V2------------------------------->
Employee3:   --V1----------------------------------V2------------>
DataVersion: --------DV1----------------DV2---------------DV3---->
```

We can represent the same data in a table with dates:

| Date       | Employee1 | Employee2 | Employee3 | DataVersion |
|------------|-----------|-----------|-----------|-------------|
| 2024-01-20 | V1        | V1        | V1        | V1          |
| 2024-02-01 |           |           |           | DV1         |
| 2024-02-10 | V2        |           |           |             |
| 2024-02-20 |           | V2        |           |             |
| 2024-03-01 |           |           |           | DV2         |
| 2024-03-20 |           |           | V2        |             |
| 2024-04-01 |           |           |           | DV3         |

### Restate Mode Example

Use `restate` mode to identify records that changed between two data versions and then fetch the full history for each record that changed. You may get a different result depending when you run the sample application.

#### Example: Run the Application on 2024-03-02

On 2024-03-02, the data looks like:

```plaintext
Employee1:   --V1------------V2-------------->
Employee2:   --V1---------------V2----------->
Employee3:   --V1---------------------------->
DataVersion: --------DV1----------------DV2-->
```

Command: `-b DV1 -d DV2 -m restate -q queries/employee.json`.

Between `DV1` and `DV2`, `Employee1` and `Employee2` both changed. The application fetches the full history for each record, as shown next.

| Date       | Employee1 | Employee2 |
|------------|-----------|-----------|
| 2024-01-20 | V1        | V1        |
| 2024-02-01 |           |           |
| 2024-02-10 | V2        |           |
| 2024-02-20 |           | V2        |

Before populating the table, the application removes all previous values for `Employee1` and `Employee2`.

### Last Mode Example

Use `last` mode to identify records that changed between two data versions and then fetch the most recent change that occurred for each record. In `last` mode, the application appends data to the table without restating the full history. The results are consistent regardless of when you run the sample application.

#### Example: Run the Application with DV1 and DV2

Command: `-b DV2 -d DV3 -m last -q queries/employee.json`.

Between DV1 and DV2, only `Employee3` changed. The application fetches the most recent change for `Employee3`, as shown next.

| Date       | Employee3 |
|------------|-----------|
| 2024-03-20 | V2        |

The application appends the most recent change for `Employee3` to the table.

# DV Query History

DV Query History is a sample application that demonstrates the use of Visier APIs to fetch and analyze changes in your
Visier tenant.

## Overview

The application performs the following operations:

1. **Load Data Version Changes**: The application runs an export job to get changes between two data versions inside
   the `DVManager` class.
   It uses the `DVExportApiClient` to schedule a data version export job and waits for it to complete.
   Once the job is complete, it downloads file with changes for a specific analytic object.

2. **Get Analytic Object Filter Property**: From the downloaded file, the application selects the filter property from
   the query template and reduces repeated values.

3. **Load History for Analytic Objects**: Using Query API with query template the application fetches all changes using
   filtering by property.

4. **Save History in Database**: The application creates a table and saves all received data in a database. If the table
   already exists, it will be dropped and recreated.

## Usage

The configuration of the application is stored in the `.env.visier-auth` and `.env.visier-auth` files.

Command-line arguments include:

- `-l` or `--list_data_versions`: List available data versions for export in the tenant. If passed, the application will
  list available data versions and exit.
- `-b` or `--base_data_version`: The base data version number to compute a diff from.
- `-d` or `--data_version`: The data version number the script should export.
- `-e` or `--export_uuid`: An optional export UUID to retrieve exported data by. If provided, a DV export job will not
  be scheduled and files will be downloaded from the existing export.
- `-q` or `--query`: File path to the query body for listing changes using the Query API (`/v1/data/query/list`).
  It should include a filter for changes between data versions.
  Use the memberSet include filter with the {{PropertyName}} placeholder, which will be replaced with actual values from
  the data version export files.
  Examples are in the `queries` path. More details are in
  the [Visier API documentation](https://docs.visier.com/developer/apis/data-model-query/swagger/current/index.html#/Query/Query_List:~:text=Query%20a%20list%20of%20details).

Examples of command-line arguments:
1. `-b 7000005 -d 7000006 -q queries/employee.json`  - export employee changes for the applicant object between data versions `7000005` and `7000006` 
2. `-e 92edafd0-22aa-11ef-9027-6fa2c7d9d5d2 -q queries/productivity.json` - export productivity changes for the productivity object using the existing export with the UUID `92edafd0-22aa-11ef-9027-6fa2c7d9d5d2`.  
export_uuid could be found in logs after running the export job.  

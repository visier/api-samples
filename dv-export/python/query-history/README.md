# DV Query History

DV Query History is a sample application that demonstrates the use of Visier APIs to fetch and analyze data version changes in your Visier tenant.

## Overview

The application performs the following operations:

1. **Load Data Version Changes**: The application fetches the changes between two data versions using the `DVChangesFetcher` class. This class uses the `DVExportApiClient` to schedule a data version export job and waits for it to complete. Once the job is complete, it retrieves the changes for a specific subject property between the two data versions.

2. **Get Analytic Object ID**: From the fetched data version changes, the application identifies the IDs of the analytic objects that have been changed.

3. **Load History for Analytic Objects**: Using the identified analytic object IDs, the application then fetches the entire history for these objects. This allows you to track the changes made to these objects over time.

4. **Save History in Database**: The application saves the fetched history from scratch in a database every time it runs. This ensures that full history are always available for analysis.

## Usage

The application is configured through command-line arguments and a `.env` files.

Command-line arguments are parsed in `main.py` using the `argparse` library. The arguments include:

- `-d` or `--data_version`: The data version number the script should export.
- `-b` or `--base_data_version`: The base data version number to compute a diff from.
- `-e` or `--export_uuid`: An optional export UUID to retrieve export metadata for. If provided, a DV export job will not be scheduled.

#TODO add information about query
# Snapshot Recorder Sample Application

## Overview

Organizations frequently report HR metrics to external stakeholders and use them for internal scorecarding.
However, subsequent corrections to historical data can introduce discrepancies between the initially reported values and
the current ones.

This sample application addresses the challenge of maintaining data integrity for accurate historical reporting and analysis.
It provides a solution to preserve original metric values, ensuring consistency and avoiding issues caused
by data corrections at a specific point in time.

The two sample queries in this application highlight the different aggregation semantics for event-based metrics like `resignationCount` and subject-based metrics like `employeeCount`. The snapshot overlays compute values based on whether the snapshot values are
cumulative (event-based) or not cumulative (subject-based).

## Solution

The sample application comprises two steps:

1. Downloading the current data state:
    - Use the Data Query API to download the current data state and save it in temporary CSV files.
    - Two aggregate queries stored in JSON files are required for this step. Sample queries are located in
      [./queries/event-metrics.json](queries%2Fevent-metrics.json) and
      [./queries/subject-metrics.json](queries%2Fsubject-metrics.json).

2. Uploading the CSV files using Data Upload API:
    - Use the Data Upload API to upload the CSV files.
    - The Visier platform maps the data to a pre-created overlays, which will be used to access data as it was at a
      specific point in time.

## Usage

To save data periodically, this application should be run using scheduling software like `cron`.
Both sample queries
[./queries/event-metrics.json](queries%2Fevent-metrics.json) and [./queries/subject-metrics.json](queries%2Fsubject-metrics.json)
fetch data for the last completed month.
This means that the sample should be run once a month. If it is necessary this interval could be changed.

```json
"timeIntervals": {
"dynamicDateFrom": "COMPLETE_PERIOD",
"intervalPeriodType": "MONTH",
"intervalCount": 1
}
```

When run every month, this sample will upload the state of the data to the pre-created overlay.
The overlay retains all the uploaded snapshots which will enable historical analysis of the data as it was known at the time.
The `EventDate` in either overlay will be the last day of the completed period.

### Prerequisites

Ensure that the user has the required permissions to access both the Data Query API and the Data Upload API, as well as
to authenticate using the method you configured.
To process the uploaded files, the Visier platform requires the creation of sources, overlays, and mappings.
To analyze the data, metrics should be created.

Here are the instructions:

1. [Source creation](https://docs.visier.com/developer/Studio/data/sources/source-create.htm)
2. [Overlay creation](https://docs.visier.com/developer/Analytic%20Model/analytic-objects/overlays/overlays-configure.htm)
3. [Mapping from source to overlay](https://docs.visier.com/developer/Studio/data/mappings/mapping-add.htm)
4. [Metrics creation](https://docs.visier.com/developer/Analytic%20Model/metrics/metrics-create.htm)

Instead of manually creating the sources, overlays, mappings, and metrics, you can import these pre-configured components from the
provided files:

1. [WFF_sourcea.zip](import%2FWFF_sources.zip) -
   to [import](https://docs.visier.com/developer/Studio/data/sources/sources-import-export.htm) sources.
2. [WFF_overlay_mapping_metrics.zip](import%2FWFF_overlay_mapping_metrics.zip) -
   to [import](https://docs.visier.com/developer/Studio/projects/projects-import-export.htm) overlays, mappings, metrics.

Python 3.8 or higher is required to run this sample application.

### Setup

1. Clone the repository to your local machine.
   ```shell
   git clone https://github.com/visier/api-samples
   ```
2. Go to the snapshot-recorder folder and install the required packages:
   ```shell
   cd snapshot-recorder
   pip install -r requirements.txt
   ```
3. Configure authentication within the  [.env.snapshot-recorder](.env.snapshot-recorder) file as instructed. Ensure the provided
   credentials have the necessary permissions to utilize both the Data Query API and the Data Upload API.

### Running the script

```shell
python3 main.py -q ./queries/event-metrics.json
python3 main.py -q ./queries/subject-metrics.json
```

The script generates temporary data files, which are removed by default. You can preserve them by setting
`KEEP_TEMP_FILE=True` in your `.env` file.

Ensure that the Data Category release behavior is set to use the latest data version.
After uploading the file, you need to [run a job](https://docs.visier.com/developer/Studio/data/jobs/jobs-run.htm) to
generate a new Data Version.

### MacOS `venv` Troubleshooting Tip:

There is a known issue with SSL certificates when running Python apps in `venv` on MacOS.
To fix it install `certifi` package and add `SSL_CERT_FILE` to the [.env.snapshot-recorder](.env.snapshot-recorder).
Replace {PYTHON_VERSION} with the version you are using.

```shell
pip install certifi
```

```
SSL_CERT_FILE='../.venv/lib/python{PYTHON_VERSION}/site-packages/certifi/cacert.pem'
```

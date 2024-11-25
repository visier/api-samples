# Snapshot Recorder Sample Application

## Overview

Organizations frequently report HR metrics to external stakeholders and use them for internal scorecarding.
However, subsequent corrections to historical data can introduce discrepancies between the initially reported values and
the current ones.

This sample application addresses the challenge of maintaining data integrity for accurate historical reporting and analysis.
It provides a solution to preserve original metric values, ensuring consistency and avoiding issues caused
by data corrections at a specific point in time.

There are two sample queries included in this sample to highlight that Event-based metrics (like `resignationCount`) have
different aggregation semantics than Subject-based ones (like `employeeCount`). This distinction is reflected also in the
target objects; the Snapshot Overlays, which will compute values based on whether the values contained within are
cumulative (Event-based) or not (Subject-based).

## Solution

The sample application comprises two steps:

1. Downloading the current data state:
    - Use the Data Query API to download the current data state and save it in temporary CSV files.
    - Two aggregate queries stored in JSON files arerequired for this step. Sample queries are located in
      [./queries/gender-resignation-joblevel.json](queries%2Fgender-resignation-joblevel.json) and
      [./queries/gender-headcount-joblevel.json](queries%2Fgender-headcount-joblevel.json).

2. Uploading the csv files using Data Upload API:
    - Use the Data Upload API to upload the CSV files.
    - The Visier platform maps the data to a pre-created Overlays, which will be used to access data as it was at a
      specific point in time.

## Usage

To save data periodically, this application should be run using scheduling software like `cron`.
Both sample queries
[./queries/gender-resignation-joblevel.json](queries%2Fgender-resignation-joblevel.json) and 
[./queries/gender-headcount-joblevel.json](queries%2Fgender-headcount-joblevel.json) fetch data for the last completed month.
This means that the sample should be run once a month. If it is necessary this interval could be changed.

```json
"timeIntervals": {
"dynamicDateFrom": "COMPLETE_PERIOD",
"intervalPeriodType": "MONTH",
"intervalCount": 1
}
```

When run every month, this sample will upload the state of the data to the pre-created Overlay.
The Overlay retains all the uploaded snapshots which will enable historical analysis of the data as it was known at the time.
The `EventDate` in either Overlay will be the last day of the completed period.

### Prerequisites

Ensure that the user has the required permissions to access both the Data Query API and the Data Upload API, as well as
to authenticate using the method you configured.
To process the uploaded files, the Visier Platform requires the creation of Sources, Overlays, and Mappings.
To analyze the data, metrics should be created.

Here are the instructions:

1. [Source creation](https://docs.visier.com/developer/Studio/data/sources/source-create.htm)
2. [Overlay creation](https://docs.visier.com/developer/Analytic%20Model/analytic-objects/overlays/overlays-configure.htm)
3. [Mapping from Source to Overlay](https://docs.visier.com/developer/Studio/data/mappings/mapping-add.htm)
4. [Metrics creation](https://docs.visier.com/developer/Analytic%20Model/metrics/metrics-create.htm)

Instead of manually creating the sources, overlays, mappings, and metrics, you can import these pre-configured components from the
provided files:

1. [WFF_source.zip](import%2FWFF_source.zip) -
   to [import](https://docs.visier.com/developer/Studio/data/sources/sources-import-export.htm) source.
2. [WFF_overlay_mapping_metrics.zip](import%2FWFF_overlay_mapping_metrics.zip) -
   to [import](https://docs.visier.com/developer/Studio/projects/projects-import-export.htm) overlay, mapping, metrics.

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
python3 main.py -q ./queries/gender-resignation-joblevel.json
python3 main.py -q ./queries/gender-headcount-joblevel.json
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

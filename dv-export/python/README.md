# DV Export Script
This script provides an example for using the Visier Data Version Export API through the
[Visier Python Connector](https://github.com/visier/connector-python) to export and process data versions from Visier.

## Getting Started
### Environment
Python 3.x installed on your system.

You have cloned the repository.

Installed dependencies: `dotenv`, `visier-connector`, `pandas`, and `sqlalchemy`. You can install them using `pip` and the provided `requirements.txt`:
```
# cd into ../dv-export/python working directory
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

Configured the .env file. The provided .env file contains parameters specific to the script as well as auth variables for the Visier Python Connector.

### Visier user configuration
See https://github.com/visier/connector-python for more details on authentication through the Visier Python Connector.

In addition to the capabilities mentioned above, the user will need the `Manage Jobs` capability to be able to schedule DV export jobs. 
The user will also need read access to data. The user will need a profile which grants them API level access to the 
`Data` and `Model` capabilities.

### Usage
To use the script, you primarily interact with `main.py`. Here's a brief overview of its functionality:
- It configures logging settings.
- Loads environment variables from the .env file. 
- Authenticates with Visier using the provided credentials through the Visier Python Connector
- Initiates a `DV Export` session.
- Processes metadata for data version exports, either initial or delta, based on the provided parameters.

Run the script with `python3 main.py`. For easy testing, use a local `SQLite` database file by providing a `DB_URL` like
`sqlite:///visier-export-test-database.db` in the .env file. `SQLAlchemy` will create a `.db` file in the local working
directory which you can then interact with. 

Once you have run a successful DV export job, save the export UUID and provide it in the .env file as `EXPORT_UUID`.
The export ID is logged multiple times throughout the script to both the `stdout` as well as a local `app.log` file.
This will make the script retrieve the existing export metadata instead of running a new DV export job. This is useful for
quick testing, as there is a limit to the number of DV export jobs you can run in a day and a DV export job can take some time.

## Components
`main.py`

This is the entry point of the script. It orchestrates the export process, including authentication, export job scheduling, metadata retrieval, and file cleanup.

`dv_export.py`

This module contains the `DVExport` class, responsible for interacting with the DV Export API client and the output data store. It schedules export jobs, retrieves metadata, manages file downloads, and copies data to the data store.

`dv_export_model.py`

Defines data classes and helper functions related to data export and processing. It includes classes for file and column information, as well as functions for extracting metadata.

`data_store.py`

Defines an abstract class `DataStore` and its `SQLAlchemy` implementation `SQLAlchemyDataStore`. These classes handle database interactions, including table creation, data insertion, and table dropping.

## Extending Functionality
You can extend the script's functionality by:
 - Modifying `main.py` to customize export parameters or integrate with other systems.
 - Expanding `dv_export.py` to add more API interaction methods or handle additional export scenarios.
 - Enhancing `data_store.py` to support other database systems or add more data manipulation features.

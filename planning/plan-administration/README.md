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

Use the following properties for authentication. This script authenticates using the [Visier Python SDKs](https://github.com/visier/python-sdk). For more authentication options, see [API Authentication](https://docs.visier.com/visier-people/Default.htm#cshid=1054).
```
VISIER_HOST=https://customer-specific.ai.visier.io
VISIER_API='visier-provided-api-key'
VISIER_USERNAME='visier-username'
VISIER_PASSWORD='visier-password'
VISIER_VANITY='visier-tenant-vanity-name
```

Use the following properties to specify the plan you want to modify. The script will look up the collaborating scenario for you. The user must have edit access to the plan. If the user is not the owner of the plan, see [How to Share Your Plan](https://docs.visier.com/visier-people/Planning/plan%20sharing/plan%20sharing.htm).
```
TARGET_PLAN_NAME='Untitled'
```

# Usage
This script consolidate and rolls up all plan data to the root plan. Modify `TARGET_PLAN_NAME` to your root plan's name, and the script will look up the collaborating scenario for you.
During the execution, it will terminate the process if it encouter any fatel error. In such case, please look into the log for how to fix the error, then run the script again. 

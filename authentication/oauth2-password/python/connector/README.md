# Authentication With Python Connector and Password
1. Create a virtual environment: `python3 -m venv env`.
1. Activate the virtual environment: `source env/bin/activate`.
1. Install the required dependencies: `pip install -r requirements.txt`.
1. Clone the `../.env-password-template` environment file to `.env`.
1. Update the `.env` file with the appropriate values to match your system details.
1. Source the environment file `source .env` and provide the sensitive values. Sensitive values should not be stored in the 'source .env` file itself.
1. Call `python app.py` to see an example of how to parse the JWT and make a Data Model API call.
1. Deactivate the virtual environment: `deactivate`.

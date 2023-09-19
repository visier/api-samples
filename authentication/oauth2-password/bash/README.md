# Authentication With Shell Script and Password
1. Clone the `../.env-password-teamplate` environment file to `./.env`
1. Update the `.env` file with the appropriate values to match your system details.
1. Source the environment file `source .env` and provide the sensitive values. Sensitive values should not be stored in the `source .env` file itself.
1. The token requesting API is called in: `authenticate.sh`
1. Call `./get-members.sh` to see an example of how to parse the JWT and make a Data Model API call.

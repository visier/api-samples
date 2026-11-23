#!/usr/bin/env bash
# Runs the full bundle setup in the order documented in
# src/visier-sdlc/README.md ("Initialize and deploy").
#
# Works with either option from the README:
#   dotenv run -- ./deploy.sh      # Option 1: values from .env
#   ./deploy.sh                    # Option 2: BUNDLE_VAR_* already exported
#
# Run from the visier_sdlc/ directory (where databricks.yml lives).
set -euo pipefail

cd "$(dirname "$0")"

step() {
  echo
  echo "==> $*"
  "$@"
}

# 0. Validate
step databricks bundle validate

# 1. Create/update the app and its service principal (required before secrets are granted).
step databricks bundle deploy

# 2. Create the promotion state table.
step databricks bundle run sql_setup_job

# 3. Create/update tenant secrets and grant the app's service principal access.
step databricks bundle run setup_secrets

# 4. Start (or restart) the app.
step databricks bundle run visier_sdlc_app

echo
echo "Deployment complete."

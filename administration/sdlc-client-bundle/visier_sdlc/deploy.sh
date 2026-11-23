#!/usr/bin/env bash
# Runs the full bundle setup in the order documented in
# src/visier-sdlc/README.md ("Initialize and deploy").
#
# Works with either option from the README:
#   dotenv run -- ./deploy.sh      # Values from .env
#   ./deploy.sh                    # BUNDLE_VAR_* exported or native variable file
#
# Run from the visier_sdlc/ directory (where databricks.yml lives).
set -euo pipefail

cd "$(dirname "$0")"

if (( $# > 0 )); then
  echo "Usage: ./deploy.sh (set bundle variables using the CLI's standard configuration)" >&2
  exit 2
fi

step() {
  echo
  echo "==> $*"
  "$@"
}

# 0. Validate
step databricks bundle validate

# 1. Create the table before registering it as an app resource (no deployed job needed).
step databricks bundle run setup_table

# 2. Create/update the app and its service principal (required before secrets are granted).
step databricks bundle deploy

# 3. Create/update tenant secrets and grant the app's service principal access.
step databricks bundle run setup_secrets

# 4. Start (or restart) the app.
step databricks bundle run visier_sdlc_app

echo
echo "Deployment complete."

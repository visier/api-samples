#!/usr/bin/env bash
# Removes the bundle and its configured state table, tenant secrets, and grants.
# Use the same environment or native variable file as ./deploy.sh.
set -euo pipefail

cd "$(dirname "$0")"
exec uv run --locked --no-dev --project src/visier-sdlc python src/visier-sdlc/scripts/undeploy.py "$@"

"""Unbind deleted apps before planning deployment (Databricks CLI nil-remote bug)."""
import json
import subprocess
import sys

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import DatabricksError, NotFound


def prepare_deploy():
    # Pull authoritative bundle state; a local cache can retain obsolete bindings.
    # Keep JSON captured: the resolved configuration can contain secret variables.
    result = subprocess.run(
        ["databricks", "bundle", "summary", "--force-pull", "--output", "json"],
        check=True, stdout=subprocess.PIPE, text=True,
    )
    summary = json.loads(result.stdout)
    apps = summary.get("resources", {}).get("apps", {})
    bound_apps = {key: app["id"] for key, app in apps.items() if app.get("id")}
    if not bound_apps:
        return

    # Use the same workspace/profile that the bundle resolved, including any
    # workspace override in databricks.yml, rather than the SDK's default host.
    settings = summary["workspace"]
    workspace = WorkspaceClient(**{
        key: settings[key] for key in ("host", "profile") if settings.get(key)
    })
    for key, app_id in bound_apps.items():
        try:
            workspace.apps.get(app_id)
        except NotFound:
            # Unbind only this confirmed-missing app. Preserve every other
            # resource and let deploy recreate the app and its service principal.
            print(f"Clearing stale binding for deleted app {app_id} ({key}).", flush=True)
            subprocess.run(
                ["databricks", "bundle", "deployment", "unbind", key], check=True,
            )


if __name__ == "__main__":
    try:
        prepare_deploy()
    except subprocess.CalledProcessError as error:
        # CLI errors already went to stderr; do not print captured bundle JSON.
        sys.exit(error.returncode)
    except DatabricksError as error:
        sys.exit(f"Cannot check app deployment state: {error}")

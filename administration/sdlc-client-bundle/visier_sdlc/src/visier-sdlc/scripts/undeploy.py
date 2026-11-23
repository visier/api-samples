"""Remove bundle resources and the Unity Catalog objects provisioned by setup."""
import argparse
import json
import os
import re
import subprocess
import sys
from urllib.parse import quote

from databricks.sdk import WorkspaceClient
from databricks.sdk.errors import DatabricksError, NotFound


ROLES = ("source", "target")
FIELDS = ("host", "vanity", "username", "password")


def cli_env():
    # Teardown never needs tenant credentials. Preserve secret_prefix and all
    # normal Databricks authentication and bundle configuration settings.
    credentials = {f"BUNDLE_VAR_secret_{role}_{field}" for role in ROLES for field in FIELDS}
    return {key: value for key, value in os.environ.items() if key not in credentials}


def bundle_json(*args):
    # Resolved config can contain secrets from a native variable file; keep it
    # out of terminal output, including when a CLI command fails.
    result = subprocess.run(
        ["databricks", "bundle", *args, "--output", "json"],
        env=cli_env(), stdout=subprocess.PIPE, text=True, check=True,
    )
    return json.loads(result.stdout)


def cleanup_settings(summary):
    variables = summary["variables"]
    settings = {key: variables[key]["value"] for key in (
        "catalog_name", "schema_name", "state_table_name", "secret_prefix", "app_name",
    )}
    for key in ("catalog_name", "schema_name", "state_table_name"):
        if not isinstance(settings[key], str) or not re.fullmatch(r"[A-Za-z_]\w*", settings[key]):
            raise ValueError(f"{key} must be a simple identifier")
    prefix = settings["secret_prefix"]
    if not isinstance(prefix, str) or (prefix and not re.fullmatch(r"[\w-]+", prefix)):
        raise ValueError("secret_prefix must contain only letters, digits, underscores, or hyphens")
    return settings


def ignore_missing(action, *args, **kwargs):
    try:
        return action(*args, **kwargs)
    except NotFound:
        return None


def revoke_grants(workspace, settings, principal):
    catalog, schema, prefix = (settings[key] for key in ("catalog_name", "schema_name", "secret_prefix"))
    targets = [
        ("table", f"{catalog}.{schema}.{settings['state_table_name']}", ["SELECT", "MODIFY"]),
        # setup_secrets also grants optional, manually provisioned tenant-id
        # secrets. Revoke those grants, but retain the manually created secrets.
        *[("secret", f"{catalog}.{schema}.{prefix}{role}-{field}", ["READ_SECRET"])
          for role in ROLES for field in (*FIELDS, "tenant-id")],
        ("schema", f"{catalog}.{schema}", ["USE_SCHEMA"]),
    ]
    # USE_CATALOG is inherited through membership in account users; do not revoke it.
    for kind, name, privileges in targets:
        path = f"/api/2.1/unity-catalog/permissions/{kind}/{quote(name, safe='')}"
        ignore_missing(
            workspace.api_client.do, "PATCH", path,
            body={"changes": [{"principal": principal, "remove": privileges}]},
        )


def remove_data(workspace, settings):
    namespace = f"{settings['catalog_name']}.{settings['schema_name']}"
    for role in ROLES:
        for field in FIELDS:
            name = f"{namespace}.{settings['secret_prefix']}{role}-{field}"
            ignore_missing(workspace.secrets_uc.delete_secret, name)
            print(f"Removed secret (if present): {name}", flush=True)
    table = f"{namespace}.{settings['state_table_name']}"
    ignore_missing(workspace.tables.delete, table)
    print(f"Removed state table (if present): {table}", flush=True)


def undeploy(*, dry_run=False, yes=False, force_lock=False):
    summary = bundle_json("summary", "--force-pull")
    settings = cleanup_settings(summary)
    apps = summary.get("resources", {}).get("apps", {})
    app = apps.get("visier_sdlc_app", {})
    if app.get("id") and app["id"] != settings["app_name"]:
        raise ValueError("The bound app differs from app_name; restore the deployment's original variables first")

    config = summary["workspace"]
    workspace = WorkspaceClient(**{key: config[key] for key in ("host", "profile") if config.get(key)})
    namespace = f"{settings['catalog_name']}.{settings['schema_name']}"
    # The CLI omits workspace.host when unified authentication supplies it.
    print(f"Workspace: {workspace.config.host}")
    print(f"Bundle: {summary['bundle']['name']} / {summary['bundle']['target']}")
    print("Remove bundle-managed app, its service principal, setup job, and uploaded bundle files.")
    print(f"Remove state table and ALL promotion history: {namespace}.{settings['state_table_name']}")
    print("Remove these tenant secrets (including any that existed before deployment):")
    for role in ROLES:
        for field in FIELDS:
            print(f"  {namespace}.{settings['secret_prefix']}{role}-{field}")
    print("Revoke setup grants for the app's service principal.")
    print("Retain the catalog, schema, SQL warehouse, optional tenant-id secrets, and local settings.")
    if dry_run:
        print("Preview only; no resources changed.")
        return
    if not yes:
        try:
            answer = input("Delete these resources and their data? Type 'undeploy' to continue: ")
        except EOFError:
            raise ValueError("Confirmation required; use --yes for unattended teardown") from None
        if answer != "undeploy":
            raise ValueError("Undeployment cancelled; no resources changed")

    # Capture and revoke grants before Apps deletes its dedicated principal.
    # Use only the tracked app, never an unrelated app with a matching name.
    if app.get("id"):
        remote = ignore_missing(workspace.apps.get, app["id"])
        if remote is not None:
            principal = remote.service_principal_client_id
            if not principal:
                raise ValueError("The bound app has no service principal; cannot clean up its grants")
            revoke_grants(workspace, settings, principal)

    command = ["databricks", "bundle", "destroy", "--auto-approve"]
    if force_lock:
        command.append("--force-lock")
    subprocess.run(command, env=cli_env(), check=True)
    # The bundle cannot track these objects. Destroy must succeed before their
    # data is removed; missing objects are harmless when retrying partial cleanup.
    remove_data(workspace, settings)
    print("Undeployment complete.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Show what would be removed without changing resources")
    parser.add_argument("--yes", action="store_true", help="Confirm deletion of the listed resources and data")
    parser.add_argument("--force-lock", action="store_true", help="Override a stale lock only when no deployment is running")
    args = parser.parse_args()
    try:
        undeploy(dry_run=args.dry_run, yes=args.yes, force_lock=args.force_lock)
    except subprocess.CalledProcessError as error:
        sys.exit(error.returncode)
    except (DatabricksError, ValueError) as error:
        sys.exit(f"Undeployment stopped: {error}")


if __name__ == "__main__":
    main()

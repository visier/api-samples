"""Create/update the tenant secrets in Unity Catalog and grant the app READ_SECRET on them.

Run through the bundle, which resolves settings files, BUNDLE_VAR_* environment
variables, and --var overrides and passes the results as BUNDLE_VAR_* inputs:

    databricks bundle run setup_secrets

Secret values are passed to this local process, never to a deployed job.
Secrets are named {prefix}{source|target}-{field} (underscores become
hyphens). A non-empty value creates the secret or updates it; an empty value leaves any existing
secret untouched. Afterwards the supported tenant secrets in catalog.schema with the prefix are granted
READ_SECRET for the app's service principal (looked up from the deployed app), plus USE CATALOG /
USE SCHEMA on the parents. Everything is idempotent. Create the app first (through the bundle or Apps UI) so its service principal exists.
The state table must also exist; the script grants SELECT and MODIFY on it.
"""
import os
import re
import sys

from databricks.sdk import WorkspaceClient
from databricks.sdk.common.types.fieldmask import FieldMask
from databricks.sdk.errors import DatabricksError, NotFound
from databricks.sdk.service.catalog import Secret

IDENT = re.compile(r"[A-Za-z_][\w-]*")
ROLES = ("source", "target")
FIELDS = ("host", "vanity", "username", "password")
REQUIRED = ("source-host", "target-host")


def secret_values(env, prefix):
    """Map non-empty BUNDLE_VAR_secret_{role}_{field} inputs to secret names."""
    values = {}
    for role in ROLES:
        for field in FIELDS:
            value = env.get(f"BUNDLE_VAR_secret_{role}_{field}", "")
            if value:
                values[f"{prefix}{role}-{field.replace('_', '-')}"] = value
    return values


def upsert_secrets(workspace, catalog, schema, values):
    for name, value in values.items():
        full_name = f"{catalog}.{schema}.{name}"
        try:
            workspace.secrets_uc.get_secret(full_name)
        except NotFound:
            workspace.secrets_uc.create_secret(Secret(name=name, catalog_name=catalog, schema_name=schema, value=value))
        else:
            workspace.secrets_uc.update_secret(full_name, Secret(name=name, catalog_name=catalog,
                                                                 schema_name=schema, value=value), FieldMask(["value"]))


def _grant(workspace, securable_type, full_name, principal, privileges):
    # The SDK's Privilege / SecurableType enums predate UC secrets, so use the REST endpoint directly.
    workspace.api_client.do(
        "PATCH", f"/api/2.1/unity-catalog/permissions/{securable_type}/{full_name}",
        body={"changes": [{"principal": principal, "add": list(privileges)}]},
    )


def grant_secret_access(workspace, catalog, schema, prefix, principal):
    supported = {f"{prefix}{role}-{field}" for role in ROLES for field in (*FIELDS, "tenant-id")}
    names = sorted(
        s.name for s in workspace.secrets_uc.list_secrets(catalog_name=catalog, schema_name=schema)
        if s.name in supported
    )
    missing = [prefix + r for r in REQUIRED if prefix + r not in names]
    if missing:
        raise RuntimeError(f"Missing required secrets in {catalog}.{schema}: {missing}")
    try:
        _grant(workspace, "catalog", catalog, principal, ["USE_CATALOG"])
    except DatabricksError as e:
        # Often implicitly granted to all account users, so a failed grant is not necessarily a problem.
        print(f"WARNING: could not grant USE_CATALOG on {catalog} to {principal}: {e}. "
              "Continuing; the app needs USE_CATALOG, which may already be granted implicitly.", file=sys.stderr)
    _grant(workspace, "schema", f"{catalog}.{schema}", principal, ["USE_SCHEMA"])
    for name in names:
        _grant(workspace, "secret", f"{catalog}.{schema}.{name}", principal, ["READ_SECRET"])
    return names


def main(env=None):
    env = os.environ if env is None else env
    catalog, schema = env["BUNDLE_VAR_catalog_name"], env["BUNDLE_VAR_schema_name"]
    prefix = env.get("BUNDLE_VAR_secret_prefix", "visier-sdlc-")
    table = env.get("BUNDLE_VAR_state_table_name", "promotion_state")
    app_name = env["BUNDLE_VAR_app_name"]
    if not re.fullmatch(r"[A-Za-z_]\w*", table):
        raise ValueError("State table name must be a simple identifier")
    for part in (catalog, schema):
        if not IDENT.fullmatch(part):
            raise ValueError(f"Invalid identifier: {part!r}")
    workspace = WorkspaceClient()
    upsert_secrets(workspace, catalog, schema, secret_values(env, prefix))
    principal = workspace.apps.get(app_name).service_principal_client_id
    if not principal:
        raise RuntimeError(f"App {app_name} has no service principal; create the app first")
    names = grant_secret_access(workspace, catalog, schema, prefix, principal)
    _grant(workspace, "table", f"{catalog}.{schema}.{table}", principal, ["SELECT", "MODIFY"])
    print(f"READ_SECRET granted to {principal} on {len(names)} secret(s): {', '.join(names)}")


if __name__ == "__main__":
    main()

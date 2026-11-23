"""Create/update the tenant secrets in Unity Catalog and grant the app READ_SECRET on them.

Run through the bundle (which supplies every value from bundle variables, so BUNDLE_VAR_* in the
environment or an interactive prompt):

    databricks bundle run setup_secrets

Secret values travel only from your environment to Unity Catalog; they are never put in the bundle
or in a deployed job. Secrets are named {prefix}{source|target}-{field} (underscores become
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
    """{secret name: value} for every non-empty SECRET_{ROLE}_{FIELD} environment value."""
    values = {}
    for role in ROLES:
        for field in FIELDS:
            value = env.get(f"SECRET_{role}_{field}".upper(), "")
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
    # The bundle passes script variables; standalone UI-app setup can use the
    # same BUNDLE_VAR_* inputs used by CLI deployment, without deploying a bundle.
    inputs = {"CATALOG": "catalog_name", "SCHEMA": "schema_name", "PREFIX": "secret_prefix",
              "APP_NAME": "app_name", "TABLE": "state_table_name"}
    inputs.update({f"SECRET_{role}_{field}".upper(): f"secret_{role}_{field}"
                   for role in ROLES for field in FIELDS})
    env = dict(env)
    for name, variable in inputs.items():
        bundle_name = f"BUNDLE_VAR_{variable}"
        if bundle_name not in env:
            continue
        if name in env and env[name] != env[bundle_name]:
            raise ValueError(f"Conflicting values for {name} and {bundle_name}")
        env[name] = env[bundle_name]
    env.setdefault("PREFIX", "visier-sdlc-")
    env.setdefault("TABLE", "promotion_state")
    catalog, schema, prefix = env["CATALOG"], env["SCHEMA"], env.get("PREFIX", "")
    table = env["TABLE"]
    if not re.fullmatch(r"[A-Za-z_]\w*", table):
        raise ValueError("State table name must be a simple identifier")
    for part in (catalog, schema):
        if not IDENT.fullmatch(part):
            raise ValueError(f"Invalid identifier: {part!r}")
    workspace = WorkspaceClient()
    upsert_secrets(workspace, catalog, schema, secret_values(env, prefix))
    principal = workspace.apps.get(env["APP_NAME"]).service_principal_client_id
    if not principal:
        raise RuntimeError(f"App {env['APP_NAME']} has no service principal; create the app first")
    names = grant_secret_access(workspace, catalog, schema, prefix, principal)
    _grant(workspace, "table", f"{catalog}.{schema}.{table}", principal, ["SELECT", "MODIFY"])
    print(f"READ_SECRET granted to {principal} on {len(names)} secret(s): {', '.join(names)}")


if __name__ == "__main__":
    main()

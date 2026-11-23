"""Call build_app(spark, dbutils.secrets.get) in a configured Databricks runtime.

This deliberately receives runtime capabilities instead of creating a session or
assuming dbutils exists in a web worker. Provision the Delta table row first.
"""
import os

from app import create_app, tenant_pair_key
from promotion.credentials import DatabricksSecretsCredentials
from promotion.storage import DatabricksDeltaStateStore, qualified_table_name


def build_app(spark, get_secret):
    credentials = DatabricksSecretsCredentials(
        get_secret, scope=os.environ["VISIER_SECRET_SCOPE"],
        keys={role: {field: f"{role}-{field.replace('_', '-')}" for field in
                     ("host", "vanity", "username", "password")}
              for role in ("source", "target")},
    )
    # Add "api_key" to the secret mapping above if required by your server.
    # Add "tenant_id" for a role only when addressing a different managed tenant.
    table = qualified_table_name(
        os.environ["VISIER_SECRETS_CATALOG"], os.environ["VISIER_SECRETS_SCHEMA"], os.environ["PROMOTION_STATE_TABLE"],
    )
    store = DatabricksDeltaStateStore(spark, table, tenant_pair_key(credentials))
    store.read()  # Fail early if the deployment hasn't provisioned the state row.
    return create_app({"APP_MODE": "live"}, store=store, credentials=credentials)

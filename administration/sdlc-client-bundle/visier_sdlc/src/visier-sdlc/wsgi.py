"""Gunicorn entry point, used by Databricks Apps (configured in resources/visier_sdlc.app.yml).

APP_MODE=demo (the default) starts the demo workspace with local SQLite state.
APP_MODE=live reads tenant secrets from Unity Catalog and keeps state in a Delta
table through a SQL warehouse. Missing tenant-pair rows are initialized at startup;
the Delta table itself must already exist.
"""
import os

from app import create_app, tenant_pair_key


def build_app():
    if os.getenv("APP_MODE", "demo") != "live":
        return create_app()

    import logging

    from databricks.sdk import WorkspaceClient

    from promotion.databricks_apps import SqlWarehouseStateStore, UnityCatalogSecretsCredentials, state_location

    # Send promotion diagnostics (for example Visier HTTP failures) to stderr, which Databricks Apps collects.
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    workspace = WorkspaceClient()  # Inside an App, authenticates as the app's service principal.
    catalog, schema, table = state_location(os.environ)
    credentials = UnityCatalogSecretsCredentials(
        workspace,
        catalog=catalog,
        schema=schema,
        prefix=os.getenv("VISIER_SECRET_PREFIX", ""),
    )
    store = SqlWarehouseStateStore(workspace, os.environ["SQL_WAREHOUSE_ID"], table, tenant_pair_key(credentials))
    store.provision()  # An empty state requires verified baselines in the app for an existing target.
    return create_app({"APP_MODE": "live"}, store=store, credentials=credentials)


app = build_app()

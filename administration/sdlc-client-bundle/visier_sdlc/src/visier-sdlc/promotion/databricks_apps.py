"""Databricks Apps adapters: Unity Catalog secrets and a SQL-warehouse state store.

A Databricks App process has no Spark session and no dbutils. These adapters use
the Databricks SDK instead, authenticated as the app's service principal.
"""
from __future__ import annotations

import json
import re
import time
import uuid

from databricks.sdk.errors import NotFound

from .ports import AppError

TABLE_NAME = re.compile(r"[A-Za-z_]\w*\.[A-Za-z_]\w*\.[A-Za-z_]\w*")
SECRET_PART = re.compile(r"[A-Za-z_][\w-]*")

REQUIRED_FIELDS = ("host",)
OPTIONAL_FIELDS = ("vanity", "username", "password", "tenant_id")
SECRET_PREFIX = re.compile(r"(?:[A-Za-z_][\w-]*)?")


def state_location(env):
    """Resolve a UI-attached table or the bundle's explicit catalog/schema/table."""
    from .storage import qualified_table_name

    full_name = env.get("PROMOTION_STATE_TABLE_FULL_NAME")
    if full_name:
        if not TABLE_NAME.fullmatch(full_name):
            raise ValueError("Expected a catalog.schema.table identifier for promotion-state")
        catalog, schema, table = full_name.split(".")
        for key, value in (("VISIER_SECRETS_CATALOG", catalog), ("VISIER_SECRETS_SCHEMA", schema),
                           ("PROMOTION_STATE_TABLE", table)):
            if env.get(key) and env[key] != value:
                raise ValueError(f"{key} conflicts with the attached promotion-state table")
        return catalog, schema, full_name
    catalog, schema = env["VISIER_SECRETS_CATALOG"], env["VISIER_SECRETS_SCHEMA"]
    return catalog, schema, qualified_table_name(catalog, schema, env["PROMOTION_STATE_TABLE"])


class UnityCatalogSecretsCredentials:
    """Reads tenant configuration from Unity Catalog secrets.

    Secret names follow ``{prefix}{role}-{field}``, for example
    ``visier-sdlc-source-host`` in ``my_catalog.my_schema`` for prefix ``visier-sdlc-``
    (the bundle's ``secret_prefix`` variable, passed as VISIER_SECRET_PREFIX). Optional fields are read only
    when their secret exists. A missing host is a startup error.
    """

    def __init__(self, workspace, *, catalog: str, schema: str, prefix: str = ""):
        for part in (catalog, schema):
            if not SECRET_PART.fullmatch(part):
                raise ValueError(f"Invalid Unity Catalog name: {part!r}")
        if not SECRET_PREFIX.fullmatch(prefix):
            raise ValueError(f"Invalid secret prefix: {prefix!r}")
        self.workspace, self.catalog, self.schema, self.prefix = workspace, catalog, schema, prefix

    def _full_name(self, role: str, field: str) -> str:
        return f"{self.catalog}.{self.schema}.{self.prefix}{role}-{field.replace('_', '-')}"

    def _read(self, role: str, field: str):
        secret = self.workspace.secrets_uc.get_secret(self._full_name(role, field), include_value=True)
        return secret.effective_value

    def configuration(self, role: str) -> dict:
        config = {}
        for field in REQUIRED_FIELDS:
            try:
                config[field] = self._read(role, field)
            except NotFound:
                raise RuntimeError(f"Missing Unity Catalog secret {self._full_name(role, field)}") from None
        for field in OPTIONAL_FIELDS:
            try:
                value = self._read(role, field)
            except NotFound:
                continue
            if value:
                config[field] = value
        return config


class SqlWarehouseStateStore:
    """Delta-backed state store that runs its statements on a SQL warehouse.

    Same contract and table layout as DatabricksDeltaStateStore, without Spark.
    Updates use the revision predicate and a per-write token, as the Spark adapter does.
    """

    def __init__(self, workspace, warehouse_id: str, table: str, key: str):
        if not TABLE_NAME.fullmatch(table):
            raise ValueError("Expected a catalog.schema.table identifier")
        self.workspace, self.warehouse_id, self.table, self.key = workspace, warehouse_id, table, key

    def _execute(self, statement: str, parameters: dict):
        from databricks.sdk.service.sql import StatementParameterListItem, StatementState

        items = [StatementParameterListItem(name=name, value=str(value), type=kind)
                 for name, (value, kind) in parameters.items()]
        response = self.workspace.statement_execution.execute_statement(
            statement=statement, warehouse_id=self.warehouse_id, parameters=items, wait_timeout="30s")
        # Poll until the statement finishes; the statement text and parameters are never logged.
        while response.status and response.status.state in (StatementState.PENDING, StatementState.RUNNING):
            time.sleep(1)
            response = self.workspace.statement_execution.get_statement(response.statement_id)
        state = response.status.state if response.status else None
        if state != StatementState.SUCCEEDED:
            message = response.status.error.message if response.status and response.status.error else "no detail"
            raise RuntimeError(f"State statement did not succeed ({state}): {message}")
        return response

    def _key_param(self):
        return {"pair": (self.key, "STRING")}

    def provision(self) -> bool:
        """Ensure this pair has a row. Return True if it was initially missing.

        A conditional MERGE keeps concurrent startups from blindly appending
        duplicate rows. Existing checkpoints and operation claims are untouched.
        """
        rows = self._read_rows()
        if rows:
            self.read()  # Validate cardinality and the document before startup.
            return False
        try:
            self._execute(
                f"MERGE INTO {self.table} AS saved USING (SELECT :pair AS pair) AS initial "
                "ON saved.pair = initial.pair "
                "WHEN NOT MATCHED THEN INSERT (pair, revision, document) VALUES (initial.pair, 0, '{}')",
                self._key_param(),
            )
        except Exception:
            # Another worker may have won the Delta transaction, or our insert
            # may have committed before the response was lost. Only accept the
            # failure if a durable row now exists; never retry with a blind INSERT.
            if not self._read_rows():
                raise
        self.read()
        return True

    def _read_rows(self):
        response = self._execute(f"SELECT revision, document FROM {self.table} WHERE pair = :pair", self._key_param())
        return (response.result.data_array if response.result else None) or []

    def read(self):
        rows = self._read_rows()
        if len(rows) != 1:
            raise RuntimeError("Provision exactly one promotion_state row for this tenant pair")
        revision, document = rows[0]
        return int(revision), json.loads(document)

    def compare_and_swap(self, revision: int, value: dict):
        token = uuid.uuid4().hex
        document = dict(value, _write_token=token)
        self._execute(
            f"UPDATE {self.table} SET revision = revision + 1, document = :document "
            "WHERE pair = :pair AND revision = :revision",
            {"document": (json.dumps(document), "STRING"), "pair": (self.key, "STRING"),
             "revision": (revision, "BIGINT")},
        )
        _, saved = self.read()
        if saved.get("_write_token") != token:
            raise AppError("State changed in another session. Refresh and try again.")

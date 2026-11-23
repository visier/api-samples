from __future__ import annotations

import json
import re
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .ports import AppError


def qualified_table_name(catalog: str, schema: str, table: str) -> str:
    """Compose a table identifier from three unqualified configuration values."""
    for name, part in (("catalog", catalog), ("schema", schema), ("table", table)):
        if not re.fullmatch(r"[A-Za-z_]\w*", part):
            raise ValueError(f"Expected an unqualified {name} identifier: {part!r}")
    return f"{catalog}.{schema}.{table}"


class SQLiteStateStore:
    def __init__(self, path: str, key: str):
        self.path, self.key = path, key
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE IF NOT EXISTS promotion_state (pair TEXT PRIMARY KEY, revision INTEGER NOT NULL, document TEXT NOT NULL)")
            db.execute("INSERT OR IGNORE INTO promotion_state VALUES (?, 0, '{}')", (key,))

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        try:
            # SQLite's context manager commits or rolls back, but does not close
            # the connection. Release its file handles on every exit path.
            with db:
                yield db
        finally:
            db.close()

    def read(self):
        with self._connect() as db:
            revision, document = db.execute("SELECT revision, document FROM promotion_state WHERE pair=?", (self.key,)).fetchone()
        return revision, json.loads(document)

    def compare_and_swap(self, revision, value):
        with self._connect() as db:
            result = db.execute("UPDATE promotion_state SET revision=revision+1, document=? WHERE pair=? AND revision=?", (json.dumps(value), self.key, revision))
            if result.rowcount != 1:
                raise AppError("State changed in another session. Refresh and try again.")


class DatabricksDeltaStateStore:
    """Inject a SparkSession on Databricks; the state lives in a Delta table.

    Provision the table and its single pair row before starting app replicas.
    Delta's optimistic concurrency plus the revision predicate protects updates.
    No credentials or SDK objects are persisted in this table.
    """

    def __init__(self, spark, table: str, key: str):
        if not re.fullmatch(r"[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*){0,2}", table):
            raise ValueError("Expected a catalog.schema.table identifier")
        self.spark, self.table, self.key = spark, table, key

    def read(self):
        from pyspark.sql import functions as F
        rows = self.spark.table(self.table).where(F.col("pair") == self.key).collect()
        if len(rows) != 1:
            raise RuntimeError("Provision exactly one promotion_state row for this tenant pair")
        return rows[0].revision, json.loads(rows[0].document)

    def compare_and_swap(self, revision, value):
        from delta.tables import DeltaTable
        from pyspark.sql import functions as F
        import uuid
        # A unique token distinguishes our successful update from a competing writer.
        token = uuid.uuid4().hex
        document = dict(value, _write_token=token)
        DeltaTable.forName(self.spark, self.table).update(
            condition=(F.col("pair") == self.key) & (F.col("revision") == revision),
            set={"revision": F.lit(revision + 1), "document": F.lit(json.dumps(document))},
        )
        _, saved = self.read()
        if saved.get("_write_token") != token:
            raise AppError("State changed in another session. Refresh and try again.")

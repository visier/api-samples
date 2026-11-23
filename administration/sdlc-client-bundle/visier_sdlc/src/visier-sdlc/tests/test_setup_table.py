from types import SimpleNamespace

import pytest
from databricks.sdk.service.sql import StatementState

from scripts.setup_table import setup_table


def test_table_setup_binds_names_and_waits_for_completion(monkeypatch):
    calls = []
    states = iter([StatementState.RUNNING, StatementState.SUCCEEDED])

    def execute(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(statement_id="stmt", status=SimpleNamespace(state=StatementState.PENDING))

    workspace = SimpleNamespace(statement_execution=SimpleNamespace(
        execute_statement=execute,
        get_statement=lambda statement_id: SimpleNamespace(status=SimpleNamespace(state=next(states))),
    ))
    monkeypatch.setattr("scripts.setup_table.time.sleep", lambda seconds: None)
    setup_table(workspace, {"CATALOG": "customer", "SCHEMA": "apps", "TABLE": "state", "WAREHOUSE_ID": "wh"})
    assert calls[0]["warehouse_id"] == "wh"
    assert "CREATE TABLE IF NOT EXISTS IDENTIFIER(" in calls[0]["statement"]
    assert {p.name: p.value for p in calls[0]["parameters"]} == {
        "catalog": "customer", "schema": "apps", "table": "state"}


def test_table_failure_stops_setup():
    workspace = SimpleNamespace(statement_execution=SimpleNamespace(execute_statement=lambda **kwargs:
        SimpleNamespace(statement_id="stmt", status=SimpleNamespace(state=StatementState.FAILED))))
    with pytest.raises(RuntimeError, match="setup failed"):
        setup_table(workspace, {"CATALOG": "cat", "SCHEMA": "sch", "TABLE": "state", "WAREHOUSE_ID": "wh"})

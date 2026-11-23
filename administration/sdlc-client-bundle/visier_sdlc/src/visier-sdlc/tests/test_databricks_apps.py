import json
import runpy
from pathlib import Path
from types import SimpleNamespace

import pytest
from databricks.sdk.errors import NotFound
from databricks.sdk.service.sql import ResultData, StatementResponse, StatementState, StatementStatus

from promotion.databricks_apps import SqlWarehouseStateStore, UnityCatalogSecretsCredentials, state_location
from promotion.ports import AppError

PAIR = "live:test-pair"
TABLE = "my_catalog.my_schema.promotion_state"


class FakeSecrets:
    def __init__(self, values):
        self.values, self.requested = values, []

    def get_secret(self, full_name, include_value=False):
        self.requested.append(full_name)
        if full_name not in self.values:
            raise NotFound(f"no secret {full_name}")
        return SimpleNamespace(effective_value=self.values[full_name])


class FakeStatements:
    """Tiny stand-in for the warehouse: one state table, and the statement shapes the adapter sends."""

    def __init__(self):
        self.rows = {}  # pair -> [revision, document]

    def execute_statement(self, statement, warehouse_id, parameters, wait_timeout):
        params = {item.name: item.value for item in parameters}
        if statement.startswith("MERGE"):
            self.rows.setdefault(params["pair"], [0, "{}"])
            return _ok([])
        if statement.startswith("SELECT revision"):
            row = self.rows.get(params["pair"])
            return _ok([[str(row[0]), row[1]]] if row else [])
        if statement.startswith("UPDATE"):
            row = self.rows.get(params["pair"])
            if row and row[0] == int(params["revision"]):
                self.rows[params["pair"]] = [row[0] + 1, params["document"]]
            return _ok([])
        raise AssertionError(f"unexpected statement: {statement}")


def _ok(data_array):
    return StatementResponse(statement_id="s", status=StatementStatus(state=StatementState.SUCCEEDED),
                             result=ResultData(data_array=data_array))


def _workspace(secrets=None, statements=None):
    return SimpleNamespace(secrets_uc=secrets or FakeSecrets({}), statement_execution=statements or FakeStatements())


def test_credentials_use_prefixed_uc_names_and_skip_missing_optional_secrets():
    secrets = FakeSecrets({
        "my_catalog.my_schema.sdlc-demo-source-host": "https://dev.example",
        "my_catalog.my_schema.sdlc-demo-source-username": "user",
        "my_catalog.my_schema.sdlc-demo-source-password": "pw",
    })
    credentials = UnityCatalogSecretsCredentials(_workspace(secrets), catalog="my_catalog", schema="my_schema", prefix="sdlc-demo-")

    config = credentials.configuration("source")

    assert config == {"host": "https://dev.example", "username": "user", "password": "pw"}
    assert "my_catalog.my_schema.sdlc-demo-source-tenant-id" in secrets.requested


def test_missing_host_secret_is_a_clear_startup_error():
    credentials = UnityCatalogSecretsCredentials(_workspace(), catalog="my_catalog", schema="my_schema", prefix="sdlc-demo-")

    with pytest.raises(RuntimeError, match="my_catalog.my_schema.sdlc-demo-target-host"):
        credentials.configuration("target")


def test_invalid_catalog_name_is_rejected():
    with pytest.raises(ValueError):
        UnityCatalogSecretsCredentials(_workspace(), catalog="my_catalog; drop", schema="my_schema")


def test_invalid_secret_prefix_is_rejected():
    with pytest.raises(ValueError):
        UnityCatalogSecretsCredentials(_workspace(), catalog="my_catalog", schema="my_schema", prefix="bad.prefix-")


def test_removed_authentication_secrets_are_not_read():
    removed = ("api-key", "client-id", "client-secret", "access-token", "asid-token")
    secrets = FakeSecrets({"my_catalog.my_schema.p-source-host": "h", **{
        f"my_catalog.my_schema.p-source-{field}": "private-value" for field in removed}})
    config = UnityCatalogSecretsCredentials(_workspace(secrets), catalog="my_catalog", schema="my_schema", prefix="p-").configuration("source")
    assert config == {"host": "h"}
    assert not any(name.endswith(field) for name in secrets.requested for field in removed)


def test_table_name_must_be_three_part_identifier():
    with pytest.raises(ValueError):
        SqlWarehouseStateStore(_workspace(), "wh", "promotion_state", PAIR)


def test_provision_inserts_once_and_never_overwrites():
    statements = FakeStatements()
    store = SqlWarehouseStateStore(_workspace(statements=statements), "wh", TABLE, PAIR)

    assert store.provision() is True
    statements.rows[PAIR] = [7, json.dumps({"checkpoint": {"source_id": "a"}})]
    assert store.provision() is False
    assert statements.rows[PAIR][0] == 7


def test_read_and_compare_and_swap_round_trip():
    statements = FakeStatements()
    store = SqlWarehouseStateStore(_workspace(statements=statements), "wh", TABLE, PAIR)
    store.provision()

    revision, state = store.read()
    assert (revision, state) == (0, {})

    store.compare_and_swap(revision, {"checkpoint": {"source_id": "a", "target_id": "b"}})

    revision, state = store.read()
    assert revision == 1
    assert state["checkpoint"] == {"source_id": "a", "target_id": "b"}
    assert "_write_token" in state


def test_provision_accepts_a_concurrent_startup_without_overwriting_its_state():
    saved = {"checkpoint": {"source_id": "a", "target_id": "b"},
             "operation": {"id": "unresolved"}}

    class CompetingStartup(FakeStatements):
        def execute_statement(self, statement, **kwargs):
            if statement.startswith("MERGE"):
                self.rows[PAIR] = [9, json.dumps(saved)]
                raise RuntimeError("concurrent update")
            return super().execute_statement(statement, **kwargs)

    store = SqlWarehouseStateStore(_workspace(statements=CompetingStartup()), "wh", TABLE, PAIR)
    store.provision()
    assert store.read() == (9, saved)


def test_provision_failure_without_a_durable_row_is_not_ignored():
    class Denied(FakeStatements):
        def execute_statement(self, statement, **kwargs):
            if statement.startswith("MERGE"):
                raise RuntimeError("write denied")
            return super().execute_statement(statement, **kwargs)

    store = SqlWarehouseStateStore(_workspace(statements=Denied()), "wh", TABLE, PAIR)
    with pytest.raises(RuntimeError, match="write denied"):
        store.provision()


def test_duplicate_state_rows_are_rejected_at_startup():
    class Duplicates(FakeStatements):
        def execute_statement(self, statement, **kwargs):
            assert statement.startswith("SELECT revision")
            return _ok([["0", "{}"], ["0", "{}"]])

    store = SqlWarehouseStateStore(_workspace(statements=Duplicates()), "wh", TABLE, PAIR)
    with pytest.raises(RuntimeError, match="exactly one"):
        store.provision()


@pytest.mark.parametrize("route", ["bundle", "direct-git"])
def test_databricks_startup_with_empty_table_requires_baselines_and_preserves_them(monkeypatch, route):
    import app
    import databricks.sdk

    secrets = FakeSecrets({
        "my_catalog.my_schema.source-host": "https://source.example",
        "my_catalog.my_schema.target-host": "https://target.example",
    })
    statements = FakeStatements()
    workspace = _workspace(secrets=secrets, statements=statements)
    monkeypatch.setattr(databricks.sdk, "WorkspaceClient", lambda: workspace)
    monkeypatch.setenv("APP_MODE", "live")
    monkeypatch.setenv("VISIER_SECRETS_CATALOG", "my_catalog")
    monkeypatch.setenv("VISIER_SECRETS_SCHEMA", "my_schema")
    monkeypatch.setenv("VISIER_SECRET_PREFIX", "")
    monkeypatch.setenv("SQL_WAREHOUSE_ID", "wh")
    monkeypatch.setenv("PROMOTION_STATE_TABLE", "promotion_state")
    monkeypatch.delenv("PROMOTION_STATE_TABLE_FULL_NAME", raising=False)
    if route == "direct-git":
        monkeypatch.setenv("PROMOTION_STATE_TABLE_FULL_NAME", TABLE)
        for key in ("VISIER_SECRETS_CATALOG", "VISIER_SECRETS_SCHEMA", "PROMOTION_STATE_TABLE"):
            monkeypatch.delenv(key)
    monkeypatch.delenv("INITIAL_SOURCE_VERSION_ID", raising=False)
    monkeypatch.delenv("INITIAL_TARGET_VERSION_ID", raising=False)

    class ReadOnlyGateway:
        def versions(self, role):
            return [{"id": f"{role}-{number}", "number": number, "description": "Version"}
                    for number in (2, 1)]

    # Any attempted tenant mutation fails: this gateway only supports history reads.
    monkeypatch.setattr(app, "VisierGateway", lambda credentials: ReadOnlyGateway())
    entrypoint = str(Path(__file__).resolve().parents[1] / "wsgi.py")
    application = runpy.run_path(entrypoint)["app"]
    assert application.extensions["promotion"].store.table == TABLE
    client = application.test_client()
    response = client.get("/api/state")
    assert response.status_code == 200
    state = response.json
    assert state["checkpoint"] is None
    assert state["issue"] and "baseline" in state["issue"]
    assert not state["can_rollback"]
    assert len(statements.rows) == 1
    assert next(iter(statements.rows.values())) == [0, "{}"]
    assert client.post("/api/sync", json={
        "fingerprint": state["fingerprint"], "version_id": "source-2"}).status_code == 409
    payload = dict(fingerprint=state["fingerprint"], reason="Verified new deployment", verified=True,
                   source_id="source-1")
    assert client.post("/api/rebaseline", json=payload).status_code == 400
    assert client.post("/api/rebaseline", json=dict(payload, target_id="target-2")).status_code == 200
    state = client.get("/api/state").json
    assert state["issue"] is None
    assert state["pending_count"] == 1
    assert state["history"][0]["before"] is None
    saved = dict(statements.rows)

    restarted = runpy.run_path(entrypoint)["app"].test_client()
    assert restarted.get("/api/state").json["checkpoint"] == state["checkpoint"]
    assert statements.rows == saved

    # Changing deployment identity creates a new empty pair, retaining the old one.
    secrets.values["my_catalog.my_schema.source-host"] = "https://new-source.example"
    changed = runpy.run_path(entrypoint)["app"].test_client()
    assert changed.get("/api/state").json["checkpoint"] is None
    assert len(statements.rows) == 2
    assert all(statements.rows[key] == value for key, value in saved.items())


@pytest.mark.parametrize("extra", [{"VISIER_SECRETS_CATALOG": "wrong"},
                                  {"VISIER_SECRETS_SCHEMA": "wrong"},
                                  {"PROMOTION_STATE_TABLE": "wrong"}])
def test_attached_table_rejects_conflicting_explicit_settings(extra):
    with pytest.raises(ValueError, match="conflicts"):
        state_location({"PROMOTION_STATE_TABLE_FULL_NAME": TABLE, **extra})


def test_attached_table_must_be_qualified_and_safe():
    with pytest.raises(ValueError, match="catalog.schema.table"):
        state_location({"PROMOTION_STATE_TABLE_FULL_NAME": "cat.sch.table; DROP TABLE other"})


def test_stale_revision_is_rejected_without_overwriting_newer_state():
    statements = FakeStatements()
    first = SqlWarehouseStateStore(_workspace(statements=statements), "wh", TABLE, PAIR)
    second = SqlWarehouseStateStore(_workspace(statements=statements), "wh", TABLE, PAIR)
    first.provision()
    stale_revision, _ = first.read()
    newer_revision, _ = second.read()
    second.compare_and_swap(newer_revision, {"checkpoint": {"source_id": "newer"}})

    with pytest.raises(AppError, match="State changed in another session"):
        first.compare_and_swap(stale_revision, {"checkpoint": {"source_id": "stale"}})

    _, state = first.read()
    assert state["checkpoint"] == {"source_id": "newer"}


def test_failed_statement_raises_without_exposing_the_document():
    class Failing(FakeStatements):
        def execute_statement(self, statement, warehouse_id, parameters, wait_timeout):
            failed = StatementResponse(statement_id="s", status=StatementStatus(
                state=StatementState.FAILED, error=SimpleNamespace(message="concurrent update")))
            return failed

    store = SqlWarehouseStateStore(_workspace(statements=Failing()), "wh", TABLE, PAIR)

    with pytest.raises(RuntimeError, match="concurrent update"):
        store.read()

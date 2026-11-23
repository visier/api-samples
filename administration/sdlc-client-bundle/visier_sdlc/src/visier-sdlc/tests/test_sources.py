import io
import json
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from urllib3 import HTTPResponse

from app import create_app
from promotion.demo import DemoGateway
from promotion.ports import AppError
from promotion.service import PromotionService
from promotion.storage import SQLiteStateStore
from promotion.visier import VisierGateway


def sources_zip():
    contents = io.BytesIO()
    with zipfile.ZipFile(contents, "w") as archive:
        archive.writestr("sources.json", "[]")
    return contents.getvalue()


@pytest.fixture
def setup(tmp_path):
    store = SQLiteStateStore(str(tmp_path / "sources.sqlite3"), "test")
    gateway = DemoGateway(store)
    app = create_app({"TESTING": True}, store=store, gateway=gateway)
    return app, app.extensions["promotion"], store, gateway


@pytest.fixture
def adapter():
    credentials = SimpleNamespace(configuration=lambda role: dict(
        host=f"https://{role}.example.com", vanity=role, access_token="private-token"))
    return VisierGateway(credentials)


@pytest.mark.parametrize("replace", [False, True])
@pytest.mark.parametrize("override", [False, True])
def test_sdk_source_export_import_transport(adapter, monkeypatch, replace, override):
    archive = sources_zip()
    expected = dict(created=1, updated=2, ignored=3, deleted=4)
    if override:
        adapter.tenant_ids.update(source="development-id", target="production-id")

    def export_response(method, url, **kwargs):
        assert method == "POST"
        assert url == "https://source.example.com/v1beta/admin/sources"
        assert json.loads(kwargs["body"]) == {"operation": "exportSources"}
        assert kwargs["headers"]["Accept"] == "application/zip, application/json"
        assert kwargs["headers"]["Authorization"] == "Bearer private-token"
        assert kwargs["headers"].get("TargetTenantID") == ("development-id" if override else None)
        return HTTPResponse(status=200, body=archive, headers={"Content-Type": "application/zip"})

    def import_response(method, url, **kwargs):
        assert method == "PUT"
        assert url == f"https://target.example.com/v1beta/admin/sources?replaceAllExistingSources={str(replace).lower()}"
        assert kwargs["body"] == archive
        assert kwargs["headers"]["Content-Type"] == "application/zip"
        assert kwargs["headers"].get("TargetTenantID") == ("production-id" if override else None)
        return HTTPResponse(status=200, body=json.dumps({"summary": expected}).encode(),
                            headers={"Content-Type": "application/json"})

    export = Mock(side_effect=export_response)
    upload = Mock(side_effect=import_response)
    monkeypatch.setattr(adapter.clients["source"].rest_client.pool_manager, "request", export)
    monkeypatch.setattr(adapter.clients["target"].rest_client.pool_manager, "request", upload)
    assert adapter.export_sources() == archive
    assert adapter.import_sources(archive, replace) == expected
    export.assert_called_once()
    upload.assert_called_once()


@pytest.mark.parametrize("status,body", [(200, b'{"error":"not a zip"}'), (204, b""), (201, sources_zip())])
def test_invalid_source_exports_release_connection(adapter, monkeypatch, status, body):
    response = Mock(status=status, data=body)
    monkeypatch.setattr(adapter.sdk.SourcesApi, "run_sources_operation_without_preload_content", Mock(return_value=response))
    with pytest.raises(AppError, match="valid sources export ZIP"):
        adapter.export_sources()
    response.release_conn.assert_called_once()


@pytest.mark.parametrize("payload", [{}, {"summary": None}, {"summary": {"created": -1}}])
def test_source_import_requires_confirmed_summary(adapter, monkeypatch, payload):
    monkeypatch.setattr(adapter.clients["target"].rest_client.pool_manager, "request", Mock(return_value=HTTPResponse(
        status=200, body=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})))
    with pytest.raises(AppError, match="summary"):
        adapter.import_sources(sources_zip())


def test_import_summary_defaults_omitted_zero_counters(adapter, monkeypatch):
    monkeypatch.setattr(adapter.clients["target"].rest_client.pool_manager, "request", Mock(return_value=HTTPResponse(
        status=200, body=b'{"summary":{}}', headers={"Content-Type": "application/json"})))
    assert adapter.import_sources(sources_zip()) == dict(created=0, updated=0, ignored=0, deleted=0)


@pytest.mark.parametrize("replace", [False, True])
def test_source_migration_is_independent_of_versions_and_survives_restart(setup, monkeypatch, replace):
    app, service, store, gateway = setup
    before = service.snapshot()
    for name in ("create_project", "upload", "publish", "rollback_project", "export"):
        monkeypatch.setattr(gateway, name, Mock(side_effect=AssertionError("Version operation called")))
    response = app.test_client().post("/api/sources/migrate", json={
        "fingerprint": before["fingerprint"], "replace_all_existing_sources": replace})
    assert response.status_code == 200
    expected = dict(created=1, updated=1, ignored=0, deleted=int(replace))
    assert response.get_json()["summary"] == expected
    after = service.snapshot()
    assert after["checkpoint"] == before["checkpoint"]
    assert after["source"] == before["source"]
    assert after["target"] == before["target"]
    assert after["drift"] == before["drift"]
    assert after["history"][0]["summary"] == expected
    assert after["history"][0]["replace_all_existing_sources"] is replace
    assert after["history"][0]["kind"] == "sources"
    assert after["operation"] is None
    restarted = DemoGateway(SQLiteStateStore(store.path, store.key))
    assert {source["id"] for source in restarted._sources("target")} == (
        {"employees", "movements"} if replace else {"employees", "movements", "production-only"})
    assert restarted.import_sources(restarted.export_sources()) == dict(created=0, updated=0, ignored=2, deleted=0)
    # A previously opened confirmation cannot repeat a completed source import.
    with pytest.raises(AppError, match="state changed"):
        service.migrate_sources(before["fingerprint"])


def test_sources_can_migrate_without_a_version_baseline(setup):
    _, service, store, _ = setup
    revision, state = store.read()
    state.pop("checkpoint")
    store.compare_and_swap(revision, state)
    snapshot = service.snapshot()
    assert snapshot["issue"]
    service.migrate_sources(snapshot["fingerprint"])
    assert "checkpoint" not in store.read()[1]


@pytest.mark.parametrize("payload", [None, [], {}, {"fingerprint": 1},
                                          {"fingerprint": "x", "replace_all_existing_sources": "false"},
                                          {"fingerprint": "x", "replace_all_existing_sources": None},
                                          {"fingerprint": "x", "replace_all_existing_sources": 1}])
def test_invalid_migration_requests_do_not_change_state(setup, payload):
    app, _, store, _ = setup
    before = store.read()
    response = app.test_client().post("/api/sources/migrate", data=json.dumps(payload), content_type="application/json")
    assert response.status_code == 400
    assert store.read() == before


def test_source_migration_request_protection_and_stale_state(setup):
    app, service, store, _ = setup
    client = app.test_client()
    before = store.read()
    payload = {"fingerprint": service.snapshot()["fingerprint"]}
    assert client.post("/api/sources/migrate", json=payload, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.post("/api/sources/migrate", data="{}").status_code == 415
    assert client.post("/api/sources/migrate", json={"fingerprint": "stale"}).status_code == 409
    assert store.read() == before


def test_source_export_failure_is_retryable_and_redacted(setup, monkeypatch):
    _, service, store, gateway = setup
    upload = Mock()
    monkeypatch.setattr(gateway, "import_sources", upload)
    monkeypatch.setattr(gateway, "export_sources", Mock(side_effect=RuntimeError("private-secret")))
    checkpoint = service.snapshot()["checkpoint"]
    with pytest.raises(AppError) as error:
        service.migrate_sources(service.snapshot()["fingerprint"])
    state = store.read()[1]
    assert state["operation"] is None
    assert state["checkpoint"] == checkpoint
    assert state["history"][-1]["status"] == "failed"
    assert "private-secret" not in str(error.value) + str(state)
    upload.assert_not_called()


@pytest.mark.parametrize("outcome", ["--sources-imported", "--not-imported"])
def test_uncertain_source_import_locks_all_operations_until_reconciled(setup, monkeypatch, outcome):
    app, service, store, gateway = setup
    before = service.snapshot()
    original = gateway.import_sources

    def ambiguous(*args, **kwargs):
        original(*args, **kwargs)
        raise TimeoutError("private-secret")

    upload = Mock(side_effect=ambiguous)
    monkeypatch.setattr(gateway, "import_sources", upload)
    with pytest.raises(AppError):
        service.migrate_sources(before["fingerprint"])
    restarted = PromotionService(gateway, SQLiteStateStore(store.path, store.key))
    state = restarted.snapshot()
    assert state["operation"]["status"] == "needs_review"
    assert state["operation"]["step"] == "import_sources"
    assert state["checkpoint"] == before["checkpoint"]
    assert state["target"][0]["status"] == "drift"
    for attempt in (lambda: restarted.migrate_sources(state["fingerprint"]),
                    lambda: restarted.run("rollback", state["fingerprint"]),
                    lambda: restarted.run("sync", state["fingerprint"], "dev-128"),
                    lambda: restarted.rebaseline(state["fingerprint"], source_id="dev-125", reason="Reviewed", verified=True)):
        with pytest.raises(AppError, match="already active"):
            attempt()
    with pytest.raises(AppError, match="target sources"):
        restarted.reconcile(target_id="prod-87")
    with pytest.raises(AppError, match="target sources"):
        restarted.reconcile(not_published=True)
    result = app.test_cli_runner().invoke(args=["reconcile", outcome])
    assert result.exit_code == 0, result.output
    after = restarted.snapshot()
    assert after["checkpoint"] == before["checkpoint"]
    assert after["operation"] is None
    assert after["history"][0]["status"] == ("succeeded" if outcome == "--sources-imported" else "failed")
    assert "private-secret" not in str(store.read())
    upload.assert_called_once()


def test_source_import_transport_failure_is_not_retried(adapter, monkeypatch):
    upload = Mock(side_effect=TimeoutError("private-secret"))
    monkeypatch.setattr(adapter.clients["target"].rest_client.pool_manager, "request", upload)
    with pytest.raises(AppError) as error:
        adapter.import_sources(sources_zip())
    assert "private-secret" not in str(error.value)
    upload.assert_called_once()


def test_source_claim_prevents_concurrent_migrations_and_versions(setup, monkeypatch):
    _, service, store, gateway = setup
    entered, release = threading.Event(), threading.Event()
    original = gateway.export_sources

    def export():
        entered.set()
        assert release.wait(5)
        return original()

    monkeypatch.setattr(gateway, "export_sources", export)
    fingerprint = service.snapshot()["fingerprint"]
    with ThreadPoolExecutor() as pool:
        first = pool.submit(service.migrate_sources, fingerprint)
        assert entered.wait(5)
        other = PromotionService(gateway, SQLiteStateStore(store.path, store.key))
        try:
            with pytest.raises(AppError, match="already active"):
                other.migrate_sources(fingerprint)
            with pytest.raises(AppError, match="already active"):
                other.run("rollback", fingerprint)
        finally:
            release.set()
        first.result()
    assert len(service.snapshot()["history"]) == 1

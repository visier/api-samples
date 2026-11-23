import io
import threading
import zipfile
from concurrent.futures import ThreadPoolExecutor

import pytest

from app import create_app, public_origin
from promotion.demo import DemoGateway
from promotion.ports import AppError
from promotion.service import PromotionService
from promotion.storage import SQLiteStateStore


@pytest.fixture
def setup(tmp_path):
    store = SQLiteStateStore(str(tmp_path / "test.sqlite3"), "test")
    gateway = DemoGateway(store)
    service = PromotionService(gateway, store)
    return service, store, gateway


def clear_drift(service):
    service.run("rollback", service.snapshot()["fingerprint"])


def test_initial_state_has_pending_baseline_and_drift(setup):
    service, _, _ = setup
    state = service.snapshot()
    assert state["pending_count"] == 3
    assert [v["status"] for v in state["source"]] == ["pending", "pending", "pending", "synced"]
    assert state["target"][0]["status"] == "drift"
    assert state["can_rollback"]


def test_drift_blocks_sync(setup):
    service, store, _ = setup
    with pytest.raises(AppError, match="drift"):
        service.run("sync", service.snapshot()["fingerprint"], "dev-128")
    assert store.read()[1]["checkpoint"]["source_id"] == "dev-125"


def test_rollback_publishes_project_and_preserves_source_checkpoint(setup):
    service, store, gateway = setup
    before = gateway.versions("target")[0]["id"]
    last_sync_at = service.snapshot()["checkpoint"]["at"]
    clear_drift(service)
    state = service.snapshot()
    assert not state["drift"]
    assert not state["can_rollback"]
    assert state["checkpoint"]["source_id"] == "dev-125"
    assert state["checkpoint"]["at"] == last_sync_at
    assert state["checkpoint"]["target_id"] != before
    assert state["history"][0]["kind"] == "rollback"
    assert not store.read()[1]["demo"]["drafts"]


def test_partial_sync_includes_older_versions_in_order(setup, monkeypatch):
    service, _, gateway = setup
    clear_drift(service)
    exported = []
    original = gateway.export
    def export(first, last):
        exported.append((first, last))
        return original(first, last)
    monkeypatch.setattr(gateway, "export", export)
    service.run("sync", service.snapshot()["fingerprint"], "dev-127")
    state = service.snapshot()
    assert exported == [("dev-126", "dev-127")]
    assert [(v["id"], v["status"]) for v in state["source"]] == [("dev-128", "pending"), ("dev-127", "synced")]
    assert state["history"][0]["count"] == 2
    assert state["target"][0]["id"] == state["checkpoint"]["target_id"]


def test_all_sync_shows_only_new_baseline(setup):
    service, _, _ = setup
    clear_drift(service)
    service.run("sync", service.snapshot()["fingerprint"], "dev-128")
    state = service.snapshot()
    assert state["pending_count"] == 0
    assert [v["id"] for v in state["source"]] == ["dev-128"]
    assert state["source"][0]["status"] == "synced"


@pytest.mark.parametrize("kind,first_sync", [("sync", False), ("sync", True), ("rollback", False)])
def test_visible_publication_is_not_new_drift_before_checkpoint(setup, monkeypatch, kind, first_sync):
    service, store, gateway = setup
    if first_sync:
        revision, data = store.read()
        data.pop("checkpoint")
        data["demo"]["target"] = []
        store.compare_and_swap(revision, data)
    elif kind == "sync":
        clear_drift(service)
    before = service.snapshot()
    visible, release = threading.Event(), threading.Event()
    original = gateway.publish

    def publish(project_id):
        target_id = original(project_id)
        visible.set()
        assert release.wait(5)
        return target_id

    monkeypatch.setattr(gateway, "publish", publish)
    with ThreadPoolExecutor() as pool:
        operation = pool.submit(service.run, kind, before["fingerprint"], "dev-126" if kind == "sync" else None)
        assert visible.wait(5)
        try:
            # A separate worker/browser sees the durable claim, not local busy state.
            reader = PromotionService(gateway, SQLiteStateStore(store.path, store.key))
            during = reader.snapshot()
            assert during["operation"]["step"] == "publish"
            assert during["checkpoint"] == before["checkpoint"]
            assert during["drift"] == before["drift"]
            assert during["issue"] is None
            assert during["target"][0]["status"] == "unconfirmed"
            assert not during["can_rollback"]
            if kind == "rollback":
                assert during["target"][1]["status"] == "drift"
        finally:
            release.set()
        operation.result()
    after = service.snapshot()
    assert not after["drift"]
    assert not after["operation"]
    assert after["target"][0]["status"] == "synced"


@pytest.mark.parametrize("finish_during_read", [False, True])
def test_refresh_retries_if_operation_changes_during_history_read(setup, monkeypatch, finish_during_read):
    service, _, gateway = setup
    clear_drift(service)
    before = service.snapshot()
    original = gateway.versions
    changed = False

    def versions(role):
        nonlocal changed
        result = original(role)
        if role == "target" and not changed:
            changed = True
            if finish_during_read:
                service.run("sync", before["fingerprint"], "dev-126")
            else:
                gateway.add_drift()
        return result

    monkeypatch.setattr(gateway, "versions", versions)
    after = service.snapshot()
    assert changed
    assert after["issue"] is None
    if finish_during_read:
        assert not after["drift"]
        assert after["checkpoint"]["source_id"] == "dev-126"
        assert after["target"][0]["id"] == after["checkpoint"]["target_id"]
    else:
        assert after["drift"]
        assert after["target"][0]["status"] == "drift"


def test_refresh_retries_are_bounded_when_state_keeps_changing(setup, monkeypatch):
    service, _, gateway = setup
    original = gateway.versions
    reads = []

    def versions(role):
        reads.append(role)
        if role == "target":
            gateway.add_drift()
        return original(role)

    monkeypatch.setattr(gateway, "versions", versions)
    with pytest.raises(AppError, match="changed while refreshing"):
        service.snapshot()
    assert reads == ["source", "target"] * 3


def test_external_change_during_publication_is_detected_after_completion(setup, monkeypatch):
    service, store, gateway = setup
    clear_drift(service)
    original = gateway.publish

    def publish(project_id):
        target_id = original(project_id)
        revision, data = store.read()
        data["demo"]["target"].insert(0, dict(data["demo"]["target"][0], id="external-drift"))
        store.compare_and_swap(revision, data)
        return target_id

    monkeypatch.setattr(gateway, "publish", publish)
    service.run("sync", service.snapshot()["fingerprint"], "dev-126")
    after = service.snapshot()
    assert after["drift"]
    assert after["target"][0]["status"] == "drift"
    assert after["target"][1]["status"] == "synced"
    assert after["can_rollback"]


def test_stale_snapshot_rejected_without_side_effect(setup):
    service, store, gateway = setup
    clear_drift(service)
    fingerprint = service.snapshot()["fingerprint"]
    gateway.add_drift()
    with pytest.raises(AppError, match="changed"):
        service.run("sync", fingerprint, "dev-127")
    assert store.read()[1]["operation"] is None


@pytest.mark.parametrize("version", [None, "dev-125", "does-not-exist"])
def test_invalid_selection(setup, version):
    service, _, _ = setup
    clear_drift(service)
    with pytest.raises(AppError, match="Select"):
        service.run("sync", service.snapshot()["fingerprint"], version)


@pytest.mark.parametrize("stage", ["export", "create_project", "upload"])
def test_preparation_failure_preserves_checkpoint_and_can_retry(setup, monkeypatch, stage):
    service, store, gateway = setup
    clear_drift(service)
    checkpoint = service.snapshot()["checkpoint"]
    def fail(*args):
        raise RuntimeError("credential-bearing error must not reach browser")
    monkeypatch.setattr(gateway, stage, fail)
    with pytest.raises(AppError, match="could not complete"):
        service.run("sync", service.snapshot()["fingerprint"], "dev-128")
    state = store.read()[1]
    assert state["checkpoint"] == checkpoint
    assert state["operation"] is None
    assert state["history"][-1]["status"] == "failed"
    assert "credential" not in str(state["history"][-1])


def test_publish_timeout_locks_until_reconciliation_even_after_restart(setup, monkeypatch):
    service, store, gateway = setup
    clear_drift(service)
    checkpoint = service.snapshot()["checkpoint"]
    original = gateway.publish
    published = []
    def ambiguous(project_id):
        published.append(original(project_id))
        raise TimeoutError("Response lost after successful publication")
    monkeypatch.setattr(gateway, "publish", ambiguous)
    with pytest.raises(AppError):
        service.run("sync", service.snapshot()["fingerprint"], "dev-127")
    assert store.read()[1]["checkpoint"] == checkpoint
    assert store.read()[1]["operation"]["status"] == "needs_review"
    restarted = PromotionService(gateway, store)
    unresolved = restarted.snapshot()
    assert not unresolved["drift"]
    assert unresolved["target"][0]["status"] == "unconfirmed"
    assert not unresolved["can_rollback"]
    with pytest.raises(AppError, match="already active"):
        restarted.run("sync", restarted.snapshot()["fingerprint"], "dev-127")
    restarted.reconcile(target_id=published[0])
    assert restarted.snapshot()["checkpoint"]["source_id"] == "dev-127"
    assert not restarted.snapshot()["operation"]


def test_unconfirmed_versions_become_drift_if_operator_confirms_not_published(setup, monkeypatch):
    service, _, gateway = setup
    clear_drift(service)

    def ambiguous(project_id):
        # An external writer changes production while our publish fails.
        revision, data = gateway.store.read()
        data["demo"]["target"].insert(0, dict(data["demo"]["target"][0], id="external-drift"))
        gateway.store.compare_and_swap(revision, data)
        raise TimeoutError()

    monkeypatch.setattr(gateway, "publish", ambiguous)
    with pytest.raises(AppError):
        service.run("sync", service.snapshot()["fingerprint"], "dev-126")
    assert service.snapshot()["target"][0]["status"] == "unconfirmed"
    service.reconcile(not_published=True)
    after = service.snapshot()
    assert after["drift"]
    assert after["target"][0]["status"] == "drift"
    assert after["can_rollback"]


def test_production_changed_during_import_blocks_publish(setup, monkeypatch):
    service, store, gateway = setup
    clear_drift(service)
    original = gateway.upload
    def upload(project_id, archive):
        original(project_id, archive)
        revision, data = store.read()
        data["demo"]["target"].insert(0, dict(data["demo"]["target"][0], id="external-drift"))
        store.compare_and_swap(revision, data)
        during = service.snapshot()
        assert during["operation"]["step"] == "upload"
        assert during["drift"]
        assert during["target"][0]["status"] == "drift"
    monkeypatch.setattr(gateway, "upload", upload)
    with pytest.raises(AppError, match="changed during preparation"):
        service.run("sync", service.snapshot()["fingerprint"], "dev-128")
    assert service.snapshot()["checkpoint"]["source_id"] == "dev-125"
    assert service.snapshot()["drift"]


def test_concurrent_requests_cannot_claim_same_pair(setup, monkeypatch):
    service, store, gateway = setup
    clear_drift(service)
    entered, release = threading.Event(), threading.Event()
    original = gateway.export
    def export(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)
    monkeypatch.setattr(gateway, "export", export)
    fingerprint = service.snapshot()["fingerprint"]
    with ThreadPoolExecutor() as pool:
        first = pool.submit(service.run, "sync", fingerprint, "dev-127")
        assert entered.wait(5)
        other_service = PromotionService(gateway, SQLiteStateStore(store.path, store.key))
        try:
            with pytest.raises(AppError, match="already active"):
                other_service.run("sync", fingerprint, "dev-128")
        finally:
            release.set()
        first.result()
    assert service.snapshot()["pending_count"] == 1


def test_compare_and_swap_rejects_old_revision(setup):
    _, store, _ = setup
    revision, state = store.read()
    store.compare_and_swap(revision, state)
    with pytest.raises(AppError, match="another session"):
        store.compare_and_swap(revision, state)


def test_missing_checkpoint_version_blocks_operations(setup):
    service, store, _ = setup
    revision, state = store.read()
    state["demo"]["source"].pop()
    store.compare_and_swap(revision, state)
    snapshot = service.snapshot()
    assert "missing" in snapshot["issue"]
    with pytest.raises(AppError, match="missing"):
        service.run("rollback", snapshot["fingerprint"])


def test_fresh_live_target_with_no_checkpoint_can_sync(setup):
    service, store, _ = setup
    revision, state = store.read()
    state.pop("checkpoint")
    state["demo"]["target"] = []
    store.compare_and_swap(revision, state)
    snapshot = service.snapshot()
    assert not snapshot["issue"]
    assert snapshot["pending_count"] == 4
    assert snapshot["next_version_number"] == 1
    service.run("sync", snapshot["fingerprint"], "dev-126")
    assert service.snapshot()["checkpoint"]["source_id"] == "dev-126"
    assert service.snapshot()["target"][0]["number"] == 1


def test_existing_target_requires_verified_baseline(setup):
    service, store, _ = setup
    revision, state = store.read()
    state.pop("checkpoint")
    store.compare_and_swap(revision, state)
    assert "baseline" in service.snapshot()["issue"]


def test_demo_state_survives_new_gateway(setup):
    service, store, gateway = setup
    clear_drift(service)
    service.run("sync", service.snapshot()["fingerprint"], "dev-128")
    assert DemoGateway(SQLiteStateStore(store.path, store.key)).versions("target") == gateway.versions("target")


def test_api_and_request_protection(setup):
    _, store, gateway = setup
    app = create_app({"TESTING": True}, store=store, gateway=gateway)
    client = app.test_client()
    assert client.get("/").status_code == 200
    state = client.get("/api/state").get_json()
    assert client.post("/api/rollback", json={"fingerprint":state["fingerprint"]}).status_code == 200
    assert client.post("/api/sync", json=[]).status_code == 400
    assert client.post("/api/sync", json={}).status_code == 400
    assert client.post("/api/sync", data="{}").status_code == 415
    assert client.post("/api/rollback", json={}, headers={"Origin":"https://evil.example"}).status_code == 403
    response = client.get("/api/state")
    assert response.headers["Cache-Control"] == "no-store"
    assert "frame-ancestors 'none'" in response.headers["Content-Security-Policy"]
    assert client.get("/static/app.js").status_code == 200


@pytest.mark.parametrize("details, expected_name", [
    ({}, "Development tenant promotion"),
    ({"project_name": "  November release · Workforce planning  "}, "November release · Workforce planning"),
    ({"project_name": "N" * 50, "project_description": "Long release notes.\n" * 40}, "N" * 50),
])
def test_sync_api_passes_project_details_to_draft_and_history(setup, monkeypatch, details, expected_name):
    service, store, gateway = setup
    clear_drift(service)
    projects = []
    original = gateway.create_project

    def create_project(name, description, version_number):
        projects.append((name, description, version_number))
        return original(name, description, version_number)

    monkeypatch.setattr(gateway, "create_project", create_project)
    app = create_app({"TESTING": True}, store=store, gateway=gateway)
    response = app.test_client().post("/api/sync", json={
        "fingerprint": service.snapshot()["fingerprint"], "version_id": "dev-126", **details})
    assert response.status_code == 200
    expected_description = details.get("project_description", "")
    assert projects == [(expected_name, expected_description, 89)]
    snapshot = service.snapshot()
    assert snapshot["history"][0]["project_name"] == expected_name
    assert snapshot["history"][0]["project_description"] == expected_description
    assert snapshot["history"][0]["version_number"] == 89
    assert snapshot["target"][0]["number"] == 89
    assert snapshot["target"][0]["description"] == (expected_description or expected_name)


@pytest.mark.parametrize("name", [None, "", " \t\n ", 123, [], {}, "N" * 51])
def test_sync_api_rejects_invalid_display_name_without_changes(setup, name):
    service, store, gateway = setup
    clear_drift(service)
    snapshot = service.snapshot()
    before = store.read()
    app = create_app({"TESTING": True}, store=store, gateway=gateway)
    response = app.test_client().post("/api/sync", json={
        "fingerprint": snapshot["fingerprint"], "version_id": "dev-126", "project_name": name})
    assert response.status_code == 400
    assert "draft project display name" in response.get_json()["error"]
    assert store.read() == before


@pytest.mark.parametrize("description", [None, 123, [], {}])
def test_sync_api_rejects_non_text_description_without_changes(setup, description):
    service, store, gateway = setup
    clear_drift(service)
    before = store.read()
    app = create_app({"TESTING": True}, store=store, gateway=gateway)
    response = app.test_client().post("/api/sync", json={
        "fingerprint": service.snapshot()["fingerprint"], "version_id": "dev-126",
        "project_description": description})
    assert response.status_code == 400
    assert store.read() == before


@pytest.mark.parametrize("previous_number", [None, 0, 42])
def test_sync_increments_latest_production_number_and_ignores_client_override(setup, previous_number):
    service, store, gateway = setup
    clear_drift(service)
    revision, state = store.read()
    state["demo"]["target"][0]["number"] = previous_number
    store.compare_and_swap(revision, state)
    expected = (previous_number or 0) + 1
    app = create_app({"TESTING": True}, store=store, gateway=gateway)
    client = app.test_client()
    for version_id, number in [("dev-126", expected), ("dev-127", expected + 1)]:
        snapshot = client.get("/api/state").get_json()
        assert snapshot["next_version_number"] == number
        response = client.post("/api/sync", json={
            "fingerprint": snapshot["fingerprint"], "version_id": version_id, "version_number": 999})
        assert response.status_code == 200
        assert service.snapshot()["target"][0]["number"] == number


def test_reconcile_cli_requires_one_explicit_resolution(setup):
    _, store, gateway = setup
    app = create_app({"TESTING": True}, store=store, gateway=gateway)
    result = app.test_cli_runner().invoke(args=["reconcile"])
    assert result.exit_code != 0


def test_public_origin_supports_trusted_tls_proxy(setup):
    _, store, gateway = setup
    app = create_app({"TESTING":True, "PUBLIC_ORIGIN":"https://promote.example.com"}, store=store, gateway=gateway)
    client = app.test_client()
    fingerprint = client.get("/api/state").get_json()["fingerprint"]
    assert client.post("/api/rollback", json={"fingerprint":fingerprint}, headers={"Origin":"https://promote.example.com"}).status_code == 200
    assert client.post("/api/demo/drift", json={}, headers={"Origin":"https://evil.example"}).status_code == 403


@pytest.mark.parametrize("with_username", [True, False])
def test_connections_expose_only_display_settings(setup, monkeypatch, with_username):
    _, store, gateway = setup
    monkeypatch.delenv("INITIAL_SOURCE_VERSION_ID", raising=False)
    monkeypatch.delenv("INITIAL_TARGET_VERSION_ID", raising=False)

    class Credentials:
        def configuration(self, role):
            config = dict(host=f"https://{role}.api.example.com", vanity=f"{role}-vanity",
                          password="private-password", api_key="private-api-key",
                          client_id="private-client-id", client_secret="private-client-secret",
                          access_token="private-access-token", asid_token="private-asid-token",
                          tenant_id=f"{role}-tenant-id")
            if with_username:
                config["username"] = f"{role}-api-user"
            return config

    app = create_app({"TESTING": True, "APP_MODE": "live"}, store=store,
                     gateway=gateway, credentials=Credentials())
    response = app.test_client().get("/api/state")
    assert response.status_code == 200
    assert response.get_json()["connections"] == {
        role: dict(host=f"https://{role}.api.example.com", vanity=f"{role}-vanity",
                   username=f"{role}-api-user" if with_username else None)
        for role in ("source", "target")
    }
    assert "private-" not in response.get_data(as_text=True)
    assert "connections" not in store.read()[1]


def test_demo_connections_do_not_read_live_credentials(setup):
    _, store, gateway = setup

    class Credentials:
        def configuration(self, role):
            pytest.fail("Demo connections must not read live credentials")

    app = create_app({"TESTING": True, "APP_MODE": "demo"}, store=store,
                     gateway=gateway, credentials=Credentials())
    response = app.test_client().get("/api/state")
    assert response.status_code == 200
    assert response.get_json()["connections"] == {
        role: dict(host=None, vanity=None, username=None) for role in ("source", "target")
    }


def test_live_mode_rejects_same_tenant(tmp_path):
    class Credentials:
        def configuration(self, role):
            return {"host":"https://same.api.visier.io", "vanity":"same"}
    with pytest.raises(ValueError, match="different tenants"):
        create_app({"APP_MODE":"live", "STATE_DB":str(tmp_path / "live.sqlite3")}, credentials=Credentials())


@pytest.mark.parametrize("env,expected", [
    ({}, ""),
    ({"DATABRICKS_APP_URL": "my-app.databricksapps.com"}, "https://my-app.databricksapps.com"),
    ({"DATABRICKS_APP_URL": "https://my-app.databricksapps.com/some/path/"}, "https://my-app.databricksapps.com"),
    ({"PUBLIC_ORIGIN": "https://override.example.com", "DATABRICKS_APP_URL": "x.example.com"}, "https://override.example.com"),
])
def test_public_origin_resolution(monkeypatch, env, expected):
    monkeypatch.delenv("PUBLIC_ORIGIN", raising=False)
    monkeypatch.delenv("DATABRICKS_APP_URL", raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    assert public_origin() == expected

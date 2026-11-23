import threading
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import Mock

import pytest

from app import create_app
from promotion.demo import DemoGateway
from promotion.ports import AccessDenied, AppError
from promotion.service import PromotionService
from promotion.storage import SQLiteStateStore


@pytest.fixture
def setup(tmp_path):
    store = SQLiteStateStore(str(tmp_path / "recovery.sqlite3"), "recovery")
    gateway = DemoGateway(store)
    service = PromotionService(gateway, store)
    service.run("rollback", service.snapshot()["fingerprint"])
    return service, store, gateway


def fail_publication(setup, monkeypatch, error=None, kind="sync"):
    service, _, gateway = setup
    original = gateway.publish
    monkeypatch.setattr(gateway, "publish", Mock(side_effect=error or TimeoutError("private-detail")))
    with pytest.raises(AppError):
        service.run(kind, service.snapshot()["fingerprint"], "dev-127",
                    project_name="My release", project_description="Release notes")
    monkeypatch.setattr(gateway, "publish", original)
    return service.snapshot()


def recover(service, snapshot, action, **options):
    return service.recover(snapshot["operation"]["id"], snapshot["state_revision"], action,
                           verified=True, **options)


@pytest.mark.parametrize("kind", ["sync", "rollback"])
def test_permission_denial_can_retry_same_draft_after_restart(setup, monkeypatch, kind):
    service, store, gateway = setup
    if kind == "rollback":
        gateway.add_drift()
    before = service.snapshot()["checkpoint"]
    failed = fail_publication(setup, monkeypatch, AccessDenied("Permission denied", 502), kind)
    operation = failed["operation"]
    assert operation["status"] == "retryable"
    assert failed["checkpoint"] == before
    assert "permissions" in operation["message"]
    original = gateway.publish
    publish = Mock(side_effect=original)
    monkeypatch.setattr(gateway, "publish", publish)
    for method in ("export", "upload", "create_project", "rollback_project"):
        monkeypatch.setattr(gateway, method, Mock(side_effect=AssertionError("Must reuse draft")))
    restarted = PromotionService(gateway, store)
    recover(restarted, restarted.snapshot(), "retry")
    publish.assert_called_once_with(operation["project_id"])
    after = restarted.snapshot()
    assert after["operation"] is None
    assert after["checkpoint"]["source_id"] == ("dev-127" if kind == "sync" else before["source_id"])
    assert not after["drift"]
    assert after["history"][0]["status"] == "succeeded"
    assert after["history"][1]["status"] == "failed"
    assert after["history"][0]["previous_operation_id"] == operation["id"]
    if kind == "sync":
        assert after["history"][0]["project_name"] == "My release"
        assert after["history"][0]["project_description"] == "Release notes"


def test_uncertain_legacy_publication_requires_verification_then_can_retry(setup, monkeypatch):
    service, store, gateway = setup
    failed = fail_publication(setup, monkeypatch)
    revision, data = store.read()
    data["operation"]["message"] = "Publication may have completed. Verify the draft in Visier and reconcile before retrying."
    store.compare_and_swap(revision, data)
    failed = service.snapshot()
    publish = Mock(side_effect=gateway.publish)
    monkeypatch.setattr(gateway, "publish", publish)
    for verified in (None, False, "true", 1):
        with pytest.raises(AppError, match="Verify"):
            service.recover(failed["operation"]["id"], failed["state_revision"], "retry", verified=verified)
    publish.assert_not_called()
    recover(service, failed, "retry")
    assert service.snapshot()["pending_count"] == 1
    assert "private-detail" not in str(store.read()[1])


def test_lost_success_response_is_confirmed_without_duplicate_publication(setup, monkeypatch):
    service, _, gateway = setup
    original = gateway.publish
    def lost_response(project_id):
        original(project_id)
        raise TimeoutError()
    monkeypatch.setattr(gateway, "publish", lost_response)
    with pytest.raises(AppError):
        service.run("sync", service.snapshot()["fingerprint"], "dev-127")
    failed = service.snapshot()
    publish = Mock(side_effect=AssertionError("Do not publish twice"))
    monkeypatch.setattr(gateway, "publish", publish)
    with pytest.raises(AppError, match="Production changed"):
        recover(service, failed, "retry")
    with pytest.raises(AppError, match="new production version"):
        recover(service, failed, "published", target_id=failed["operation"]["target_before"])
    recover(service, failed, "published", target_id=failed["target"][0]["id"])
    publish.assert_not_called()
    assert service.snapshot()["pending_count"] == 1
    assert not service.snapshot()["operation"]
    assert not service.snapshot()["drift"]


def test_confirmed_success_with_failed_checkpoint_only_allows_confirmation(setup, monkeypatch):
    service, _, _ = setup
    original = service._finish
    monkeypatch.setattr(service, "_finish", Mock(side_effect=AppError("Storage unavailable")))
    with pytest.raises(AppError):
        service.run("sync", service.snapshot()["fingerprint"], "dev-127")
    monkeypatch.setattr(service, "_finish", original)
    failed = service.snapshot()
    target_id = failed["operation"]["published_target_id"]
    for action in ("discard", "dismiss"):
        with pytest.raises(AppError, match="confirmed publication"):
            recover(service, failed, action)
    recover(service, failed, "published", target_id=target_id)
    assert service.snapshot()["checkpoint"]["target_id"] == target_id


@pytest.mark.parametrize("action", ["discard", "dismiss"])
def test_discard_or_dismiss_unblocks_without_advancing_checkpoint(setup, monkeypatch, action):
    service, store, _ = setup
    failed = fail_publication(setup, monkeypatch)
    project_id = failed["operation"]["project_id"]
    recover(service, failed, action)
    after = service.snapshot()
    assert not after["operation"]
    assert after["checkpoint"] == failed["checkpoint"]
    assert after["pending_count"] == 3
    assert (project_id in store.read()[1]["demo"]["drafts"]) is (action == "dismiss")
    service.run("sync", after["fingerprint"], "dev-127")
    assert service.snapshot()["pending_count"] == 1


@pytest.mark.parametrize("next_action", ["discard", "dismiss"])
def test_failed_deletion_can_be_retried_or_dismissed(setup, monkeypatch, next_action):
    service, store, gateway = setup
    failed = fail_publication(setup, monkeypatch)
    original = gateway.delete_project
    def lost_deletion(project_id):
        original(project_id)
        raise TimeoutError("private-response")
    monkeypatch.setattr(gateway, "delete_project", lost_deletion)
    with pytest.raises(AppError, match="could not complete recovery"):
        recover(service, failed, "discard")
    failed = service.snapshot()
    assert failed["operation"]["step"] == "delete"
    assert failed["operation"]["status"] == "needs_review"
    with pytest.raises(AppError, match="cannot be published again"):
        recover(service, failed, "retry")
    monkeypatch.setattr(gateway, "delete_project", original)
    recover(service, failed, next_action)
    assert not service.snapshot()["operation"]
    assert service.snapshot()["checkpoint"] == failed["checkpoint"]
    assert "private-response" not in str(store.read()[1])


def test_delete_permission_denial_still_allows_dismissal(setup, monkeypatch):
    service, store, gateway = setup
    failed = fail_publication(setup, monkeypatch, AccessDenied("Denied"))
    monkeypatch.setattr(gateway, "delete_project", Mock(side_effect=AccessDenied("Delete denied")))
    with pytest.raises(AppError, match="Delete denied"):
        recover(service, failed, "discard")
    recover(service, service.snapshot(), "dismiss")
    assert not service.snapshot()["operation"]
    assert failed["operation"]["project_id"] in store.read()[1]["demo"]["drafts"]


def test_stale_recovery_does_not_delete_or_publish(setup, monkeypatch):
    service, _, gateway = setup
    failed = fail_publication(setup, monkeypatch)
    recover(service, failed, "dismiss")
    # The tenant histories and fingerprint are unchanged, but this is a new claim.
    replacement = fail_publication(setup, monkeypatch)
    for method in ("publish", "delete_project"):
        monkeypatch.setattr(gateway, method, Mock(side_effect=AssertionError("Stale write")))
    for action in ("retry", "discard", "dismiss"):
        with pytest.raises(AppError, match="operation changed"):
            recover(service, failed, action)
    assert service.snapshot()["operation"] == replacement["operation"]


def test_simultaneous_recovery_is_fenced_and_old_worker_cannot_finish(setup, monkeypatch):
    service, _, gateway = setup
    failed = fail_publication(setup, monkeypatch)
    original = gateway.publish
    entered, release = threading.Event(), threading.Event()
    def publish(project_id):
        entered.set()
        assert release.wait(5)
        return original(project_id)
    monkeypatch.setattr(gateway, "publish", publish)
    with ThreadPoolExecutor(max_workers=1) as pool:
        attempt = pool.submit(recover, service, failed, "retry")
        assert entered.wait(5)
        try:
            with pytest.raises(AppError, match="operation changed"):
                recover(service, failed, "retry")
            with pytest.raises(AppError, match="another session"):
                service._finish(failed["operation"]["id"], "bad-target")
        finally:
            release.set()
        attempt.result(5)
    assert service.snapshot()["pending_count"] == 1


def test_retry_rechecks_production_and_repeated_denial_stays_recoverable(setup, monkeypatch):
    service, store, gateway = setup
    failed = fail_publication(setup, monkeypatch, AccessDenied("Denied"))
    monkeypatch.setattr(gateway, "publish", Mock(side_effect=AccessDenied("Still denied")))
    with pytest.raises(AppError, match="Still denied"):
        recover(service, failed, "retry")
    failed = service.snapshot()
    assert failed["operation"]["status"] == "retryable"
    revision, data = store.read()
    data["demo"]["target"].insert(0, dict(data["demo"]["target"][0], id="external"))
    store.compare_and_swap(revision, data)
    with pytest.raises(AppError, match="Production changed"):
        recover(service, service.snapshot(), "retry")


def test_old_preparation_worker_cannot_clear_a_replacement_claim(setup, monkeypatch):
    service, store, gateway = setup
    def delayed_export(*args):
        # Even if an operator incorrectly asserts that this worker stopped,
        # its later failure must never release a replacement worker's claim.
        recover(service, service.snapshot(), "dismiss")
        revision, data = store.read()
        data["operation"] = dict(id="replacement", kind="sync", status="running", step="export")
        store.compare_and_swap(revision, data)
        raise RuntimeError("Old export failed")
    monkeypatch.setattr(gateway, "export", delayed_export)
    with pytest.raises(AppError, match="ownership changed"):
        service.run("sync", service.snapshot()["fingerprint"], "dev-127")
    assert store.read()[1]["operation"]["id"] == "replacement"


def test_state_change_during_recovery_history_read_blocks_publish(setup, monkeypatch):
    service, store, gateway = setup
    failed = fail_publication(setup, monkeypatch)
    original = gateway.versions
    def versions(role):
        result = original(role)
        revision, data = store.read()
        data["operation"]["status"] = "retryable"
        store.compare_and_swap(revision, data)
        return result
    monkeypatch.setattr(gateway, "versions", versions)
    publish = Mock()
    monkeypatch.setattr(gateway, "publish", publish)
    with pytest.raises(AppError, match="operation changed"):
        recover(service, failed, "retry")
    publish.assert_not_called()


def test_retry_timeout_after_success_can_be_confirmed(setup, monkeypatch):
    service, _, gateway = setup
    failed = fail_publication(setup, monkeypatch, AccessDenied("Denied"))
    original = gateway.publish
    def lost_response(project_id):
        original(project_id)
        raise TimeoutError()
    monkeypatch.setattr(gateway, "publish", lost_response)
    with pytest.raises(AppError):
        recover(service, failed, "retry")
    failed = service.snapshot()
    assert failed["operation"]["status"] == "needs_review"
    recover(service, failed, "published", target_id=failed["target"][0]["id"])
    assert service.snapshot()["pending_count"] == 1


def test_crash_before_draft_id_can_be_dismissed(setup):
    service, store, _ = setup
    revision, data = store.read()
    data["operation"] = dict(id="crashed", kind="sync", status="running", step="create", project_id=None)
    store.compare_and_swap(revision, data)
    snapshot = service.snapshot()
    with pytest.raises(AppError, match="No draft ID"):
        recover(service, snapshot, "discard")
    recover(service, snapshot, "dismiss")
    assert service.snapshot()["operation"] is None


def test_recovery_endpoint_validation_and_legacy_operation(setup, monkeypatch):
    service, store, gateway = setup
    failed = fail_publication(setup, monkeypatch)
    app = create_app({"TESTING": True}, store=store, gateway=gateway)
    client = app.test_client()
    payload = dict(operation_id=failed["operation"]["id"], state_revision=failed["state_revision"],
                   action="discard", verified=True)
    for invalid in (None, [], {}, dict(payload, state_revision=True), dict(payload, action=[])):
        assert client.post("/api/operations/recover", json=invalid, content_type="application/json").status_code == 400
    assert client.post("/api/operations/recover", json=dict(payload, verified=False)).status_code == 400
    assert client.post("/api/operations/recover", json=dict(payload, action="unknown")).status_code == 400
    assert client.post("/api/operations/recover", json=payload, headers={"Origin":"https://other.example"}).status_code == 403
    assert client.post("/api/operations/recover", json=payload).status_code == 200
    assert client.get("/api/state").json["operation"] is None


def test_source_import_cannot_use_version_recovery(setup):
    service, store, _ = setup
    revision, data = store.read()
    data["operation"] = dict(id="sources", kind="sources", status="needs_review", step="import_sources")
    store.compare_and_swap(revision, data)
    with pytest.raises(AppError, match="Source imports"):
        recover(service, service.snapshot(), "dismiss")

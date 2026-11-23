import pytest

from app import create_app
from promotion.demo import DemoGateway
from promotion.ports import AppError
from promotion.service import PromotionService
from promotion.storage import SQLiteStateStore


@pytest.fixture
def setup(tmp_path, monkeypatch):
    store = SQLiteStateStore(str(tmp_path / 'rebaseline.sqlite3'), 'test')
    gateway = DemoGateway(store)
    service = PromotionService(gateway, store)
    # Re-baselining must never call a tenant mutation or export method.
    def unexpected(*args):
        pytest.fail('Re-baselining contacted a tenant write/export method')
    for name in ('export', 'create_project', 'upload', 'publish', 'rollback_project'):
        monkeypatch.setattr(gateway, name, unexpected)
    return service, store, gateway


def reset(service, **changes):
    return service.rebaseline(service.snapshot()['fingerprint'], reason='Verified external fix', verified=True, **changes)


@pytest.mark.parametrize('changes,source,target,pending,drift,scope', [
    ({'source_id': 'dev-127'}, 'dev-127', 'prod-86', 1, True, 'source'),
    ({'target_id': 'prod-87'}, 'dev-125', 'prod-87', 3, False, 'target'),
    ({'source_id': 'dev-127', 'target_id': 'prod-87'}, 'dev-127', 'prod-87', 1, False, 'both'),
    ({'target_id': 'prod-85'}, 'dev-125', 'prod-85', 3, True, 'target'),
])
def test_reset_scopes_persist_and_audit_without_changing_tenants(setup, changes, source, target, pending, drift, scope):
    service, store, gateway = setup
    before = store.read()[1]
    reset(service, **changes)
    restarted = PromotionService(gateway, SQLiteStateStore(store.path, store.key))
    after = restarted.snapshot()
    saved = store.read()[1]
    assert saved['demo'] == before['demo']
    assert saved['managed_target_ids'] == before['managed_target_ids']
    assert after['checkpoint']['source_id'] == source
    assert after['checkpoint']['target_id'] == target
    assert after['checkpoint']['at'] is None
    assert after['checkpoint']['rebaselined_at']
    assert after['pending_count'] == pending
    assert after['drift'] is drift
    record = after['history'][0]
    assert record['kind'] == 'rebaseline'
    assert record['scope'] == scope
    assert record['reason'] == 'Verified external fix'
    assert record['verified'] is True
    assert record['before'] == before['checkpoint']
    assert record['after'] == after['checkpoint']
    assert saved['history'][:-1] == before['history']


def test_full_histories_allow_rewinding_a_hidden_source_baseline(setup):
    service, _, _ = setup
    reset(service, source_id='dev-128', target_id='prod-87')
    snapshot = service.snapshot()
    assert len(snapshot['source']) == 1
    assert len(snapshot['baseline_versions']['source']) == 4
    reset(service, source_id='dev-125')
    assert service.snapshot()['pending_count'] == 3
    assert service.snapshot()['checkpoint']['target_id'] == 'prod-87'


def test_missing_checkpoint_can_be_established_only_with_two_versions(setup):
    service, store, _ = setup
    revision, state = store.read()
    state.pop('checkpoint')
    store.compare_and_swap(revision, state)
    with pytest.raises(AppError, match='Both baselines'):
        reset(service, source_id='dev-127')
    reset(service, source_id='dev-127', target_id='prod-87')
    assert not service.snapshot()['issue']


def test_missing_saved_versions_can_be_repaired_but_not_preserved(setup):
    service, store, _ = setup
    revision, state = store.read()
    state['checkpoint'].update(source_id='missing-source', target_id='missing-target')
    store.compare_and_swap(revision, state)
    with pytest.raises(AppError, match='Both baselines'):
        reset(service, target_id='prod-87')
    reset(service, source_id='dev-126', target_id='prod-87')
    assert not service.snapshot()['issue']


@pytest.mark.parametrize('changes', [
    {}, {'source_id': ''}, {'target_id': 'missing'}, {'source_id': 123},
    {'target_id': []}, {'source_id': 'prod-87'}, {'source_id': 'dev-125'},
])
def test_invalid_selection_does_not_change_state(setup, changes):
    service, store, _ = setup
    before = store.read()
    with pytest.raises(AppError):
        reset(service, **changes)
    assert store.read() == before


@pytest.mark.parametrize('reason,verified', [('', True), ('   ', True), (None, True), (123, True), ('x' * 1001, True), ('Fix', False), ('Fix', 'true'), ('Fix', 1)])
def test_reset_requires_reason_and_explicit_verification(setup, reason, verified):
    service, store, _ = setup
    before = store.read()
    with pytest.raises(AppError):
        service.rebaseline(service.snapshot()['fingerprint'], source_id='dev-127', reason=reason, verified=verified)
    assert store.read() == before


def test_stale_confirmation_rejected(setup):
    service, store, gateway = setup
    fingerprint = service.snapshot()['fingerprint']
    gateway.add_drift()
    before = store.read()
    with pytest.raises(AppError, match='changed'):
        service.rebaseline(fingerprint, target_id='prod-87', reason='External fix', verified=True)
    assert store.read() == before


@pytest.mark.parametrize('status', ['running', 'needs_review'])
def test_active_operation_cannot_be_cleared_by_reset(setup, status):
    service, store, _ = setup
    revision, state = store.read()
    state['operation'] = dict(id='unresolved', kind='sync', step='publish', status=status, target_before='prod-87')
    store.compare_and_swap(revision, state)
    before = store.read()
    with pytest.raises(AppError, match='Reconcile'):
        reset(service, target_id='prod-87')
    assert store.read() == before


def test_competing_state_update_wins_without_being_overwritten(setup, monkeypatch):
    service, store, _ = setup
    original = store.compare_and_swap
    def competing_write(revision, state):
        other_revision, other = store.read()
        other['operation'] = dict(id='new-operation', kind='sync', step='export', status='running')
        original(other_revision, other)
        original(revision, state)
    monkeypatch.setattr(store, 'compare_and_swap', competing_write)
    with pytest.raises(AppError, match='another session'):
        reset(service, target_id='prod-87')
    saved = store.read()[1]
    assert saved['operation']['id'] == 'new-operation'
    assert saved['checkpoint']['target_id'] == 'prod-86'
    assert saved['history'] == []


def test_reset_api_validation_and_origin_protection(setup):
    _, store, gateway = setup
    app = create_app({'TESTING': True}, store=store, gateway=gateway)
    client = app.test_client()
    payload = dict(fingerprint=client.get('/api/state').json['fingerprint'], target_id='prod-87', reason='External fix', verified=True)
    before = store.read()
    assert client.post('/api/rebaseline', json=payload, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.post('/api/rebaseline', json=[]).status_code == 400
    assert client.post('/api/rebaseline', json={}).status_code == 400
    assert client.post('/api/rebaseline', json=dict(payload, verified=False)).status_code == 400
    assert store.read() == before
    assert client.post('/api/rebaseline', json=payload).status_code == 200
    assert client.get('/api/state').json['drift'] is False


def test_sync_after_reset_promotes_only_versions_newer_than_source_baseline(setup, monkeypatch):
    service, _, gateway = setup
    reset(service, source_id='dev-127', target_id='prod-87')
    monkeypatch.undo()
    exported = []
    original = gateway.export
    def export(first, last):
        exported.append((first, last))
        return original(first, last)
    monkeypatch.setattr(gateway, 'export', export)
    service.run('sync', service.snapshot()['fingerprint'], 'dev-128')
    after = service.snapshot()
    assert exported == [('dev-128', 'dev-128')]
    assert after['pending_count'] == 0
    assert not after['drift']
    assert after['checkpoint']['at']
    assert 'rebaselined_at' not in after['checkpoint']
    assert [record['kind'] for record in after['history']] == ['sync', 'rebaseline']


def test_rollback_after_reset_uses_new_target_baseline_and_preserves_source_assertion(setup, monkeypatch):
    service, _, gateway = setup
    reset(service, source_id='dev-127', target_id='prod-87')
    baseline = service.snapshot()['checkpoint']
    monkeypatch.undo()
    gateway.add_drift()
    rolled_back = []
    original = gateway.rollback_project
    def rollback(version):
        rolled_back.append(version)
        return original(version)
    monkeypatch.setattr(gateway, 'rollback_project', rollback)
    service.run('rollback', service.snapshot()['fingerprint'])
    after = service.snapshot()
    assert rolled_back == ['prod-87']
    assert after['checkpoint']['source_id'] == 'dev-127'
    assert after['checkpoint']['rebaselined_at'] == baseline['rebaselined_at']
    assert after['checkpoint']['at'] is None
    assert not after['drift']


def test_restoring_previous_baseline_reinstates_known_drift_and_allows_rollback(setup, monkeypatch):
    service, _, _ = setup
    original = service.snapshot()['checkpoint']
    reset(service, target_id='prod-87')
    accepted = service.snapshot()
    assert not accepted['drift']
    assert not accepted['can_rollback']
    previous = accepted['history'][0]['before']
    assert previous == original
    reset(service, source_id=previous['source_id'], target_id=previous['target_id'])
    restored = service.snapshot()
    assert restored['drift']
    assert restored['can_rollback']
    assert restored['target'][0]['id'] == 'prod-87'
    assert restored['target'][0]['status'] == 'drift'
    assert restored['pending_count'] == accepted['pending_count']
    with pytest.raises(AppError, match='drift'):
        service.run('sync', restored['fingerprint'], 'dev-128')
    assert restored['history'][0]['before'] == accepted['checkpoint']
    assert restored['history'][1]['before'] == original
    monkeypatch.undo()
    service.run('rollback', restored['fingerprint'])
    assert not service.snapshot()['drift']
    assert service.snapshot()['history'][0]['kind'] == 'rollback'


def test_failed_sync_after_accepting_drift_preserves_baseline_restore_history(setup, monkeypatch):
    service, _, gateway = setup
    reset(service, target_id='prod-87')
    previous = service.snapshot()['history'][0]['before']
    monkeypatch.undo()
    def conflict(*args):
        raise AppError('Import found a merge conflict')
    monkeypatch.setattr(gateway, 'upload', conflict)
    with pytest.raises(AppError, match='merge conflict'):
        service.run('sync', service.snapshot()['fingerprint'], 'dev-127')
    failed = service.snapshot()
    assert failed['history'][0]['status'] == 'failed'
    latest_reset = next(record for record in failed['history'] if record['kind'] == 'rebaseline')
    assert latest_reset['before'] == previous
    assert latest_reset['after'] == failed['checkpoint']
    reset(service, source_id=previous['source_id'], target_id=previous['target_id'])
    restored = service.snapshot()
    assert restored['drift']
    assert restored['can_rollback']
    assert [record['kind'] for record in restored['history']] == ['rebaseline', 'sync', 'rebaseline']

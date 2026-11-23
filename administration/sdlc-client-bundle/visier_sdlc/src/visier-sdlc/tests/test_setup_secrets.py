from types import SimpleNamespace

import pytest
from databricks.sdk.errors import NotFound, PermissionDenied

from scripts.setup_secrets import grant_secret_access, secret_values, upsert_secrets


def make_workspace(names, existing=()):
    calls, created, updated = [], [], []

    def get_secret(full_name):
        if full_name.rsplit(".", 1)[1] not in existing:
            raise NotFound("x")

    secrets = SimpleNamespace(
        list_secrets=lambda catalog_name, schema_name: [SimpleNamespace(name=n) for n in names],
        get_secret=get_secret,
        create_secret=lambda s: created.append((s.name, s.value)),
        update_secret=lambda full, s, mask: updated.append((full, s.value)),
    )
    api = SimpleNamespace(do=lambda method, path, body=None: calls.append((method, path, body)))
    return SimpleNamespace(api_client=api, secrets_uc=secrets), calls, created, updated


def test_secret_values_maps_env_to_names_and_skips_empty():
    env = {"SECRET_SOURCE_HOST": "https://a", "SECRET_TARGET_USERNAME": "k", "SECRET_SOURCE_PASSWORD": ""}
    assert secret_values(env, "p-") == {"p-source-host": "https://a", "p-target-username": "k"}


def test_upsert_creates_missing_and_updates_existing():
    ws, _, created, updated = make_workspace([], existing=["p-source-host"])
    upsert_secrets(ws, "cat", "sch", {"p-source-host": "new", "p-target-host": "t"})
    assert created == [("p-target-host", "t")]
    assert updated == [("cat.sch.p-source-host", "new")]


def test_grants_read_secret_only_on_prefixed_secrets():
    ws, calls, *_ = make_workspace(["p-source-host", "p-target-host", "p-source-password", "other"])
    granted = grant_secret_access(ws, "cat", "sch", "p-", "sp-id")
    assert granted == ["p-source-host", "p-source-password", "p-target-host"]
    paths = [c[1] for c in calls]
    assert all("other" not in p for p in paths)
    assert "/api/2.1/unity-catalog/permissions/secret/cat.sch.p-source-password" in paths
    assert calls[-1][2] == {"changes": [{"principal": "sp-id", "add": ["READ_SECRET"]}]}
    assert paths[0].endswith("/catalog/cat") and paths[1].endswith("/schema/cat.sch")


def test_missing_host_secret_fails_before_granting():
    ws, calls, *_ = make_workspace(["p-source-host"])
    with pytest.raises(RuntimeError, match="p-target-host"):
        grant_secret_access(ws, "cat", "sch", "p-", "sp-id")
    assert calls == []


def test_catalog_grant_failure_only_warns(capsys):
    ws, calls, *_ = make_workspace(["p-source-host", "p-target-host"])

    def do(method, path, body=None):
        if "/catalog/" in path:
            raise PermissionDenied("not allowed")
        calls.append(path)

    ws.api_client.do = do
    assert grant_secret_access(ws, "cat", "sch", "p-", "sp-id") == ["p-source-host", "p-target-host"]
    assert "WARNING: could not grant USE_CATALOG" in capsys.readouterr().err
    assert any(p.endswith("secret/cat.sch.p-target-host") for p in calls)


def test_schema_grant_failure_still_raises():
    ws, *_ = make_workspace(["p-source-host", "p-target-host"])

    def do(method, path, body=None):
        if "/schema/" in path:
            raise PermissionDenied("nope")

    ws.api_client.do = do
    with pytest.raises(PermissionDenied):
        grant_secret_access(ws, "cat", "sch", "p-", "sp-id")

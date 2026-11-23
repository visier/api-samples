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


def test_grants_read_secret_only_on_supported_prefixed_secrets():
    ws, calls, *_ = make_workspace(["p-source-host", "p-target-host", "p-source-password", "other",
                                   "p-source-api-key", "p-source-client-id", "p-source-client-secret",
                                   "p-source-access-token", "p-source-asid-token", "p-unrelated"])
    granted = grant_secret_access(ws, "cat", "sch", "p-", "sp-id")
    assert granted == ["p-source-host", "p-source-password", "p-target-host"]
    paths = [c[1] for c in calls]
    assert all("other" not in p for p in paths)
    assert all(not path.endswith(("api-key", "client-id", "client-secret", "access-token", "asid-token", "unrelated"))
               for path in paths)
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


def test_standalone_ui_setup_accepts_the_same_bundle_environment(monkeypatch):
    from scripts import setup_secrets

    ws, calls, created, _ = make_workspace(["team-source-host", "team-target-host"])
    ws.apps = SimpleNamespace(get=lambda name: SimpleNamespace(service_principal_client_id="sp-id")
                              if name == "customer-app" else pytest.fail("wrong app"))
    monkeypatch.setattr(setup_secrets, "WorkspaceClient", lambda: ws)
    setup_secrets.main({
        "BUNDLE_VAR_catalog_name": "cat", "BUNDLE_VAR_schema_name": "sch",
        "BUNDLE_VAR_app_name": "customer-app", "BUNDLE_VAR_secret_prefix": "team-",
        "BUNDLE_VAR_secret_source_host": "https://source.example",
        "BUNDLE_VAR_secret_target_host": "https://target.example",
    })
    assert created == [("team-source-host", "https://source.example"),
                       ("team-target-host", "https://target.example")]
    assert any(call[1].endswith("secret/cat.sch.team-target-host") for call in calls)
    assert calls[-1][1].endswith("table/cat.sch.promotion_state")
    assert calls[-1][2]["changes"][0]["add"] == ["SELECT", "MODIFY"]


@pytest.mark.parametrize("name,variable", [
    ("CATALOG", "catalog_name"), ("SCHEMA", "schema_name"),
    ("PREFIX", "secret_prefix"), ("APP_NAME", "app_name"), ("TABLE", "state_table_name"),
    *[(f"SECRET_{role}_{field}".upper(), f"secret_{role}_{field}")
      for role in ("source", "target") for field in ("host", "vanity", "username", "password")],
])
@pytest.mark.parametrize("ambient", ["different-private-value", ""])
def test_conflicting_inputs_fail_before_connecting(monkeypatch, name, variable, ambient):
    from scripts import setup_secrets

    monkeypatch.setattr(setup_secrets, "WorkspaceClient", lambda: pytest.fail("Must validate before connecting"))
    with pytest.raises(ValueError, match=f"Conflicting values for {name} and BUNDLE_VAR_{variable}") as caught:
        setup_secrets.main({name: ambient, f"BUNDLE_VAR_{variable}": "private-value"})
    assert "private-value" not in str(caught.value)


def test_equal_duplicate_inputs_and_custom_table_are_accepted(monkeypatch):
    from scripts import setup_secrets

    ws, calls, *_ = make_workspace(["visier-sdlc-source-host", "visier-sdlc-target-host"])
    ws.apps = SimpleNamespace(get=lambda name: SimpleNamespace(service_principal_client_id="sp-id"))
    monkeypatch.setattr(setup_secrets, "WorkspaceClient", lambda: ws)
    setup_secrets.main({
        "CATALOG": "cat", "BUNDLE_VAR_catalog_name": "cat",
        "SCHEMA": "sch", "BUNDLE_VAR_schema_name": "sch",
        "APP_NAME": "app", "BUNDLE_VAR_app_name": "app",
        "TABLE": "custom_state", "BUNDLE_VAR_state_table_name": "custom_state",
    })
    assert calls[-1][1].endswith("table/cat.sch.custom_state")

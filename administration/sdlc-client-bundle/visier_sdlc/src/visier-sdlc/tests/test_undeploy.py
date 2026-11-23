import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from databricks.sdk.errors import NotFound, PermissionDenied

from scripts import undeploy


@pytest.fixture
def teardown(monkeypatch):
    summary = {
        "bundle": {"name": "visier_sdlc", "target": "default"},
        "workspace": {"host": "https://bundle.example", "profile": "customer"},
        "variables": {key: {"value": value} for key, value in {
            "catalog_name": "customer", "schema_name": "apps", "state_table_name": "custom_state",
            "secret_prefix": "team-", "app_name": "my-app",
        }.items()},
        "resources": {"apps": {"visier_sdlc_app": {"id": "my-app"}}},
    }
    events = []
    workspace = Mock()
    workspace.config.host = "https://bundle.example"
    workspace.apps.get.return_value = SimpleNamespace(service_principal_client_id="app-principal")
    workspace.api_client.do.side_effect = lambda *a, **k: events.append(("revoke", a, k))
    workspace.secrets_uc.delete_secret.side_effect = lambda name: events.append(("secret", name))
    workspace.tables.delete.side_effect = lambda name: events.append(("table", name))
    factory = Mock(return_value=workspace)
    run = Mock(side_effect=lambda *a, **k: events.append(("destroy", a, k)))
    monkeypatch.setattr(undeploy, "bundle_json", Mock(return_value=summary))
    monkeypatch.setattr(undeploy, "WorkspaceClient", factory)
    monkeypatch.setattr(undeploy.subprocess, "run", run)
    return SimpleNamespace(summary=summary, workspace=workspace, factory=factory, run=run, events=events)


def test_full_cleanup_revokes_then_destroys_then_deletes_data(teardown):
    undeploy.undeploy(yes=True)
    teardown.factory.assert_called_once_with(host="https://bundle.example", profile="customer")
    kinds = [event[0] for event in teardown.events]
    assert kinds == ["revoke"] * 12 + ["destroy"] + ["secret"] * 8 + ["table"]
    assert teardown.run.call_args.args[0] == ["databricks", "bundle", "destroy", "--auto-approve"]
    assert {event[1] for event in teardown.events if event[0] == "secret"} == {
        f"customer.apps.team-{role}-{field}"
        for role in ("source", "target") for field in ("host", "vanity", "username", "password")
    }
    teardown.workspace.tables.delete.assert_called_once_with("customer.apps.custom_state")
    for call in teardown.workspace.api_client.do.call_args_list:
        assert call.args[0] == "PATCH"
        change, = call.kwargs["body"]["changes"]
        assert change["principal"] == "app-principal"
        assert "remove" in change and "add" not in change
        assert "USE_CATALOG" not in change["remove"]
        assert "/permissions/catalog/" not in call.args[1]
    # Manually created tenant-id secrets keep their values but lose the app's grants.
    assert any("team-source-tenant-id" in c.args[1] for c in teardown.workspace.api_client.do.call_args_list)


def test_dry_run_never_mutates(teardown, capsys):
    undeploy.undeploy(dry_run=True)
    teardown.workspace.apps.get.assert_not_called()
    teardown.run.assert_not_called()
    assert teardown.events == []
    assert "ALL promotion history: customer.apps.custom_state" in capsys.readouterr().out


@pytest.mark.parametrize("answer", ["no", "", "yes"])
def test_declining_confirmation_has_no_side_effects(teardown, monkeypatch, answer):
    monkeypatch.setattr("builtins.input", lambda prompt: answer)
    with pytest.raises(ValueError, match="cancelled"):
        undeploy.undeploy()
    teardown.workspace.apps.get.assert_not_called()
    assert teardown.events == []


def test_explicit_confirmation_runs_cleanup(teardown, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda prompt: "undeploy")
    undeploy.undeploy()
    teardown.run.assert_called_once()


def test_failed_destroy_preserves_table_and_secrets(teardown):
    teardown.run.side_effect = subprocess.CalledProcessError(1, "destroy")
    with pytest.raises(subprocess.CalledProcessError):
        undeploy.undeploy(yes=True)
    teardown.workspace.tables.delete.assert_not_called()
    teardown.workspace.secrets_uc.delete_secret.assert_not_called()


def test_permission_failure_is_not_treated_as_missing(teardown):
    teardown.workspace.apps.get.side_effect = PermissionDenied("denied")
    with pytest.raises(PermissionDenied):
        undeploy.undeploy(yes=True)
    teardown.run.assert_not_called()
    assert teardown.events == []


def test_missing_app_and_data_allow_partial_cleanup_to_be_retried(teardown):
    teardown.workspace.apps.get.side_effect = NotFound("already deleted")
    teardown.workspace.secrets_uc.delete_secret.side_effect = NotFound("already deleted")
    teardown.workspace.tables.delete.side_effect = NotFound("already deleted")
    undeploy.undeploy(yes=True)
    teardown.workspace.api_client.do.assert_not_called()
    teardown.run.assert_called_once()
    assert teardown.workspace.secrets_uc.delete_secret.call_count == 8
    teardown.workspace.tables.delete.assert_called_once()


def test_missing_grant_targets_are_harmless(teardown):
    teardown.workspace.api_client.do.side_effect = NotFound("already deleted")
    undeploy.undeploy(yes=True)
    assert teardown.workspace.api_client.do.call_count == 12
    teardown.run.assert_called_once()


def test_untracked_app_is_not_touched(teardown):
    teardown.summary["resources"]["apps"]["visier_sdlc_app"].pop("id")
    undeploy.undeploy(yes=True)
    teardown.workspace.apps.get.assert_not_called()
    teardown.workspace.api_client.do.assert_not_called()


def test_changed_app_name_stops_before_mutations(teardown):
    teardown.summary["variables"]["app_name"]["value"] = "other-app"
    with pytest.raises(ValueError, match="original variables"):
        undeploy.undeploy(yes=True)
    teardown.factory.assert_not_called()
    teardown.run.assert_not_called()


@pytest.mark.parametrize("key,value", [
    ("catalog_name", "other.schema"), ("schema_name", "schema/table"),
    ("state_table_name", "table; DROP TABLE other"), ("secret_prefix", "../"),
])
def test_invalid_cleanup_names_fail_before_mutations(teardown, key, value):
    teardown.summary["variables"][key]["value"] = value
    with pytest.raises(ValueError):
        undeploy.undeploy(yes=True)
    teardown.factory.assert_not_called()


def test_only_explicit_force_lock_is_forwarded(teardown):
    undeploy.undeploy(yes=True, force_lock=True)
    assert teardown.run.call_args.args[0][-1] == "--force-lock"


def test_unified_authentication_can_supply_the_host(teardown, capsys):
    teardown.summary["workspace"] = {}
    undeploy.undeploy(dry_run=True)
    teardown.factory.assert_called_once_with()
    assert "Workspace: https://bundle.example" in capsys.readouterr().out
    assert teardown.events == []


def test_environment_excludes_tenant_credentials_but_keeps_prefix_and_auth(monkeypatch):
    monkeypatch.setenv("BUNDLE_VAR_secret_source_password", "private-value")
    monkeypatch.setenv("BUNDLE_VAR_secret_target_host", "https://private.example")
    monkeypatch.setenv("BUNDLE_VAR_secret_prefix", "team-")
    monkeypatch.setenv("DATABRICKS_CONFIG_PROFILE", "customer")
    env = undeploy.cli_env()
    assert "BUNDLE_VAR_secret_source_password" not in env
    assert "BUNDLE_VAR_secret_target_host" not in env
    assert env["BUNDLE_VAR_secret_prefix"] == "team-"
    assert env["DATABRICKS_CONFIG_PROFILE"] == "customer"

import json
import subprocess
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from databricks.sdk.errors import NotFound, PermissionDenied

from scripts import prepare_deploy


def setup_commands(monkeypatch, apps):
    summary = {
        "workspace": {"host": "https://bundle.example", "profile": "customer"},
        "resources": {"apps": apps, "jobs": {"setup": {"id": "job-123"}}},
    }
    run = Mock(return_value=SimpleNamespace(stdout=json.dumps(summary)))
    client = Mock()
    factory = Mock(return_value=client)
    monkeypatch.setattr(prepare_deploy.subprocess, "run", run)
    monkeypatch.setattr(prepare_deploy, "WorkspaceClient", factory)
    return run, client, factory


def test_deleted_app_unbinds_only_its_resource_key(monkeypatch):
    run, client, factory = setup_commands(monkeypatch, {
        "visier_sdlc_app": {"id": "old-name", "name": "new-name"},
        "other_app": {"id": "keep-me"},
    })
    client.apps.get.side_effect = [NotFound("deleted"), SimpleNamespace()]
    prepare_deploy.prepare_deploy()
    factory.assert_called_once_with(host="https://bundle.example", profile="customer")
    assert [call.args for call in client.apps.get.call_args_list] == [("old-name",), ("keep-me",)]
    assert run.call_count == 2
    run.assert_called_with(
        ["databricks", "bundle", "deployment", "unbind", "visier_sdlc_app"], check=True,
    )
    assert run.call_args_list[0].args[0] == [
        "databricks", "bundle", "summary", "--force-pull", "--output", "json",
    ]


def test_existing_app_is_left_bound(monkeypatch):
    run, client, _ = setup_commands(monkeypatch, {"app": {"id": "existing"}})
    prepare_deploy.prepare_deploy()
    client.apps.get.assert_called_once_with("existing")
    assert run.call_count == 1


@pytest.mark.parametrize("apps", [{}, {"app": {"name": "new-app"}}])
def test_first_deployment_needs_no_repair(monkeypatch, apps):
    run, _, factory = setup_commands(monkeypatch, apps)
    prepare_deploy.prepare_deploy()
    factory.assert_not_called()
    assert run.call_count == 1


@pytest.mark.parametrize("error", [PermissionDenied("denied"), TimeoutError("unreachable")])
def test_lookup_errors_stop_deployment_without_unbinding(monkeypatch, error):
    run, client, _ = setup_commands(monkeypatch, {"app": {"id": "existing"}})
    client.apps.get.side_effect = error
    with pytest.raises(type(error)):
        prepare_deploy.prepare_deploy()
    assert run.call_count == 1


def test_unbind_failure_stops_deployment(monkeypatch):
    run, client, _ = setup_commands(monkeypatch, {"app": {"id": "deleted"}})
    client.apps.get.side_effect = NotFound("deleted")
    run.side_effect = [run.return_value, subprocess.CalledProcessError(1, "unbind")]
    with pytest.raises(subprocess.CalledProcessError):
        prepare_deploy.prepare_deploy()

import io
import zipfile
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import visier_platform_sdk as sdk
from urllib3 import HTTPResponse

from promotion.ports import AppError
from promotion.visier import VisierGateway


def oauth_response(token):
    return HTTPResponse(status=200, body=(
        '{"access_token":"%s","refresh_token":"refresh-%s","id_token":"id-token",'
        '"expires_in":3600,"token_type":"Bearer"}' % (token, token)).encode())


@pytest.mark.parametrize("key_config", [{}, {"api_key": None}, {"api_key": ""}, {"api_key": "configured-key"}],
                         ids=["unset", "none", "blank", "configured"])
@pytest.mark.parametrize("authentication", ["basic", "oauth"])
def test_optional_api_key_with_sdk_authentication_and_refresh(monkeypatch, key_config, authentication):
    def configuration(role):
        config = dict(host=f"https://{role}.example.com", vanity=role,
                      username="user", password="password", **key_config)
        if authentication == "oauth":
            config.update(client_id="client", client_secret="secret")
        return config

    def token_response(*args, **kwargs):
        # Exercise the SDK's actual token exchange and verify it never passes an
        # invalid None header to urllib3 when no API key was supplied.
        assert all(isinstance(value, str) for value in kwargs["headers"].values())
        if authentication == "oauth":
            assert kwargs["headers"]["apikey"] == (key_config.get("api_key") or "")
            return HTTPResponse(status=200, body=b'{"access_token":"access-token","refresh_token":"refresh-token","id_token":"id-token","expires_in":3600,"token_type":"Bearer"}')
        return HTTPResponse(status=200, body=b"asid-token")

    token_request = Mock(side_effect=token_response)
    monkeypatch.setattr(sdk.configuration.http, "request", token_request)
    gateway = VisierGateway(SimpleNamespace(configuration=configuration))
    for role, client in gateway.clients.items():
        def api_response(*args, **kwargs):
            headers = kwargs["headers"]
            assert "TargetTenantID" not in headers
            if key_config.get("api_key"):
                assert headers["apikey"] == key_config["api_key"]
            else:
                assert "apikey" not in headers
            if authentication == "oauth":
                assert headers["Authorization"] == "Bearer access-token"
            else:
                assert headers["Cookie"] == "VisierASIDToken=asid-token"
            # Force one authentication refresh before returning version history.
            status = 401 if api_request.call_count == 1 else 200
            return HTTPResponse(status=status, body=b'{"publishedVersions":[]}',
                                headers={"Content-Type": "application/json"})

        api_request = Mock(side_effect=api_response)
        monkeypatch.setattr(client.rest_client.pool_manager, "request", api_request)
        assert gateway.versions(role) == []
        assert api_request.call_count == 2
    assert token_request.call_count == 4


def test_repeated_unauthorized_preserves_diagnostics_without_secrets(monkeypatch, caplog):
    credentials = SimpleNamespace(configuration=lambda role: dict(
        host=f"https://{role}.example.com", vanity=role, username="user",
        password="private-password", tenant_id="incorrect-vanity"))
    token_request = Mock(side_effect=lambda *a, **kw: HTTPResponse(status=200, body=b"private-token"))
    monkeypatch.setattr(sdk.configuration.http, "request", token_request)
    gateway = VisierGateway(credentials)
    def unauthorized_response(*args, **kwargs):
        assert kwargs["headers"]["TargetTenantID"] == "incorrect-vanity"
        return HTTPResponse(
            status=401, headers={"Set-Cookie": "private-cookie"},
            body=b'{"code":"VSE_AUTHENTICATION_INVALID_TOKEN","rci":"RCI12345","message":"private-password private-token"}')

    api_request = Mock(side_effect=unauthorized_response)
    monkeypatch.setattr(gateway.clients["source"].rest_client.pool_manager, "request", api_request)
    with pytest.raises(AppError) as caught:
        gateway.versions("source")
    message = str(caught.value)
    assert caught.value.status == 502
    assert "source GET /v1/admin/production-versions" in message
    assert "HTTP 401" in message
    assert "VSE_AUTHENTICATION_INVALID_TOKEN" in message
    assert "RCI12345" in message
    assert "SOURCE_TENANT_ID" in message
    assert message in caplog.text
    assert "private-" not in message + caplog.text
    assert api_request.call_count == 2
    assert token_request.call_count == 2  # No unused third token request.


@pytest.mark.parametrize("role", ["source", "target"])
@pytest.mark.parametrize("authentication", ["basic", "oauth"])
def test_unauthorized_retries_with_new_token_silently(monkeypatch, caplog, role, authentication):
    def configuration(role):
        config = dict(host=f"https://{role}.example.com", vanity=role, username="user", password="password")
        if authentication == "oauth":
            config.update(client_id="client", client_secret="secret")
        return config

    tokens = [oauth_response(token) if authentication == "oauth" else HTTPResponse(status=200, body=token.encode())
              for token in ("old-token", "new-token")]
    token_request = Mock(side_effect=tokens)
    monkeypatch.setattr(sdk.configuration.http, "request", token_request)
    gateway = VisierGateway(SimpleNamespace(configuration=configuration))
    rejected = HTTPResponse(status=401, body=b"expired", preload_content=False)
    rejected.read = Mock(side_effect=AssertionError("A 401 body must not be read before reauthentication"))
    rejected.close = Mock(wraps=rejected.close)
    rejected.release_conn = Mock(wraps=rejected.release_conn)
    headers = []

    def api_response(*args, **kwargs):
        headers.append(dict(kwargs["headers"]))
        return rejected if len(headers) == 1 else HTTPResponse(status=200, body=b'{"publishedVersions":[]}')

    monkeypatch.setattr(gateway.clients[role].rest_client.pool_manager, "request", api_response)
    assert gateway.versions(role) == []
    header, prefix = ("Authorization", "Bearer ") if authentication == "oauth" else ("Cookie", "VisierASIDToken=")
    assert [request[header] for request in headers] == [prefix + "old-token", prefix + "new-token"]
    assert token_request.call_count == 2
    rejected.close.assert_called_once()
    rejected.release_conn.assert_called_once()
    assert not caplog.records


@pytest.mark.parametrize("trigger", ["expired", "unauthorized"])
def test_expired_oauth_refresh_token_falls_back_to_login(monkeypatch, caplog, trigger):
    from urllib.parse import parse_qs

    credentials = SimpleNamespace(configuration=lambda role: dict(
        host=f"https://{role}.example.com", vanity=role, username="user", password="password",
        client_id="client", client_secret="secret"))
    token_request = Mock(side_effect=[
        oauth_response("old-token"),
        HTTPResponse(status=400, body=b'{"error":"invalid_grant"}'),
        oauth_response("new-token"),
    ])
    monkeypatch.setattr(sdk.configuration.http, "request", token_request)
    gateway = VisierGateway(credentials)
    headers = []

    def api_response(*args, **kwargs):
        headers.append(dict(kwargs["headers"]))
        status = 401 if trigger == "unauthorized" and len(headers) == 2 else 200
        return HTTPResponse(status=status, body=b'{"publishedVersions":[]}')

    client = gateway.clients["source"]
    monkeypatch.setattr(client.rest_client.pool_manager, "request", api_response)
    assert gateway.versions("source") == []
    if trigger == "expired":
        client.configuration._token_acquired_at -= client.configuration.token_expiration_secs + 1
    assert gateway.versions("source") == []
    assert headers[-1]["Authorization"] == "Bearer new-token"
    assert [parse_qs(call.kwargs["body"])["grant_type"] for call in token_request.call_args_list] == [
        ["password"], ["refresh_token"], ["password"]]
    assert not caplog.records


@pytest.mark.parametrize("status,body", [
    (400, b'{"error":"invalid_client"}'),
    (403, b'{"error":"invalid_grant"}'),
    (500, b'{"error":"invalid_grant"}'),
])
def test_other_oauth_refresh_failures_do_not_trigger_login(monkeypatch, status, body):
    credentials = SimpleNamespace(configuration=lambda role: dict(
        host=f"https://{role}.example.com", vanity=role, username="user", password="password",
        client_id="client", client_secret="secret"))
    token_request = Mock(side_effect=[oauth_response("old-token"), HTTPResponse(status=status, body=body)])
    monkeypatch.setattr(sdk.configuration.http, "request", token_request)
    gateway = VisierGateway(credentials)
    client = gateway.clients["source"]
    api_request = Mock(return_value=HTTPResponse(status=200, body=b'{"publishedVersions":[]}'))
    monkeypatch.setattr(client.rest_client.pool_manager, "request", api_request)
    assert gateway.versions("source") == []
    client.configuration._token_acquired_at -= client.configuration.token_expiration_secs + 1
    with pytest.raises(AppError, match=f"authentication token request failed.*HTTP {status}"):
        gateway.versions("source")
    assert token_request.call_count == 2
    api_request.assert_called_once()


@pytest.mark.parametrize("wrapped", [False, True])
@pytest.mark.parametrize("repeated", [False, True])
def test_dropped_read_reauthenticates_once(monkeypatch, caplog, wrapped, repeated):
    from http.client import RemoteDisconnected
    from urllib3.exceptions import MaxRetryError, ProtocolError

    credentials = SimpleNamespace(configuration=lambda role: dict(
        host=f"https://{role}.example.com", vanity=role, username="user", password="password"))
    token_request = Mock(side_effect=[HTTPResponse(status=200, body=token) for token in (b"old-token", b"new-token")])
    monkeypatch.setattr(sdk.configuration.http, "request", token_request)
    gateway = VisierGateway(credentials)
    headers = []

    def api_response(*args, **kwargs):
        headers.append(dict(kwargs["headers"]))
        if len(headers) == 1 or repeated:
            error = ProtocolError("Connection aborted.", RemoteDisconnected("private-detail"))
            if wrapped:
                raise MaxRetryError(None, args[1], reason=error)
            raise error
        return HTTPResponse(status=200, body=b'{"publishedVersions":[]}')

    monkeypatch.setattr(gateway.clients["source"].rest_client.pool_manager, "request", api_response)
    if repeated:
        with pytest.raises(AppError, match="source GET /v1/admin/production-versions failed"):
            gateway.versions("source")
        assert "private-detail" not in caplog.text
    else:
        assert gateway.versions("source") == []
        assert not caplog.records
    assert [request["Cookie"] for request in headers] == ["VisierASIDToken=old-token", "VisierASIDToken=new-token"]
    assert token_request.call_count == 2


@pytest.mark.parametrize("operation,args", [
    ("publish", ("draft-1",)), ("create_project", ("name", "description", 1)),
    ("upload", ("draft-1", b"archive")), ("delete_project", ("draft-1",)),
])
def test_dropped_write_is_never_replayed(monkeypatch, operation, args):
    from http.client import RemoteDisconnected
    from urllib3.exceptions import MaxRetryError, ProtocolError

    credentials = SimpleNamespace(configuration=lambda role: dict(
        host=f"https://{role}.example.com", vanity=role, username="user", password="password"))
    token_request = Mock(return_value=HTTPResponse(status=200, body=b"token"))
    monkeypatch.setattr(sdk.configuration.http, "request", token_request)
    gateway = VisierGateway(credentials)
    api_request = Mock(side_effect=MaxRetryError(None, "url", reason=ProtocolError("aborted", RemoteDisconnected())))
    monkeypatch.setattr(gateway.clients["target"].rest_client.pool_manager, "request", api_request)
    with pytest.raises(AppError):
        getattr(gateway, operation)(*args)
    api_request.assert_called_once()
    token_request.assert_called_once()


def test_publish_retries_only_after_explicit_unauthorized(monkeypatch, caplog):
    credentials = SimpleNamespace(configuration=lambda role: dict(
        host=f"https://{role}.example.com", vanity=role, username="user", password="password"))
    token_request = Mock(side_effect=[HTTPResponse(status=200, body=token) for token in (b"old-token", b"new-token")])
    monkeypatch.setattr(sdk.configuration.http, "request", token_request)
    gateway = VisierGateway(credentials)
    api_request = Mock(side_effect=[
        HTTPResponse(status=401, body=b"expired"),
        HTTPResponse(status=200, body=b'{"commitAndPublish":{"publishedVersion":{"id":"published-1"}}}'),
    ])
    monkeypatch.setattr(gateway.clients["target"].rest_client.pool_manager, "request", api_request)
    assert gateway.publish("draft-1") == "published-1"
    assert api_request.call_count == 2
    first, second = api_request.call_args_list
    assert first.args == second.args
    assert first.kwargs["body"] == second.kwargs["body"]
    assert not caplog.records


def test_token_request_failure_identifies_authentication_stage(monkeypatch, caplog):
    credentials = SimpleNamespace(configuration=lambda role: dict(
        host=f"https://{role}.example.com", vanity=role, username="user", password="private-password"))
    monkeypatch.setattr(sdk.configuration.http, "request", lambda *a, **kw: HTTPResponse(
        status=401, body=b'{"code":"VSE_AUTHENTICATION_FAILED","message":"private-password"}'))
    gateway = VisierGateway(credentials)
    with pytest.raises(AppError, match="source authentication token request.*HTTP 401.*VSE_AUTHENTICATION_FAILED"):
        gateway.versions("source")
    assert "private-password" not in caplog.text


def test_edge_block_is_identifiable_from_logs_without_secrets(monkeypatch, caplog):
    credentials = SimpleNamespace(configuration=lambda role: dict(
        host="https://source.example.com/path", vanity="source", username="user", password="private-password"))
    monkeypatch.setattr(sdk.configuration.http, "request", lambda *a, **kw: HTTPResponse(
        status=200, body=b"private-token", headers={"Set-Cookie": "private-cookie"}))
    gateway = VisierGateway(credentials)

    def blocked(*args, **kwargs):
        return HTTPResponse(status=403, headers={"Server": "cloudflare", "CF-Ray": "8a1b2c3d4e5f-IAD",
                                                 "Content-Type": "text/html", "Set-Cookie": "private-cookie"},
                            body=b"<html>Access denied</html>")

    monkeypatch.setattr(gateway.clients["source"].rest_client.pool_manager, "request", Mock(side_effect=blocked))
    with pytest.raises(AppError, match="HTTP 403"):
        gateway.versions("source")
    logged = caplog.text
    assert "host=source.example.com" in logged and "example.com/path" not in logged
    assert "server=cloudflare" in logged and "cf-ray=8a1b2c3d4e5f-IAD" in logged
    assert "content-type=text/html" in logged and "body=non-json" in logged and "body_bytes=" in logged
    assert "private-" not in logged and "private-cookie" not in logged and "Access denied" not in logged


def test_transport_failure_logs_exception_chain_without_message(monkeypatch, caplog):
    from urllib3.exceptions import ProtocolError
    from http.client import RemoteDisconnected
    credentials = SimpleNamespace(configuration=lambda role: dict(
        host="https://demo-tenant.api.example.com", vanity="demo-tenant", username="user", password="private-password"))

    def dropped(*args, **kwargs):
        raise ProtocolError("Connection aborted.", RemoteDisconnected("private-detail from server"))

    monkeypatch.setattr(sdk.configuration.http, "request", dropped)
    gateway = VisierGateway(credentials)
    with pytest.raises(AppError, match="authentication token request failed.*ProtocolError<-RemoteDisconnected"):
        gateway.versions("source")
    assert "private-" not in caplog.text


def test_token_request_403_logs_edge_headers(monkeypatch, caplog):
    credentials = SimpleNamespace(configuration=lambda role: dict(
        host="https://demo-tenant.api.example.com", vanity="demo-tenant", username="user", password="private-password"))
    monkeypatch.setattr(sdk.configuration.http, "request", lambda *a, **kw: HTTPResponse(
        status=403, reason="Forbidden", headers={"Server": "cloudflare", "CF-Ray": "8a1b2c3d4e5f-IAD", "Set-Cookie": "private-cookie"},
        body=b"<html><head><title>Access denied | demo-tenant.api.example.com used Cloudflare to restrict access</title></head>"
             b"<body>Error 1020 private-page-text Cloudflare Ray ID</body></html>"))
    gateway = VisierGateway(credentials)
    with pytest.raises(AppError, match="authentication token request failed.*HTTP 403"):
        gateway.versions("source")
    logged = caplog.text
    assert "host=demo-tenant.api.example.com" in logged
    assert "server=cloudflare" in logged and "cf-ray=8a1b2c3d4e5f-IAD" in logged
    assert "body=non-json" in logged
    assert "title=Access denied | demo-tenant.api.example.com used Cloudflare to restrict access" in logged
    assert "cloudflare_error=1020" in logged
    assert "private-" not in logged and "private-page-text" not in logged


@pytest.mark.parametrize("token_field, header, value", [
    ("access_token", "Authorization", "Bearer supplied-token"),
    ("asid_token", "Cookie", "VisierASIDToken=supplied-token"),
])
def test_supplied_tokens_work_without_username_password(monkeypatch, token_field, header, value):
    credentials = SimpleNamespace(configuration=lambda role: dict(
        host=f"https://{role}.example.com", vanity=role, **{token_field: "supplied-token"}))
    token_request = Mock(side_effect=AssertionError("Supplied tokens must not trigger a login"))
    monkeypatch.setattr(sdk.configuration.http, "request", token_request)
    gateway = VisierGateway(credentials)

    def api_response(*args, **kwargs):
        assert kwargs["headers"][header] == value
        assert "TargetTenantID" not in kwargs["headers"]
        return HTTPResponse(status=200, body=b'{"publishedVersions":[]}',
                            headers={"Content-Type": "application/json"})

    monkeypatch.setattr(gateway.clients["source"].rest_client.pool_manager, "request", api_response)
    assert gateway.versions("source") == []
    token_request.assert_not_called()


def test_expired_supplied_token_fails_without_retrying_login(monkeypatch):
    credentials = SimpleNamespace(configuration=lambda role: dict(
        host=f"https://{role}.example.com", vanity=role, access_token="expired-token"))
    token_request = Mock(side_effect=AssertionError("Token-only configurations cannot log in"))
    monkeypatch.setattr(sdk.configuration.http, "request", token_request)
    gateway = VisierGateway(credentials)
    api_request = Mock(return_value=HTTPResponse(status=401, body=b'{"code":"VSE_AUTHENTICATION_INVALID_TOKEN"}'))
    monkeypatch.setattr(gateway.clients["source"].rest_client.pool_manager, "request", api_request)
    with pytest.raises(AppError, match="HTTP 401"):
        gateway.versions("source")
    api_request.assert_called_once()
    token_request.assert_not_called()


@pytest.fixture
def adapter(monkeypatch):
    gateway = VisierGateway.__new__(VisierGateway)
    gateway.sdk, gateway.clients, gateway.tenant_ids = sdk, {"source":object(), "target":object()}, {"source":"dev", "target":"prod"}
    versions, projects = Mock(), Mock()
    monkeypatch.setattr(sdk,"ProductionVersionsApi",lambda client: versions)
    monkeypatch.setattr(sdk,"ProjectsApi",lambda client: projects)
    return gateway, versions, projects


def test_sdk_contract_and_binary_export_import(adapter):
    gateway, versions, projects = adapter
    contents = io.BytesIO()
    with zipfile.ZipFile(contents,"w") as z:
        z.writestr("changes.json","[]")
    archive = contents.getvalue()
    response = Mock(status=200, data=archive)
    versions.post_production_versions_without_preload_content.return_value = response
    assert gateway.export("first","last") == archive
    args, kwargs = versions.post_production_versions_without_preload_content.call_args
    assert args[0].to_dict() == {"operation":"export", "exportParameters":{"startVersion":"first","endVersion":"last"}}
    assert kwargs["_headers"]["Accept"] == "application/zip, application/json"
    assert kwargs["target_tenant_id"] == "dev"
    response.release_conn.assert_called_once()
    gateway.upload("draft-1", archive)
    args, kwargs = projects.put_project_commits.call_args
    assert args == ("draft-1", archive)
    assert kwargs["_content_type"] == "application/zip"
    assert kwargs["target_tenant_id"] == "prod"


def test_sdk_create_project_uses_name_description_and_version_number(adapter):
    gateway, _, projects = adapter
    projects.create_project.return_value = sdk.ProjectDTO(id="draft-1")
    name = "November release · Workforce planning"
    description = "A longer description with release details. " * 10
    assert gateway.create_project(name, description, 89) == "draft-1"
    args, kwargs = projects.create_project.call_args
    assert args[0].to_dict() == {"name": name, "description": description, "versionNumber": 89}
    assert kwargs["target_tenant_id"] == "prod"


def test_sdk_publish_requires_confirmed_published_version(adapter):
    gateway, _, projects = adapter
    projects.run_project_operation.return_value = sdk.ProjectOperationResponseDTO.from_dict({"commitAndPublish":{"publishedVersion":{"id":"published-1"}}})
    assert gateway.publish("draft-1") == "published-1"
    args, kwargs = projects.run_project_operation.call_args
    assert args[1].operation == "commitAndPublish"
    projects.run_project_operation.return_value = sdk.ProjectOperationResponseDTO()
    with pytest.raises(AppError, match="confirmed"):
        gateway.publish("draft-1")


def test_sdk_delete_project_is_target_scoped_and_missing_is_idempotent(adapter):
    from promotion.ports import AccessDenied, ProjectNotFound
    gateway, _, projects = adapter
    gateway.delete_project("draft-1")
    args, kwargs = projects.delete_project.call_args
    assert args == ("draft-1",)
    assert kwargs["target_tenant_id"] == "prod"
    projects.delete_project.side_effect = ProjectNotFound("Already deleted")
    gateway.delete_project("draft-1")
    projects.delete_project.side_effect = AccessDenied("Denied")
    with pytest.raises(AccessDenied):
        gateway.delete_project("draft-1")


@pytest.mark.parametrize("status,stage,expected", [
    (401, "POST /v1/admin/projects/draft-1", "AccessDenied"),
    (403, "POST /v1/admin/projects/draft-1", "AccessDenied"),
    (500, "POST /v1/admin/projects/draft-1", "AppError"),
    (404, "DELETE /v1/admin/projects/draft-1", "ProjectNotFound"),
    (404, "authentication token request", "AppError"),
])
def test_sdk_failure_classifies_only_definitive_access_denials(adapter, status, stage, expected):
    gateway, _, _ = adapter
    gateway.hosts = {}
    error = gateway._failure("target", stage, error=SimpleNamespace(status=status))
    assert type(error).__name__ == expected


def test_sdk_rollback_returns_draft(adapter):
    gateway, versions, _ = adapter
    versions.post_production_version.return_value = sdk.ProductionVersionAPIOperationResponseDTO.from_dict({"rollBackTo":{"id":"rollback-draft"}})
    assert gateway.rollback_project("baseline") == "rollback-draft"
    args, kwargs = versions.post_production_version.call_args
    assert args[0] == "baseline"
    assert args[1].operation == "rollBackTo"


def test_sdk_paginates_versions_and_does_not_invent_metadata(adapter):
    gateway, versions, _ = adapter
    versions.get_production_versions.side_effect = [
        sdk.GetProductionVersionsAPIResponseDTO(published_versions=[sdk.ProjectDTO(id=str(i),name=f"Version {i}") for i in range(400)]),
        sdk.GetProductionVersionsAPIResponseDTO(published_versions=[sdk.ProjectDTO(id="last",description="Final version")]),
    ]
    data = gateway.versions("source")
    assert len(data) == 401
    assert data[-1]["description"] == "Final version"
    assert data[-1]["owner"] is None
    assert data[-1]["published_at"] is None
    assert versions.get_production_versions.call_args_list[1].kwargs["start"] == 400


def test_sdk_rejects_non_zip_export(adapter):
    gateway, versions, _ = adapter
    response = Mock(status=200, data=b'{"error":"invalid export"}')
    versions.post_production_versions_without_preload_content.return_value = response
    with pytest.raises(AppError, match="valid export ZIP"):
        gateway.export("a","b")
    response.release_conn.assert_called_once()

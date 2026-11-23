from __future__ import annotations

import io
import json
import logging
import re
import zipfile
from functools import partial
from http.client import RemoteDisconnected
from threading import RLock
from urllib.parse import urlsplit

from urllib3.exceptions import MaxRetryError, ProtocolError

from .ports import AccessDenied, AppError, ProjectNotFound

# Response headers that identify the tier which produced a status code (edge proxy,
# WAF, load balancer or the Visier application) and the request for correlation.
# Cookies, auth challenges and free-text bodies are never logged.
SAFE_RESPONSE_HEADERS = ("server", "via", "cf-ray", "x-amz-cf-id", "x-amzn-requestid",
                         "x-request-id", "x-correlation-id", "content-type")
SAFE_HEADER_VALUE = re.compile(r"[A-Za-z0-9._:/ ;,=+-]{1,120}")
SAFE_HTML_TITLE = re.compile(r"[A-Za-z0-9 .,!|:'()/-]{1,120}")
CLOUDFLARE_ERROR = re.compile(r"\b[Ee]rror\s+(1\d{3})\b")


def _connection_dropped(error):
    if isinstance(error, MaxRetryError):
        error = error.reason
    return isinstance(error, (ProtocolError, RemoteDisconnected))


def _exception_chain(error):
    """Exception class names only, e.g. ProtocolError<-RemoteDisconnected. Messages can carry request details, so they are not logged."""
    names, seen, current = [], set(), error
    while isinstance(current, BaseException) and id(current) not in seen and len(names) < 4:
        seen.add(id(current))
        names.append(type(current).__name__)
        current = (next((arg for arg in current.args if isinstance(arg, BaseException)), None)
                   or current.__cause__ or current.__context__)
    return "<-".join(names)


def _html_summary(body):
    """Bounded facts from an HTML block page: its title and any Cloudflare error code. Never the page text."""
    text = body.decode("utf-8", "replace") if isinstance(body, bytes) else body
    summary = []
    title = re.search(r"<title[^>]*>([^<]{1,200})</title>", text, re.IGNORECASE)
    if title and SAFE_HTML_TITLE.fullmatch(title.group(1).strip()):
        summary.append(f"title={title.group(1).strip()}")
    if "cloudflare" in text.lower():
        code = CLOUDFLARE_ERROR.search(text)
        if code:
            summary.append(f"cloudflare_error={code.group(1)}")
    return summary


class VisierGateway:
    """Only this adapter knows SDK DTOs and transport details."""

    def __init__(self, credentials):
        import visier_platform_sdk as sdk

        class OptionalApiKeyConfiguration(sdk.Configuration):
            def auth_settings(self):
                auth = super().auth_settings()
                if not self.api_key:
                    auth.pop("ApiKeyAuth", None)
                return auth

        gateway = self

        class DiagnosticApiClient(sdk.ApiClient):
            def _refresh_auth(self, headers, post_params):
                if self.configuration.refresh_config:
                    self.configuration.refresh_config(self.configuration, True)
                    self.update_params_for_auth(
                        headers, post_params, ["ApiKeyAuth", "CookieAuth", "OAuth2Auth"],
                        None, None, None)

            def call_api(self, method, url, header_params=None, body=None,
                         post_params=None, _request_timeout=None):
                # The SDK discards the last 401 and raises an exception with a
                # string in its status field. Preserve the actual response and
                # refresh only when another authenticated attempt will follow.
                stage = f"{method} {urlsplit(url).path}"
                header_params = dict(header_params or {})
                for attempt in range(self.auth_retries):
                    try:
                        response = self.rest_client.request(
                            method, url, headers=header_params, body=body,
                            post_params=post_params, _request_timeout=_request_timeout)
                    except Exception as error:
                        # A connection can close before any 401 reaches us.
                        # Only reads can be replayed without a response:
                        # a write may already have taken effect.
                        if (method in ("GET", "HEAD") and _connection_dropped(error)
                                and attempt + 1 < self.auth_retries):
                            self._refresh_auth(header_params, post_params)
                            continue
                        raise gateway._failure(self.tenant_role, stage, error=error) from None
                    if (response.status == 401 and self.configuration.refresh_config
                            and attempt + 1 < self.auth_retries):
                        # Discard the rejected response without reading its body;
                        # a dropped error body must not prevent reauthentication.
                        response.response.close()
                        response.response.release_conn()
                        self._refresh_auth(header_params, post_params)
                        continue
                    if response.status >= 400:
                        response.read()
                        error = gateway._failure(self.tenant_role, stage, response=response)
                        response.response.release_conn()
                        raise error from None
                    return response

        self.sdk, self.clients, self.tenant_ids = sdk, {}, {}
        self.hosts = {}
        self.auth_locks = {role: RLock() for role in ("source", "target")}
        for role in ("source", "target"):
            config = dict(credentials.configuration(role))
            self.tenant_ids[role] = config.pop("tenant_id", None)
            if not all(config.get(k) for k in ("host", "vanity")):
                raise ValueError(f"Configure {role.upper()}_HOST and {role.upper()}_VANITY before enabling live mode")
            # Hostname only: no scheme, path, or credentials.
            self.hosts[role] = urlsplit(config["host"]).hostname
            if not (config.get("access_token") or config.get("asid_token") or (config.get("username") and config.get("password"))):
                raise ValueError(f"Configure authentication for {role}")
            # The SDK's OAuth token exchange always adds an apikey header. An empty
            # value is valid HTTP; None is not. Omit it from API calls above.
            config["api_key"] = config.get("api_key") or ""
            # Never retry a publish after a transport error: it may have succeeded.
            configuration = OptionalApiKeyConfiguration(**config, retries=0)
            if config.get("username") and config.get("password"):
                configuration.refresh_config = partial(self._refresh, role, configuration.refresh_config)
            else:
                # Supplied tokens need no login. The SDK's default refresh hook
                # rejects token-only configurations for lacking username/password.
                configuration.refresh_config = None
            client = DiagnosticApiClient(configuration)
            client.tenant_role = role
            self.clients[role] = client

    def _refresh(self, role, callback, configuration, force=False):
        # The same client is shared by requests in a worker. Do not race token
        # exchanges (in particular, rotating OAuth refresh tokens).
        with self.auth_locks[role]:
            try:
                used_refresh_token = bool(configuration.client_id and configuration.client_secret
                                          and configuration.refresh_token)
                try:
                    callback(configuration, force)
                except self.sdk.ApiException as error:
                    try:
                        details = json.loads(error.body or "{}")
                    except (ValueError, UnicodeError):
                        details = {}
                    if (not used_refresh_token or error.status not in (400, 401)
                            or not isinstance(details, dict) or details.get("error") != "invalid_grant"):
                        raise
                    # A refresh token can expire or be revoked independently of
                    # the access token. Stored credentials allow a fresh login.
                    configuration.refresh_token = None
                    configuration.access_token = None
                    callback(configuration, True)
            except Exception as error:
                raise self._failure(role, "authentication token request", error=error) from None

    def _failure(self, role, stage, *, error=None, response=None):
        """Expose structured diagnostics, never raw response bodies or headers."""
        status = response.status if response is not None else getattr(error, "status", None)
        parts = [f"Visier {role} {stage} failed"]
        if self.hosts.get(role):
            parts.append(f"host={self.hosts[role]}")
        if isinstance(status, int):
            parts.append(f"HTTP {status}")
        if error is not None:
            parts.append(_exception_chain(error))
        body = response.data if response is not None else getattr(error, "body", None)
        # The SDK's token request raises ApiException with the response headers
        # attached; API calls hand us the RESTResponse directly.
        headers = response.getheaders() if response is not None else getattr(error, "headers", None)
        if headers is not None or body is not None:
            # Which tier answered: a proxy or WAF usually adds its own server/ray
            # headers, and a non-JSON body suggests a block page rather than Visier.
            for name in SAFE_RESPONSE_HEADERS:
                value = headers.get(name) if headers is not None else None
                if isinstance(value, str) and SAFE_HEADER_VALUE.fullmatch(value):
                    parts.append(f"{name}={value}")
            parts.append(f"body_bytes={len(body) if isinstance(body, (bytes, str)) else 0}")
        try:
            details = json.loads(body) if isinstance(body, (str, bytes)) else {}
            is_json = isinstance(details, dict)
        except (ValueError, UnicodeError):
            details, is_json = {}, False
        if body and not is_json:
            parts.append("body=non-json")
            parts.extend(_html_summary(body))
        elif not body and status is not None:
            parts.append("body=empty")
        if isinstance(details, dict):
            # Visier codes and correlation IDs are safe, bounded identifiers.
            # Free-text server messages can echo credentials and are excluded.
            for field, pattern in (("code", r"VSE_[A-Z0-9_]{1,100}"), ("rci", r"RCI[A-Za-z0-9-]{1,100}")):
                value = details.get(field)
                if isinstance(value, str) and re.fullmatch(pattern, value):
                    parts.append(f"{field}={value}")
            oauth_error = details.get("error")
            if oauth_error in ("invalid_request", "invalid_client", "invalid_grant", "unauthorized_client", "unsupported_grant_type", "invalid_scope"):
                parts.append(oauth_error)
        message = "; ".join(parts) + "."
        if status == 401:
            if stage == "authentication token request":
                message += " Check the login credentials, vanity, and authentication method."
            elif self.tenant_ids.get(role):
                message += (f" Check {role.upper()}_TENANT_ID: TargetTenantID requires a tenant ID, not a vanity name."
                            " Leave it unset when authenticating directly to that tenant.")
            else:
                message += " The server rejected the token. Check the authentication method and tenant access."
        elif status == 403:
            message += " Check the user's permissions and access to the requested tenant."
        elif status == 404:
            message += " Check the configured host and API endpoint."
        elif status is None:
            message += " Check server connectivity and authentication configuration."
        logging.getLogger(__name__).error("%s", message)
        error_type = AppError
        if status in (401, 403):
            error_type = AccessDenied
        elif status == 404 and role == "target" and stage.startswith("DELETE /v1/admin/projects/"):
            error_type = ProjectNotFound
        return error_type(message, 502)

    def _options(self, role):
        options = {"_request_timeout": (10.0, 120.0)}
        # Login already scopes requests to the administrating tenant. Override
        # only when explicitly addressing a different tenant through that login.
        if self.tenant_ids[role]:
            options["target_tenant_id"] = self.tenant_ids[role]
        return options

    def versions(self, role):
        api, result, start = self.sdk.ProductionVersionsApi(self.clients[role]), [], 0
        while True:
            response = api.get_production_versions(limit=400, start=start, **self._options(role))
            page = response.published_versions or []
            for item in page:
                data = item.to_dict()
                if not item.id:
                    raise AppError("Visier returned a version without an ID.", 502)
                # The supplied ProjectDTO doesn't guarantee owner or publish date.
                # Show missing metadata honestly instead of manufacturing values.
                owner = data.get("ownerUser") or data.get("owner")
                if isinstance(owner, dict):
                    owner = owner.get("displayName") or owner.get("username")
                result.append({"id": item.id, "description": item.description or item.name or "Untitled version",
                               "number": item.version_number, "owner": owner,
                               "published_at": data.get("publishDate") or data.get("publishedAt") or data.get("publishedDate")})
            if len(page) < 400:
                break
            start += len(page)
        return result

    def export(self, first_id, last_id):
        request = self.sdk.ProductionVersionsAPIOperationRequestDTO(
            operation="export", export_parameters=self.sdk.ExportProductionVersionsAPIOperationParametersDTO(start_version=first_id, end_version=last_id))
        response = self.sdk.ProductionVersionsApi(self.clients["source"]).post_production_versions_without_preload_content(
            request, _headers={"Accept": "application/zip, application/json"}, **self._options("source"))
        try:
            data = response.data
            if response.status != 200 or not zipfile.is_zipfile(io.BytesIO(data)):
                raise AppError("Visier did not return a valid export ZIP. No target changes were made.", 502)
            return data
        finally:
            response.release_conn()

    def create_project(self, name, description, version_number):
        project = self.sdk.ProjectsApi(self.clients["target"]).create_project(
            self.sdk.ProjectDTO(name=name, description=description, version_number=version_number), **self._options("target"))
        if not project.id:
            raise AppError("Visier did not return a draft project ID.", 502)
        return project.id

    def export_sources(self):
        request = self.sdk.SourcesAPIOperationRequestDTO(operation="exportSources")
        # The specification describes JSON, but exportSources returns ZIP bytes.
        response = self.sdk.SourcesApi(self.clients["source"]).run_sources_operation_without_preload_content(
            request, _headers={"Accept": "application/zip, application/json"}, **self._options("source"))
        try:
            data = response.data
            if response.status != 200 or not zipfile.is_zipfile(io.BytesIO(data)):
                raise AppError("Visier did not return a valid sources export ZIP. No target changes were made.", 502)
            return data
        finally:
            response.release_conn()

    def import_sources(self, archive, replace_all_existing_sources=False):
        response = self.sdk.SourcesApi(self.clients["target"]).put_sources(
            archive, replace_all_existing_sources=replace_all_existing_sources,
            _content_type="application/zip", **self._options("target"))
        if response is None or response.summary is None:
            raise AppError("Source import returned no confirmed summary. Verify the target sources before retrying.", 502)
        summary = {key: getattr(response.summary, key) or 0 for key in ("created", "updated", "ignored", "deleted")}
        if any(type(value) is not int or value < 0 for value in summary.values()):
            raise AppError("Source import returned an invalid summary. Verify the target sources before retrying.", 502)
        return summary

    def upload(self, project_id, archive):
        self.sdk.ProjectsApi(self.clients["target"]).put_project_commits(
            project_id, archive, _content_type="application/zip", **self._options("target"))

    def publish(self, project_id):
        response = self.sdk.ProjectsApi(self.clients["target"]).run_project_operation(
            project_id, self.sdk.ProjectOperationRequestDTO(operation="commitAndPublish"), **self._options("target"))
        published = response.commit_and_publish.published_version if response.commit_and_publish else None
        if not published or not published.id:
            raise AppError("Publish returned no confirmed production version. Reconcile the operation before retrying.", 502)
        return published.id

    def delete_project(self, project_id):
        try:
            self.sdk.ProjectsApi(self.clients["target"]).delete_project(project_id, **self._options("target"))
        except ProjectNotFound:
            # A prior deletion may have succeeded before its response was lost.
            pass

    def rollback_project(self, version_id):
        response = self.sdk.ProductionVersionsApi(self.clients["target"]).post_production_version(
            version_id, self.sdk.ProductionVersionAPIOperationRequestDTO(operation="rollBackTo"), **self._options("target"))
        if not response.roll_back_to or not response.roll_back_to.id:
            raise AppError("Visier did not return a rollback draft project.", 502)
        return response.roll_back_to.id

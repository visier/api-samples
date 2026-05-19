"""
SDK-backed helpers for the Administration APIs used by the promotion sample.

This module intentionally delegates HTTP, authentication, generated DTOs, and error
handling to ``visier-platform-sdk``. The orchestration code in this repository should
teach the promotion sequence, not become a second Python SDK.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from visier_sdlc.config import EnvironmentProfile, visier_sdlc_troubleshoot_logging
from visier_sdlc.exceptions import VisierSDLCError

logger = logging.getLogger(__name__)

# Default timeout (seconds) for HTTP calls (exports can be large)
_DEFAULT_TIMEOUT = 120


@dataclass
class NewDraftProject:
    """Fields for ``POST /v1/admin/projects`` when creating a blank draft project."""

    name: str
    description: str = ""
    release_version: str = "1"
    ticket_number: str = ""
    version_number: int = 0


def _load_sdk() -> dict[str, Any]:
    try:
        from visier_platform_sdk import (  # type: ignore[import-not-found]
            ApiClient,
            Configuration,
            ExportProductionVersionsAPIOperationParametersDTO,
            ProductionVersionsApi,
            ProductionVersionsAPIOperationRequestDTO,
            ProjectDTO,
            ProjectOperationRequestDTO,
            ProjectsApi,
        )
        from visier_platform_sdk.exceptions import ApiException  # type: ignore[import-not-found]
    except ImportError as e:  # pragma: no cover - depends on caller environment
        raise ImportError(
            "Install visier-platform-sdk to run this sample: "
            "pip install -r requirements.txt"
        ) from e
    return {
        "ApiClient": ApiClient,
        "Configuration": Configuration,
        "ExportProductionVersionsAPIOperationParametersDTO": ExportProductionVersionsAPIOperationParametersDTO,
        "ProductionVersionsApi": ProductionVersionsApi,
        "ProductionVersionsAPIOperationRequestDTO": ProductionVersionsAPIOperationRequestDTO,
        "ProjectDTO": ProjectDTO,
        "ProjectOperationRequestDTO": ProjectOperationRequestDTO,
        "ProjectsApi": ProjectsApi,
        "ApiException": ApiException,
    }


def _dto_to_dict(value: Any) -> dict[str, Any]:
    """Return a plain dict from generated SDK DTOs or dict-like fake test objects."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if hasattr(value, "to_dict"):
        data = value.to_dict()
        return data if isinstance(data, dict) else {}
    if hasattr(value, "model_dump"):
        data = value.model_dump(by_alias=True, exclude_none=True)
        return data if isinstance(data, dict) else {}
    public = {k: v for k, v in vars(value).items() if not k.startswith("_")}
    return public


def _safe_api_error_message(exc: Exception) -> str:
    """Surface status/reason and a short body snippet without dumping headers or tokens."""
    status = getattr(exc, "status", None)
    reason = getattr(exc, "reason", None)
    body = getattr(exc, "data", None) or getattr(exc, "body", None)
    pieces: list[str] = []
    if status:
        pieces.append(f"HTTP {status}")
    if reason:
        pieces.append(str(reason))
    if body:
        body_text = str(body).strip()
        if len(body_text) > 300:
            body_text = body_text[:300] + "..."
        pieces.append(body_text)
    return ": ".join(pieces) if pieces else str(exc)


class VisierClient:
    """
    API client for one Visier tenant.

    The generated ``visier-platform-sdk`` handles authentication and request signing.
    This wrapper only keeps source/target profile metadata and provides small methods
    that match the promotion steps.
    """

    def __init__(self, profile: EnvironmentProfile, *, timeout: int = _DEFAULT_TIMEOUT) -> None:
        self._profile = profile
        self._timeout = timeout
        sdk = _load_sdk()
        self._api_exception_type = sdk["ApiException"]
        self._config = sdk["Configuration"](
            host=profile.base_url,
            api_key=profile.api_key,
            username=profile.username,
            password=profile.password,
            vanity=profile.vanity,
        )
        self._api_client = sdk["ApiClient"](self._config)
        self._production_versions_api = sdk["ProductionVersionsApi"](self._api_client)
        self._projects_api = sdk["ProjectsApi"](self._api_client)
        self._export_params_type = sdk["ExportProductionVersionsAPIOperationParametersDTO"]
        self._production_versions_operation_type = sdk["ProductionVersionsAPIOperationRequestDTO"]
        self._project_type = sdk["ProjectDTO"]
        self._project_operation_type = sdk["ProjectOperationRequestDTO"]

    @property
    def profile(self) -> EnvironmentProfile:
        return self._profile

    def authenticate(self) -> str:
        """
        Step 0 - force SDK authentication now so failures are reported before mutations.
        """
        try:
            self._config.refresh_config(self._config, True)
        except self._api_exception_type as e:
            raise VisierSDLCError(_safe_api_error_message(e), step=0) from e
        token = (self._config.asid_token or self._config.access_token or "").strip()
        if not token:
            raise VisierSDLCError("Authentication completed without a token.", step=0)
        logger.info("Authenticated tenant (base_url=%s)", self._profile.base_url)
        return token

    def get_production_versions(
        self,
        *,
        limit: int = 400,
        start: int = 0,
    ) -> dict[str, Any]:
        """Step 1 - list published production versions (newest first)."""
        try:
            response = self._production_versions_api.get_production_versions(
                limit=limit,
                start=start,
                target_tenant_id=self._profile.target_tenant_id,
                _request_timeout=self._timeout,
            )
        except self._api_exception_type as e:
            raise VisierSDLCError(_safe_api_error_message(e), step=1) from e
        return _dto_to_dict(response)

    def get_all_published_production_versions(
        self,
        *,
        page_size: int = 400,
    ) -> dict[str, Any]:
        """
        List all published production versions by following pagination until a page
        is empty or shorter than ``page_size``.
        """
        merged: list[dict[str, Any]] = []
        start = 0
        while True:
            page = self.get_production_versions(limit=page_size, start=start)
            batch = page.get("publishedVersions") or page.get("published_versions")
            if not isinstance(batch, list) or not batch:
                break
            merged.extend([_dto_to_dict(item) for item in batch])
            if len(batch) < page_size:
                break
            start += page_size
        return {"publishedVersions": merged}

    def export_production_versions_zip(
        self,
        start_version: str,
        end_version: str,
        excluded_versions: list[str] | None = None,
    ) -> bytes:
        """Step 2 - export a range of production versions as a ZIP."""
        request = self._production_versions_operation_type(
            operation="export",
            export_parameters=self._export_params_type(
                start_version=start_version,
                end_version=end_version,
                excluded_versions=excluded_versions,
            ),
        )
        try:
            response = self._production_versions_api.post_production_versions_without_preload_content(
                request,
                target_tenant_id=self._profile.target_tenant_id,
                _request_timeout=self._timeout,
                _headers={"Accept": "application/zip, application/json"},
            )
        except self._api_exception_type as e:
            raise VisierSDLCError(_safe_api_error_message(e), step=2) from e
        content_type = (getattr(response, "headers", {}).get("Content-Type") or "").lower()
        content = getattr(response, "data", b"") or b""
        if isinstance(content, str):
            content = content.encode("utf-8")
        if "json" in content_type:
            snippet = content.decode("utf-8", errors="replace")[:300]
            raise VisierSDLCError(
                "Expected a ZIP file but got JSON. Response may be an error: " + snippet,
                step=2,
            )
        if "zip" not in content_type and content[:2] != b"PK":
            logger.warning("Unexpected Content-Type for export: %s", content_type or "(missing)")
        return bytes(content)

    def create_draft_project(self, spec: NewDraftProject) -> dict[str, Any]:
        """Step 3 - create a new blank draft project."""
        payload = self._project_type(
            name=spec.name,
            description=spec.description,
            release_version=spec.release_version,
            ticket_number=spec.ticket_number,
            version_number=spec.version_number,
        )
        if visier_sdlc_troubleshoot_logging():
            logger.info(
                "[SDLC troubleshooting] Creating project name=%r description_len=%s",
                spec.name,
                len(spec.description or ""),
            )
        try:
            response = self._projects_api.create_project(
                payload,
                target_tenant_id=self._profile.target_tenant_id,
                _request_timeout=self._timeout,
            )
        except self._api_exception_type as e:
            raise VisierSDLCError(_safe_api_error_message(e), step=3) from e
        data = _dto_to_dict(response)
        logger.info("Created draft project id=%s name=%r", data.get("id"), data.get("name"))
        return data

    def import_commits(self, project_id: str, zip_bytes: bytes) -> dict[str, Any]:
        """Step 4 - import the ZIP from Step 2 into an existing draft project."""
        try:
            response = self._projects_api.put_project_commits(
                project_id,
                zip_bytes,
                target_tenant_id=self._profile.target_tenant_id,
                _request_timeout=self._timeout,
            )
        except self._api_exception_type as e:
            raise VisierSDLCError(_safe_api_error_message(e), step=4) from e
        return _dto_to_dict(response)

    def commit_and_publish(self, project_id: str) -> dict[str, Any]:
        """Step 5 - run Visier ``commitAndPublish`` for this tenant."""
        request = self._project_operation_type(operation="commitAndPublish")
        try:
            response = self._projects_api.run_project_operation(
                project_id,
                request,
                target_tenant_id=self._profile.target_tenant_id,
                _request_timeout=self._timeout,
            )
        except self._api_exception_type as e:
            raise VisierSDLCError(_safe_api_error_message(e), step=5) from e
        return _dto_to_dict(response)

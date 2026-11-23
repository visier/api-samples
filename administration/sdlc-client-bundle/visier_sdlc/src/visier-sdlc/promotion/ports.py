from __future__ import annotations

from typing import Any, Mapping, Protocol


class AppError(Exception):
    def __init__(self, message: str, status: int = 409):
        super().__init__(message)
        self.status = status


class AccessDenied(AppError):
    """The server explicitly rejected a request before applying it."""


class ProjectNotFound(AppError):
    """A draft was already removed (safe when retrying deletion)."""


class StateStore(Protocol):
    """A durable document with atomic compare-and-swap, scoped to a tenant pair."""

    def read(self) -> tuple[int, dict]: ...
    def compare_and_swap(self, revision: int, value: dict) -> None: ...


class CredentialProvider(Protocol):
    def configuration(self, role: str) -> Mapping[str, Any]: ...


class TenantGateway(Protocol):
    def versions(self, role: str) -> list[dict]: ...
    def export(self, first_id: str, last_id: str) -> bytes: ...
    def export_sources(self) -> bytes: ...
    def import_sources(self, archive: bytes, replace_all_existing_sources: bool = False) -> dict: ...
    def create_project(self, name: str, description: str, version_number: int) -> str: ...
    def upload(self, project_id: str, archive: bytes) -> None: ...
    def publish(self, project_id: str) -> str: ...
    def delete_project(self, project_id: str) -> None: ...
    def rollback_project(self, version_id: str) -> str: ...

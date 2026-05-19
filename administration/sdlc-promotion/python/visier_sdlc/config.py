"""
Load per-tenant connection settings (e.g. ``source`` and ``target`` profiles) without hardcoding secrets.

- Supports YAML files with a ``profiles`` map (see ``config.yaml.example``).
- If ``python-dotenv`` is installed, ``.env`` is loaded automatically so you can
  keep secrets in environment variables and reference them from YAML, or set
  ``${VAR_NAME}`` placeholders in the file (see ``load_config``).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

# Optional: load .env before reading YAML so ${VAR} can resolve
try:
    from dotenv import load_dotenv

    _DOTENV = True
except ImportError:  # pragma: no cover - optional dependency
    _DOTENV = False


_ENV_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")


@dataclass(frozen=True)
class EnvironmentProfile:
    """
    Connection details for one Visier tenant (URL + credentials; used for source or target).

    * ``base_url`` — API root, e.g. https://<vanity>.api.visier.io
    * ``api_key`` — sent as the ``apikey`` header (see Visier code samples)
    * ``username`` / ``password`` — used to obtain the ASID token
    * ``target_tenant_id`` — optional ``TargetTenantID`` header (partner / multi-tenant)
    * ``vanity`` — if your tenant requires it, sent as ``vanityName`` on
      ``POST /v1/admin/visierSecureToken`` (matches Visier's Python connector)
    """

    base_url: str
    api_key: str
    username: str
    password: str
    target_tenant_id: str | None = None
    vanity: str | None = None

    @staticmethod
    def from_dict(data: Mapping[str, Any], *, profile_name: str = "profile") -> "EnvironmentProfile":
        missing = [k for k in ("base_url", "api_key", "username", "password") if not data.get(k)]
        if missing:
            hint = (
                " If you use ${VAR_NAME} in config.yaml, that variable must be set in the environment "
                "or in a .env file in the same folder as config.yaml."
            )
            raise ValueError(
                f"Profile {profile_name!r} is missing or has empty values for: {', '.join(missing)}.{hint}"
            )
        base_url = str(data["base_url"]).strip().rstrip("/")
        _validate_base_url(base_url, profile_name=profile_name)
        return EnvironmentProfile(
            base_url=base_url,
            api_key=str(data["api_key"]).strip(),
            username=str(data["username"]).strip(),
            password=str(data["password"]),
            target_tenant_id=(str(data["target_tenant_id"]).strip() if data.get("target_tenant_id") else None),
            vanity=(str(data["vanity"]).strip() if data.get("vanity") else None),
        )


def _expand_env_placeholders(obj: Any) -> Any:
    """Replace ``${VAR}`` in strings, recursively in dicts/lists."""

    if isinstance(obj, str):
        def replacer(match: re.Match[str]) -> str:
            return os.environ.get(match.group(1), "")

        return _ENV_PATTERN.sub(replacer, obj)
    if isinstance(obj, dict):
        return {k: _expand_env_placeholders(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_expand_env_placeholders(v) for v in obj]
    return obj


def _validate_base_url(base_url: str, *, profile_name: str) -> None:
    parsed = urlparse(base_url)
    if parsed.scheme != "https":
        raise ValueError(f"Profile {profile_name!r} base_url must use https://")
    if not parsed.netloc:
        raise ValueError(f"Profile {profile_name!r} base_url must include a host")
    if parsed.query or parsed.fragment:
        raise ValueError(f"Profile {profile_name!r} base_url must not include query strings or fragments")


def load_config(
    path: str | os.PathLike[str] | None = None,
) -> dict[str, EnvironmentProfile]:
    """
    Read ``config.yaml`` and return a map ``profile_name -> EnvironmentProfile``.

    * If ``path`` is None, looks for ``config.yaml`` in the current working directory.
    * If PyYAML is not installed, raises ``ImportError`` with a clear message.
    * Calls ``_expand_env_placeholders`` on the parsed YAML.
    """
    cfg_path = Path(path or os.environ.get("VISIER_SDLC_CONFIG", "config.yaml"))
    if not cfg_path.is_file():
        raise FileNotFoundError(f"Config file not found: {cfg_path.resolve()}")

    # Load .env only from the config file's directory. Loading from cwd as well can
    # accidentally mix credentials when the command is launched from another folder.
    if _DOTENV:
        load_dotenv(cfg_path.parent / ".env")

    try:
        import yaml
    except ImportError as e:  # pragma: no cover
        raise ImportError("Install pyyaml (see requirements.txt) to use config.yaml") from e

    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
    raw = _expand_env_placeholders(raw)
    if not raw or "profiles" not in raw:
        raise ValueError("config.yaml must contain a top-level 'profiles' mapping")
    out: dict[str, EnvironmentProfile] = {}
    for name, p in raw["profiles"].items():
        if not isinstance(p, dict):
            raise ValueError(f"Profile {name!r} must be a mapping (got {type(p).__name__!r})")
        out[str(name)] = EnvironmentProfile.from_dict(p, profile_name=str(name))
    validate_distinct_source_and_target(out)
    return out


def tenant_fingerprint(profile: EnvironmentProfile) -> tuple[str, str | None]:
    """Return a conservative identity tuple for same-tenant safety checks."""
    host = (urlparse(profile.base_url).hostname or profile.base_url).lower()
    return (host, profile.target_tenant_id)


def validate_distinct_source_and_target(config: Mapping[str, EnvironmentProfile]) -> None:
    """Reject configs where source and target clearly point at the same tenant."""
    source = config.get("source")
    target = config.get("target")
    if not source or not target:
        return
    if tenant_fingerprint(source) == tenant_fingerprint(target):
        raise ValueError(
            "profiles.source and profiles.target appear to point at the same tenant. "
            "Use distinct source and target tenants before running this sample."
        )


def get_profile(config: Mapping[str, EnvironmentProfile], name: str) -> EnvironmentProfile:
    """Return a profile by name or raise ``KeyError`` with a short hint."""
    try:
        return config[name]
    except KeyError as e:
        available = ", ".join(sorted(config.keys())) or "(none)"
        raise KeyError(f"Unknown profile {name!r}. Available: {available}") from e


# --- Optional troubleshooting (draft project name / API payload) ---
# Grep: SDLC troubleshooting | visier_sdlc_troubleshoot_logging | VISIER_SDLC_DEBUG
# Set ``VISIER_SDLC_DEBUG=1`` to enable. Remove the guarded log blocks in client.py / workflow.py
# when you no longer need them, or keep with the env var unset.
def visier_sdlc_troubleshoot_logging() -> bool:
    return os.environ.get("VISIER_SDLC_DEBUG", "").strip().lower() in ("1", "true", "yes")

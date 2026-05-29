"""
End-to-end SDLC helper: copy published work from the *source* tenant into a new draft
on the *target* tenant, then publish.

Visier API paths still use names like ``production-versions`` (their terminology for
published configuration history). Each public step helper is numbered to match the brief.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal, TypeVar
from urllib.parse import urlparse

from visier_sdlc.client import NewDraftProject, VisierClient
from visier_sdlc.config import EnvironmentProfile, visier_sdlc_troubleshoot_logging
from visier_sdlc.exceptions import VisierSDLCError

logger = logging.getLogger(__name__)

# --- Auto-generated draft project display name + description (Visier length limits) ----------
_MAX_DRAFT_DISPLAY_NAME_LEN = 50
_MAX_DRAFT_DESC_LEN = 150


def source_tenant_vanity_label(profile: EnvironmentProfile) -> str:
    """
    Short label for the source tenant: explicit ``vanity`` in config, else the hostname
    segment from a typical ``https://<vanity>.api.visier.io`` URL, else the full host.
    """
    if profile.vanity and str(profile.vanity).strip():
        return str(profile.vanity).strip()
    parsed = urlparse(profile.base_url)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        return "source"
    if host.endswith(".api.visier.io") and host != "api.visier.io":
        return host[: -len(".api.visier.io")]
    return host


def _draft_utc_date_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _truncate_draft_display_name(text: str, max_len: int = _MAX_DRAFT_DISPLAY_NAME_LEN) -> str:
    if len(text) <= max_len:
        return text
    if max_len < 2:
        return "…"[:max_len]
    return text[: max_len - 1] + "…"


def _truncate_draft_description(text: str, max_len: int = _MAX_DRAFT_DESC_LEN) -> str:
    text = text.strip()
    if len(text) <= max_len:
        return text
    if max_len < 2:
        return "…"[:max_len]
    return text[: max_len - 1] + "…"


def _base_url_for_description(base: str) -> str:
    """Prefer scheme + host so long paths/query strings do not eat the 150-char budget."""
    parsed = urlparse(base)
    if parsed.netloc and parsed.scheme:
        return f"{parsed.scheme}://{parsed.netloc}"
    if parsed.netloc:
        return parsed.netloc
    return base


def _published_row_for_id(history: dict[str, Any], version_id: str) -> dict[str, Any] | None:
    """
    Return the ``publishedVersions`` entry whose ``id`` matches ``version_id``.

    Match is by stripped string equality on both sides. Returns ``None`` if there is no
    such row (no fallback to another version).
    """
    want = str(version_id).strip()
    versions = _published_versions(history)
    if not versions:
        return None
    for v in versions:
        if not isinstance(v, dict):
            continue
        got = str(v.get("id", "")).strip()
        if got and got == want:
            return v
    return None


def _published_versions(history: dict[str, Any]) -> list[Any]:
    """Return published version rows from either JSON or generated-SDK field names."""
    versions = history.get("publishedVersions")
    if versions is None:
        versions = history.get("published_versions")
    return versions if isinstance(versions, list) else []


def _build_all_mode_display_name(vanity: str) -> str:
    """
    Project display name for ``--mode all`` (max :data:`_MAX_DRAFT_DISPLAY_NAME_LEN` chars).
    """
    s = f"Import full version history from {vanity}"
    return _truncate_draft_display_name(s, _MAX_DRAFT_DISPLAY_NAME_LEN)


def _build_latest_mode_display_name(vanity: str, pv_name: str) -> str:
    """
    Project display name for ``--mode latest`` (max :data:`_MAX_DRAFT_DISPLAY_NAME_LEN` chars).
    Format: ``Imported from {vanity} - {project name}``. Truncates the project name, then
    the whole string, to stay within the limit.
    """
    m = _MAX_DRAFT_DISPLAY_NAME_LEN
    s = f"Imported from {vanity} - {pv_name}"
    if len(s) <= m:
        return s
    prefix = f"Imported from {vanity} - "
    if len(prefix) >= m:
        return _truncate_draft_display_name(s, m)
    room = m - len(prefix)
    if room >= 2:
        if len(pv_name) <= room:
            return prefix + pv_name
        return prefix + pv_name[: room - 1] + "…"
    if room == 1:
        return _truncate_draft_display_name(s, m)
    return _truncate_draft_display_name(s, m)


def build_auto_draft_name_and_description(
    mode: Literal["latest", "all"],
    source_profile: EnvironmentProfile,
    history: dict[str, Any],
    exported_start_version_id: str,
) -> tuple[str, str]:
    """
    Return ``(name, description)`` for the target draft project.

    * **latest** — title includes vanity, published version name, and id.
    * **all** — title is the full-history import; description references vanity and base URL.

    Display names are at most 50 characters; descriptions at most 150 (Visier limits).
    """
    vanity = source_tenant_vanity_label(source_profile)
    base = source_profile.base_url
    base_short = _base_url_for_description(base)
    date = _draft_utc_date_str()

    if mode == "all":
        name = _build_all_mode_display_name(vanity)
        desc = _truncate_draft_description(
            f"Full range from {vanity} on {date}. Source {base_short}. All versions (paginated export)."
        )
        return name, desc

    row = _published_row_for_id(history, exported_start_version_id)
    if not row:
        raise ValueError(
            "Cannot build latest draft name: no publishedVersions row with id matching "
            f"{exported_start_version_id!r}. The exported version must appear in the same "
            "Step 1 history used for auto naming (e.g. use a large enough list limit, "
            "export_full_published_history, or ensure manual export ids are present on the "
            "listed page)."
        )
    pv_name = (row.get("name") or "Published version").strip() or "Published version"
    pv_id = str(row.get("id") or exported_start_version_id)

    name = _build_latest_mode_display_name(vanity, pv_name)
    desc = _truncate_draft_description(
        f"Latest from {vanity} ({base_short}) on {date}. Version \u201c{pv_name}\u201d (id: {pv_id})."
    )
    return name, desc

T = TypeVar("T")


def _run_step(step: int, label: str, fn: Callable[[], T]) -> T:
    """
    Run ``fn`` and re-wrap failures so logs and exceptions always mention ``step`` + ``label``.

    (Inner functions in :class:`VisierClient` already attach ``step`` for HTTP issues; this
    catches anything else, such as key errors when parsing a response.)
    """
    logger.info("--- Step %s — %s ---", step, label)
    try:
        return fn()
    except VisierSDLCError:
        raise
    except Exception as e:  # noqa: BLE001 - surface unexpected bugs with a clear step label
        raise VisierSDLCError(f"{label}: {e}", step=step) from e


# --- Public step wrappers (explicit numbering for learning / scripting) ---


def step0_get_secure_token(client: VisierClient) -> str:
    """Step 0: ``POST /v1/admin/visierSecureToken`` (see :meth:`VisierClient.authenticate`)."""
    return _run_step(0, "Get secure token", client.authenticate)


def step1_list_production_history(client: VisierClient, *, limit: int = 400, start: int = 0) -> dict[str, Any]:
    """
    Step 1: ``GET /v1/admin/production-versions`` — list publish history
    (returns a ``publishedVersions`` list when successful).
    """
    return _run_step(
        1,
        "List published versions at source tenant",
        lambda: client.get_production_versions(limit=limit, start=start),
    )


def step2_download_production_export_zip(
    source: VisierClient,
    start_version: str,
    end_version: str,
    excluded_versions: list[str] | None = None,
) -> bytes:
    """Step 2: ``POST /v1/admin/production-versions`` with ``export`` operation (ZIP)."""
    return _run_step(
        2,
        "Download published-version export (ZIP) from source tenant",
        lambda: source.export_production_versions_zip(
            start_version,
            end_version,
            excluded_versions=excluded_versions,
        ),
    )


def step3_create_blank_project_on_target(
    target: VisierClient,
    project: NewDraftProject,
) -> dict[str, Any]:
    """Step 3: ``POST /v1/admin/projects`` — new draft on the *target* tenant."""
    return _run_step(3, "Create blank draft project in target tenant", lambda: target.create_draft_project(project))


def step4_import_zip_into_target_project(
    target: VisierClient,
    project_id: str,
    zip_bytes: bytes,
) -> dict[str, Any]:
    """Step 4: ``PUT /v1/admin/projects/{id}/commits`` (ZIP from Step 2)."""
    return _run_step(
        4,
        "Import ZIP into target tenant draft project",
        lambda: target.import_commits(project_id, zip_bytes),
    )


def step5_publish_target_project(target: VisierClient, project_id: str) -> dict[str, Any]:
    """Step 5: ``POST /v1/admin/projects/{id}`` with ``commitAndPublish``."""
    return _run_step(
        5,
        "Commit and publish draft in target tenant",
        lambda: target.commit_and_publish(project_id),
    )


@dataclass
class PromotionResult:
    """Summary returned to the caller after a successful end-to-end run."""

    published_versions_list: dict[str, Any]
    """Exact JSON from ``GET /v1/admin/production-versions`` (Step 1)."""
    export_start_version_id: str
    """Production version id passed to the export call (start of range)."""
    export_end_version_id: str
    """Production version id passed to the export call (end of range)."""
    planned_project: NewDraftProject
    """Draft project values that will be used if target changes are applied."""
    export_zip_size_bytes: int | None = None
    """ZIP size when Step 2 ran; ``None`` in preview mode."""
    new_project: dict[str, Any] | None = None
    """Step 3 response when target changes were applied; ``None`` in preview mode."""
    import_result: dict[str, Any] | None = None
    """Step 4 response when target changes were applied; ``None`` in preview mode."""
    publish_result: dict[str, Any] | None = None
    """Step 5 JSON when publish ran; ``None`` unless publishing was requested."""


@dataclass
class PromotionRequest:
    """All inputs required to run the workflow in one call."""

    new_project: NewDraftProject
    export_excluded_version_ids: list[str] | None = None
    # --- Export version selection (ties Step 1 → Step 2 together) ---
    # Visier returns ``publishedVersions`` newest-first. If you leave the manual ids unset,
    # the workflow uses ``publishedVersions[export_published_version_index]`` for BOTH
    # start and end (a single-version export), unless ``export_full_published_history`` is True.
    export_start_version_id: str | None = None
    export_end_version_id: str | None = None
    export_published_version_index: int = 0
    # When True, Step 1 lists *all* pages of published versions, then export uses the **oldest**
    # and **newest** id in that list as ``startVersion`` / ``endVersion`` (full range in one ZIP).
    # Incompatible with manual ``export_start_version_id`` / ``export_end_version_id`` or index mode.
    export_full_published_history: bool = False
    # Single-page GET (when not using export_full_published_history).
    source_production_versions_list_limit: int = 400
    source_production_versions_list_start: int = 0
    # Page size when fetching every page for ``export_full_published_history``.
    source_production_versions_page_size: int = 400
    # When set to ``"latest"`` or ``"all"``, ``name`` / ``description`` on ``new_project`` are
    # replaced using the source profile and Step 1 history (vanity + base URL in both cases).
    auto_draft_naming: Literal["latest", "all"] | None = None
    # Default is a preview: authenticate source, list versions, choose the export range,
    # and compute the target draft metadata. No ZIP export and no target mutation happen
    # unless ``apply_to_target`` is True.
    apply_to_target: bool = False
    # Publishing is production-impacting. Keep it separate from applying the import so
    # callers can create and inspect a target draft without committing it.
    publish: bool = False


def pick_export_version_ids(
    history: dict[str, Any],
    request: PromotionRequest,
) -> tuple[str, str]:
    """
    Decide which production version UUIDs to send to ``POST …/production-versions`` (export).

    * If ``export_start_version_id`` and ``export_end_version_id`` are both set, those values
      are used (manual range — can differ for multi-version exports). Not used with
      ``export_full_published_history``.
    * If ``export_full_published_history`` is True, ``startVersion``/``endVersion`` are
      the **oldest** and **newest** version in ``history`` (list is newest-first from Visier).
    * Otherwise, if both manual ids are ``None``, ids are taken from a single list row using
      ``export_published_version_index`` (default ``0`` = latest only).
    * Setting only one of the manual ids is not allowed (ambiguous).
    """
    manual_start = request.export_start_version_id
    manual_end = request.export_end_version_id
    if request.export_full_published_history:
        if manual_start is not None or manual_end is not None:
            raise VisierSDLCError(
                "Do not set export_start_version_id / export_end_version_id when using "
                "export_full_published_history (or turn export_full_published_history off).",
                step=1,
            )
        versions = _published_versions(history)
        if not versions:
            raise VisierSDLCError(
                "No publishedVersions in the API response (or list is empty); nothing to export.",
                step=1,
            )
        if len(versions) == 1:
            v = str(versions[0]["id"])
            if not v:
                raise VisierSDLCError("publishedVersions[0] has no 'id' field.", step=1)
            return v, v
        # Newest-first: index 0 = latest publish, -1 = oldest in the merged list.
        oldest = versions[-1]
        newest = versions[0]
        if not isinstance(oldest, dict) or not isinstance(newest, dict):
            raise VisierSDLCError("publishedVersions entries are not objects; cannot read id.", step=1)
        oid, nid = oldest.get("id"), newest.get("id")
        if not oid or not nid:
            raise VisierSDLCError("publishedVersions item missing 'id' (full-history export).", step=1)
        return str(oid), str(nid)

    if manual_start is not None or manual_end is not None:
        if manual_start is None or manual_end is None:
            raise VisierSDLCError(
                "Set both export_start_version_id and export_end_version_id for a manual range, "
                "or leave both unset to auto-select from GET /v1/admin/production-versions.",
                step=1,
            )
        return manual_start.strip(), manual_end.strip()

    versions = _published_versions(history)
    if not versions:
        raise VisierSDLCError(
            "No publishedVersions in the API response (or list is empty); nothing to export.",
            step=1,
        )
    idx = request.export_published_version_index
    if idx < 0 or idx >= len(versions):
        raise VisierSDLCError(
            f"export_published_version_index={idx} is out of range "
            f"(API returned {len(versions)} production version(s)).",
            step=1,
        )
    entry = versions[idx]
    if not isinstance(entry, dict):
        raise VisierSDLCError(f"publishedVersions[{idx}] is not an object; cannot read id.", step=1)
    vid = entry.get("id")
    if not vid:
        raise VisierSDLCError(f"publishedVersions[{idx}] has no 'id' field.", step=1)
    return str(vid), str(vid)


def run_sdlc_promotion(
    source: VisierClient,
    target: VisierClient,
    request: PromotionRequest,
) -> PromotionResult:
    """
    Run a guarded SDLC promotion workflow.

    By default, this is a preview: authenticate the source tenant, list source published
    history, choose the export ids, and compute target draft metadata. It does not export
    the ZIP and does not mutate the target tenant.

    Set ``apply_to_target=True`` to export the ZIP, authenticate the target tenant, create
    a target draft, and import the ZIP. Set ``publish=True`` as well to run Step 5
    ``commitAndPublish``.

    Export version ids for Step 2 are resolved from the Step 1 response unless you set
    ``export_start_version_id`` / ``export_end_version_id``. Use
    ``export_full_published_history=True`` to export every published version returned by a
    paginated listing (oldest→newest span).

    Set ``auto_draft_naming`` to ``"latest"`` or ``"all"`` to fill the target draft
    project name and description (vanity + base URL; for ``latest``, the exported
    version’s name and id as well).
    """
    if request.publish and not request.apply_to_target:
        raise VisierSDLCError("publish=True requires apply_to_target=True.", step=None)

    step0_get_secure_token(source)
    if request.export_full_published_history:
        history = _run_step(
            1,
            "List all published versions at source tenant (paginated)",
            lambda: source.get_all_published_production_versions(
                page_size=request.source_production_versions_page_size
            ),
        )
    else:
        history = step1_list_production_history(
            source,
            limit=request.source_production_versions_list_limit,
            start=request.source_production_versions_list_start,
        )
    start_id, end_id = pick_export_version_ids(history, request)
    logger.info("Selected published version range (start=%s, end=%s).", start_id, end_id)
    if request.auto_draft_naming is not None:
        try:
            auto_name, auto_desc = build_auto_draft_name_and_description(
                request.auto_draft_naming,
                source.profile,
                history,
                start_id,
            )
        except ValueError as e:
            raise VisierSDLCError(f"Auto draft naming failed: {e}", step=1) from e
        base = request.new_project
        draft_project = NewDraftProject(
            name=auto_name,
            description=auto_desc,
            release_version=base.release_version,
            ticket_number=base.ticket_number,
            version_number=base.version_number,
        )
    else:
        draft_project = request.new_project
    if visier_sdlc_troubleshoot_logging():
        logger.info(
            "[SDLC troubleshooting] Step 3 NewDraftProject: name=%r (len=%s) description_len=%s",
            draft_project.name,
            len(draft_project.name or ""),
            len(draft_project.description or ""),
        )
    if not request.apply_to_target:
        logger.info("Preview only: no ZIP export, target draft creation, import, or publish was run.")
        return PromotionResult(
            published_versions_list=history,
            export_start_version_id=start_id,
            export_end_version_id=end_id,
            planned_project=draft_project,
        )

    zip_bytes = step2_download_production_export_zip(
        source,
        start_id,
        end_id,
        request.export_excluded_version_ids,
    )
    step0_get_secure_token(target)
    created = step3_create_blank_project_on_target(target, draft_project)
    project_id = created.get("id")
    if not project_id:
        raise VisierSDLCError("Create project response missing 'id' field; cannot import.", step=3)
    imported = step4_import_zip_into_target_project(target, str(project_id), zip_bytes)
    if not request.publish:
        logger.info(
            "No publish requested: stopping before Step 5. Draft project %s exists on target with import applied; "
            "not publishing.",
            project_id,
        )
        return PromotionResult(
            published_versions_list=history,
            export_start_version_id=start_id,
            export_end_version_id=end_id,
            planned_project=draft_project,
            export_zip_size_bytes=len(zip_bytes),
            new_project=created,
            import_result=imported,
            publish_result=None,
        )
    published = step5_publish_target_project(target, str(project_id))
    logger.info("SDLC promotion finished. Draft project %s published in target tenant.", project_id)
    return PromotionResult(
        published_versions_list=history,
        export_start_version_id=start_id,
        export_end_version_id=end_id,
        planned_project=draft_project,
        export_zip_size_bytes=len(zip_bytes),
        new_project=created,
        import_result=imported,
        publish_result=published,
    )


# Backward compatibility (older name)
run_dev_to_production_sdlc = run_sdlc_promotion

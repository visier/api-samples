from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from .ports import AccessDenied, AppError


DEFAULT_PROJECT_NAME = "Development tenant promotion"


def timestamp():
    return datetime.now(timezone.utc).isoformat()


class PromotionService:
    def __init__(self, gateway, store, source_name="Development", target_name="Production", mode="demo"):
        self.gateway, self.store = gateway, store
        self.source_name, self.target_name, self.mode = source_name, target_name, mode

    def snapshot(self):
        # Tenant reads can overlap a publish/checkpoint update in another worker.
        # Retry rather than compare a new checkpoint with an older history.
        for _ in range(3):
            revision, state = self.store.read()
            source, target = self.gateway.versions("source"), self.gateway.versions("target")
            if self.store.read()[0] == revision:
                break
        else:
            raise AppError("An operation changed while refreshing tenant histories. Refresh to see its progress.")
        checkpoint = state.get("checkpoint")
        operation = state.get("operation")
        publishing = bool(operation and operation["step"] == "publish"
                          and operation["status"] in ("running", "needs_review"))
        source_ids = [v["id"] for v in source]
        target_ids = [v["id"] for v in target]
        issue = None
        if checkpoint and checkpoint["source_id"] not in source_ids:
            issue = "The development baseline version is missing. Restore its history or reset the sync baseline after verifying the tenant states."
        if checkpoint and checkpoint["target_id"] not in target_ids:
            issue = "The production baseline version is missing. Restore its history or reset the sync baseline after verifying the tenant states."
        boundary = source_ids.index(checkpoint["source_id"]) if checkpoint and checkpoint["source_id"] in source_ids else len(source)
        pending = source[:boundary]
        baseline = source[boundary:boundary + 1] if checkpoint and not issue else []
        # A version can become visible before publish returns its confirmed ID.
        # Keep pre-existing drift, but leave newer versions unclassified until
        # this publication is confirmed (or reconciled after an uncertain result).
        target_head = target_ids[0] if target_ids else None
        if publishing:
            target_head = operation["target_before"]
        drift = bool(checkpoint and target_head and target_head != checkpoint["target_id"])
        # An existing target without a verified checkpoint is not assumed safe.
        if not checkpoint and target and not (publishing and operation["target_before"] is None):
            issue = "Set a verified source and production baseline before the first sync to an existing tenant."
        managed = set(state.get("managed_target_ids", []))
        if checkpoint:
            managed.add(checkpoint["target_id"])
        target_boundary = target_ids.index(checkpoint["target_id"]) if checkpoint and checkpoint["target_id"] in target_ids else 0
        publication_boundary = 0
        if publishing:
            publication_boundary = target_ids.index(target_head) if target_head in target_ids else len(target)
        target_rows = []
        for i, version in enumerate(target):
            if version["id"] in managed:
                status = "synced"
            elif i < publication_boundary:
                status = "unconfirmed"
            elif checkpoint and i < target_boundary:
                status = "drift"
            else:
                status = "historical"
            target_rows.append(dict(version, status=status))
        last_sources_operation = next((record["id"] for record in reversed(state.get("history", []))
                                       if record["kind"] == "sources"), None)
        fingerprint = hashlib.sha256(json.dumps([source_ids, target_ids, checkpoint, last_sources_operation], sort_keys=True).encode()).hexdigest()
        return dict(source_name=self.source_name, target_name=self.target_name, mode=self.mode,
                    source=[dict(v, status="pending") for v in pending] + [dict(v, status="synced") for v in baseline],
                    target=target_rows, pending_count=len(pending), drift=drift, issue=issue,
                    next_version_number=((target[0].get("number") or 0) if target else 0) + 1,
                    baseline_versions=dict(source=source, target=target),
                    checkpoint=checkpoint, fingerprint=fingerprint, operation=operation,
                    can_rollback=bool(drift and not issue and not operation),
                    history=list(reversed(state.get("history", []))), checked_at=timestamp(), state_revision=revision)

    def rebaseline(self, fingerprint, *, source_id=None, target_id=None, reason=None, verified=False):
        """Record an operator-verified relationship without writing to either tenant."""
        if verified is not True:
            raise AppError("Confirm that source changes through the baseline are accounted for in the target and accepted target changes will not cause merge conflicts with pending development changes.", 400)
        if not isinstance(reason, str) or not reason.strip() or len(reason) > 1000:
            raise AppError("Provide a reason for resetting the baseline (up to 1000 characters).", 400)
        if source_id is None and target_id is None:
            raise AppError("Choose a source baseline, target baseline, or both.", 400)
        snapshot = self.snapshot()
        if snapshot["operation"]:
            raise AppError("An operation is already active or awaiting reconciliation. Reconcile it before resetting the baseline.")
        if fingerprint != snapshot["fingerprint"]:
            raise AppError("Tenant versions changed since your last refresh. Review the updated lists and try again.")
        before = snapshot["checkpoint"]
        after = dict(source_id=source_id if source_id is not None else (before or {}).get("source_id"),
                     target_id=target_id if target_id is not None else (before or {}).get("target_id"))
        for role in ("source", "target"):
            value = after[role + "_id"]
            if not isinstance(value, str) or value not in [v["id"] for v in snapshot["baseline_versions"][role]]:
                raise AppError(f"Choose an existing {role} version. Both baselines must exist in the tenant histories.", 400)
        if before and all(before[key] == value for key, value in after.items()):
            raise AppError("The selected versions already match the saved baseline.", 400)
        at = timestamp()
        # A baseline assertion is not a successful publication timestamp.
        after.update(at=None, rebaselined_at=at)
        revision, state = self.store.read()
        if state.get("operation") or revision != snapshot["state_revision"]:
            raise AppError("State changed in another session. Refresh and review the baseline again.")
        state["checkpoint"] = after
        state.setdefault("history", []).append(dict(
            id=uuid.uuid4().hex, kind="rebaseline", status="succeeded", step="complete",
            started_at=at, finished_at=at, before=before, after=after,
            scope="both" if source_id is not None and target_id is not None else "source" if source_id is not None else "target",
            reason=reason.strip(), verified=True))
        self.store.compare_and_swap(revision, state)
        return {"message": "Sync baseline reset. Tenant versions were not changed."}

    def _save_operation(self, id, **changes):
        revision, state = self.store.read()
        if not state.get("operation") or state["operation"]["id"] != id:
            raise AppError("Operation ownership changed. Review the operation before retrying.")
        state["operation"].update(changes)
        self.store.compare_and_swap(revision, state)

    def run(self, kind, fingerprint, version_id=None, *, project_name=DEFAULT_PROJECT_NAME, project_description=""):
        if kind == "sync":
            if not isinstance(project_name, str) or not project_name.strip():
                raise AppError("Provide a draft project display name.", 400)
            project_name = project_name.strip()
            if len(project_name) > 50:
                raise AppError("The draft project display name must be 50 characters or fewer.", 400)
            if not isinstance(project_description, str):
                raise AppError("Provide the draft project description as text.", 400)
        snapshot = self.snapshot()
        if snapshot["operation"]:
            raise AppError("An operation is already active or awaiting reconciliation.")
        if snapshot["issue"]:
            raise AppError(snapshot["issue"])
        if fingerprint != snapshot["fingerprint"]:
            raise AppError("Tenant versions changed since your last refresh. Review the updated lists and try again.")
        selected = []
        if kind == "sync":
            if snapshot["drift"]:
                raise AppError("Resolve production drift with a rollback, or reset the target baseline after verifying that the production changes will not cause merge conflicts with pending development changes.")
            pending = [v for v in snapshot["source"] if v["status"] == "pending"]
            ids = [v["id"] for v in pending]
            if version_id not in ids:
                raise AppError("Select an unsynchronized development version.", 400)
            # API lists are newest-first; include every older unsynchronized change.
            selected = list(reversed(pending[ids.index(version_id):]))
        elif kind == "rollback":
            if not snapshot["can_rollback"]:
                raise AppError("There is no production drift to roll back.")
        else:
            raise AppError("Unknown operation.", 400)
        id = uuid.uuid4().hex
        operation = dict(id=id, kind=kind, status="running", step="export" if kind == "sync" else "rollback",
                         started_at=timestamp(), count=len(selected), source_id=version_id,
                         target_before=snapshot["target"][0]["id"] if snapshot["target"] else None,
                         project_id=None)
        if kind == "sync":
            operation.update(project_name=project_name, project_description=project_description,
                             version_number=snapshot["next_version_number"])
        revision, state = self.store.read()
        if state.get("operation") or revision != snapshot["state_revision"]:
            raise AppError("Another operation started. Refresh to see its progress.")
        # Claim durably before contacting either tenant. Other workers and restarts
        # see the claim and cannot repeat a potentially successful publish.
        state["operation"] = operation
        self.store.compare_and_swap(revision, state)
        publishing = False
        try:
            if kind == "sync":
                archive = self.gateway.export(selected[0]["id"], selected[-1]["id"])
                self._save_operation(id, step="create")
                project_id = self.gateway.create_project(project_name, project_description, operation["version_number"])
                self._save_operation(id, project_id=project_id, step="upload")
                self.gateway.upload(project_id, archive)
            else:
                project_id = self.gateway.rollback_project(snapshot["checkpoint"]["target_id"])
                self._save_operation(id, project_id=project_id)
            # Recheck target immediately before publication; catch drift introduced
            # during export/import. Visier has no conditional-publish endpoint.
            target = self.gateway.versions("target")
            if (target[0]["id"] if target else None) != operation["target_before"]:
                raise AppError("Production changed during preparation. The draft was kept; refresh and review production.")
            self._save_operation(id, step="publish")
            publishing = True
            target_id = self.gateway.publish(project_id)
            self._save_operation(id, published_target_id=target_id)
            self._finish(id, target_id)
            return {"message": f"{len(selected)} development version{'s' if len(selected) != 1 else ''} synchronized successfully." if kind == "sync" else "Production restored to the last synchronized state."}
        except Exception as error:
            if publishing:
                self._publication_failed(id, error)
            else:
                self._abandon(id, "Preparation failed; sync checkpoint was not advanced.")
            if isinstance(error, AppError):
                raise
            # SDK exceptions can contain secrets and server payloads. Never send
            # their raw text to the browser or log them with request headers.
            raise AppError("Visier could not complete the operation. Check tenant access and review the activity details.", 502) from None

    def _publication_failed(self, id, error):
        rejected = isinstance(error, AccessDenied)
        message = ("Publication was denied. Correct the target user's permissions, then retry publishing this draft or discard it."
                   if rejected else "Publication may have completed. Verify the result in Visier, then use Recover operation to continue.")
        self._save_operation(id, status="retryable" if rejected else "needs_review", message=message)

    def _abandon(self, id, message):
        revision, state = self.store.read()
        operation = state.get("operation")
        if not operation or operation["id"] != id:
            raise AppError("Operation ownership changed. Refresh before recovering it.")
        operation.update(status="failed", finished_at=timestamp(), message=message)
        state.setdefault("history", []).append(operation)
        state["operation"] = None
        self.store.compare_and_swap(revision, state)

    def recover(self, operation_id, state_revision, action, *, verified=False, target_id=None):
        """Recover the exact reviewed operation; fence stale workers before writes."""
        if action not in ("retry", "discard", "dismiss", "published"):
            raise AppError("Choose a recovery action.", 400)
        if verified is not True:
            raise AppError("Verify the outcome in Visier and confirm that the original operation is no longer running.", 400)
        revision, state = self.store.read()
        operation = state.get("operation")
        if revision != state_revision or not operation or operation["id"] != operation_id:
            raise AppError("The operation changed. Refresh and review recovery again.")
        if operation["kind"] not in ("sync", "rollback"):
            raise AppError("Source imports must be reconciled after checking the target sources.", 400)
        if action == "retry" and (operation["step"] != "publish" or not operation.get("project_id")):
            raise AppError("This draft cannot be published again. Discard or dismiss the operation and start a new promotion.")
        if action == "discard" and not operation.get("project_id"):
            raise AppError("No draft ID was saved. Inspect Visier for any unfinished draft, then dismiss this operation.")
        if action in ("retry", "published"):
            target_ids = [v["id"] for v in self.gateway.versions("target")]
            if action == "retry" and (target_ids[0] if target_ids else None) != operation["target_before"]:
                raise AppError("Production changed since this draft was prepared. Confirm its publication, or dismiss/discard it and review production before starting again.")
            if action == "published":
                boundary = target_ids.index(operation["target_before"]) if operation["target_before"] in target_ids else len(target_ids)
                if not isinstance(target_id, str) or target_id not in target_ids[:boundary]:
                    raise AppError("Choose the new production version verified to have been published by this operation.", 400)
        if operation.get("published_target_id") and (action != "published" or target_id != operation["published_target_id"]):
            raise AppError("Visier confirmed publication. Confirm the saved production version to complete recovery.")
        # Re-read after tenant reads. Compare-and-swap prevents simultaneous
        # recoveries; a fresh ID prevents an old worker finalizing this claim.
        current_revision, current = self.store.read()
        if current_revision != revision:
            raise AppError("The operation changed. Refresh and review recovery again.")
        if action == "retry":
            current.setdefault("history", []).append(dict(operation, status="failed", finished_at=timestamp(),
                                                        message=operation.get("message") or "Interrupted publication; operator verified it was not published."))
        id = uuid.uuid4().hex
        current["operation"] = dict(operation, id=id, previous_operation_id=operation_id,
                                    status="running", recovery_action=action, recovery_verified_at=timestamp())
        current["operation"].pop("message", None)
        if action == "discard":
            current["operation"]["step"] = "delete"
        self.store.compare_and_swap(revision, current)
        if action == "published":
            self._finish(id, target_id)
            return {"message": "Publication confirmed. The sync checkpoint has been updated."}
        if action == "dismiss":
            self._abandon(id, "Operator confirmed no publication. Operation dismissed; any draft was retained in Visier.")
            return {"message": "Operation dismissed. You can start again; any draft remains in Visier."}
        try:
            if action == "discard":
                self.gateway.delete_project(operation["project_id"])
                self._abandon(id, "Operator confirmed no publication. Draft deleted; sync checkpoint was not advanced.")
                return {"message": "Draft deleted. You can start a new promotion."}
            target_id = self.gateway.publish(operation["project_id"])
            self._save_operation(id, published_target_id=target_id)
            self._finish(id, target_id)
            return {"message": "Draft published successfully."}
        except Exception as error:
            if action == "retry":
                self._publication_failed(id, error)
            else:
                self._save_operation(id, status="needs_review", message="Draft deletion could not be confirmed. Retry deletion, or dismiss the operation and keep any remaining draft in Visier.")
            if isinstance(error, AppError):
                raise
            raise AppError("Visier could not complete recovery. Review the operation and try again.", 502) from None

    def _finish(self, id, target_id):
        revision, state = self.store.read()
        operation = state.get("operation")
        if not operation or operation["id"] != id:
            raise AppError("Cannot finalize an operation owned by another session.")
        if operation["kind"] == "sources":
            raise AppError("Source migrations must be reconciled by checking the target sources, not a production version.")
        checkpoint = state.get("checkpoint", {})
        state["checkpoint"] = dict(source_id=operation["source_id"] if operation["kind"] == "sync" else checkpoint["source_id"],
                                   target_id=target_id, at=timestamp() if operation["kind"] == "sync" else checkpoint.get("at"))
        if operation["kind"] == "rollback" and checkpoint.get("rebaselined_at"):
            state["checkpoint"]["rebaselined_at"] = checkpoint["rebaselined_at"]
        state.setdefault("managed_target_ids", []).append(target_id)
        operation.update(status="succeeded", step="complete", target_id=target_id, finished_at=timestamp())
        state.setdefault("history", []).append(operation)
        state["operation"] = None
        self.store.compare_and_swap(revision, state)

    def migrate_sources(self, fingerprint, *, replace_all_existing_sources=False):
        if type(replace_all_existing_sources) is not bool:
            raise AppError("replace_all_existing_sources must be a boolean.", 400)
        snapshot = self.snapshot()
        if snapshot["operation"]:
            raise AppError("An operation is already active or awaiting reconciliation.")
        if fingerprint != snapshot["fingerprint"]:
            raise AppError("Tenant state changed since your last refresh. Review the updated state and try again.")
        id = uuid.uuid4().hex
        revision, state = self.store.read()
        if state.get("operation") or revision != snapshot["state_revision"]:
            raise AppError("Another operation started. Refresh to see its progress.")
        state["operation"] = dict(id=id, kind="sources", status="running", step="export_sources",
                                  started_at=timestamp(), replace_all_existing_sources=replace_all_existing_sources)
        self.store.compare_and_swap(revision, state)
        importing = False
        try:
            archive = self.gateway.export_sources()
            self._save_operation(id, step="import_sources")
            # Once the PUT may have reached Visier, never retry automatically.
            importing = True
            summary = self.gateway.import_sources(archive, replace_all_existing_sources=replace_all_existing_sources)
            self._finish_sources(id, summary=summary)
            return dict(message="Unversioned sources migrated successfully.", summary=summary)
        except Exception as error:
            if importing:
                self._save_operation(id, status="needs_review", message="Source import may have completed. Verify the target sources and reconcile before retrying.")
            else:
                self._finish_sources(id, succeeded=False, message="Source export failed. No target sources were changed.")
            if isinstance(error, AppError):
                raise
            raise AppError("Visier could not complete the source migration. Review the activity details and target sources.", 502) from None

    def _finish_sources(self, id, *, summary=None, succeeded=True, message=None):
        revision, state = self.store.read()
        operation = state.get("operation")
        if not operation or operation["id"] != id or operation["kind"] != "sources":
            raise AppError("Cannot finalize a source migration owned by another session.")
        operation.update(status="succeeded" if succeeded else "failed", finished_at=timestamp())
        if succeeded:
            operation["step"] = "complete"
        if summary is not None:
            operation["summary"] = summary
        if message:
            operation["message"] = message
        else:
            operation.pop("message", None)
        state.setdefault("history", []).append(operation)
        state["operation"] = None
        self.store.compare_and_swap(revision, state)

    def reconcile(self, target_id=None, not_published=False, *, sources_imported=False, not_imported=False):
        """Operator-only recovery after checking Visier; exposed through the CLI."""
        _, state = self.store.read()
        operation = state.get("operation")
        if not operation:
            raise AppError("No unresolved operation exists.")
        if sum(bool(option) for option in (target_id, not_published, sources_imported, not_imported)) != 1:
            raise AppError("Choose exactly one reconciliation outcome.", 400)
        if operation["kind"] == "sources":
            if not (sources_imported or not_imported):
                raise AppError("Verify the target sources and choose --sources-imported or --not-imported.", 400)
            self._finish_sources(operation["id"], succeeded=sources_imported,
                                 message="Operator verified the target sources and confirmed the import completed."
                                 if sources_imported else "Operator confirmed the source import did not complete; inspect any partial changes before retrying.")
            return
        if sources_imported or not_imported:
            raise AppError("The unresolved operation is a version operation, not a source migration.", 400)
        if target_id:
            if target_id not in [v["id"] for v in self.gateway.versions("target")]:
                raise AppError("The confirmed production version does not exist.")
            self._finish(operation["id"], target_id)
        elif not_published:
            revision, state = self.store.read()
            state["operation"].update(status="failed", finished_at=timestamp(), message="Operator confirmed the operation was not published.")
            state.setdefault("history", []).append(state["operation"])
            state["operation"] = None
            self.store.compare_and_swap(revision, state)
        else:
            raise AppError("Supply a confirmed production version or confirm that nothing was published.")

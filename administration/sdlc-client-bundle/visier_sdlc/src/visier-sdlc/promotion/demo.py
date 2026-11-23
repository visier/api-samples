from __future__ import annotations

import io
import json
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

from .ports import AppError


def now():
    return datetime.now(timezone.utc).isoformat()


def seed_demo(store):
    revision, state = store.read()
    if "demo" in state:
        return
    today = datetime.now(timezone.utc)
    def version(id, number, description, owner, hours):
        return dict(id=id, number=number, description=description, owner=owner,
                    published_at=(today - timedelta(hours=hours)).isoformat())
    source = [
        version("dev-128", 128, "Add workforce planning metrics", "Alex Morgan", 1),
        version("dev-127", 127, "Update retention risk calculations", "Sarah Chen", 4),
        version("dev-126", 126, "Refine headcount & movement analysis", "Alex Morgan", 7),
        version("dev-125", 125, "Refresh organizational hierarchy", "Jamie Patel", 25),
    ]
    target = [
        version("prod-87", 87, "Adjust regional access permissions", "Taylor Kim", 2),
        version("prod-86", 86, "Refresh organizational hierarchy", "Promotion service", 24),
        version("prod-85", 85, "Update talent acquisition dashboard", "Promotion service", 48),
    ]
    state.update(demo=dict(source=source, target=target, drafts={}),
                 checkpoint=dict(source_id="dev-125", target_id="prod-86", at=target[1]["published_at"]),
                 managed_target_ids=["prod-86", "prod-85"], history=[], operation=None)
    store.compare_and_swap(revision, state)


class DemoGateway:
    """A persistent simulated tenant, using the same application service as live mode."""

    def __init__(self, store):
        self.store = store
        seed_demo(store)

    def versions(self, role):
        return self.store.read()[1]["demo"][role]

    def export(self, first_id, last_id):
        versions = list(reversed(self.versions("source")))
        ids = [v["id"] for v in versions]
        changes = versions[ids.index(first_id):ids.index(last_id) + 1]
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w") as archive:
            archive.writestr("changes.json", json.dumps(changes))
        return data.getvalue()

    def _sources(self, role):
        # Defaults also make existing persisted demos usable after an upgrade.
        defaults = {
            "source": [{"id": "employees", "name": "Employees", "schema": 2},
                       {"id": "movements", "name": "Movements", "schema": 1}],
            "target": [{"id": "employees", "name": "Employees", "schema": 1},
                       {"id": "production-only", "name": "Production only", "schema": 1}],
        }
        return self.store.read()[1]["demo"].get("sources", defaults)[role]

    def export_sources(self):
        data = io.BytesIO()
        with zipfile.ZipFile(data, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("sources.json", json.dumps(self._sources("source")))
        return data.getvalue()

    def import_sources(self, archive, replace_all_existing_sources=False):
        with zipfile.ZipFile(io.BytesIO(archive)) as contents:
            sources = json.loads(contents.read("sources.json"))
        previous = {source["id"]: source for source in self._sources("target")}
        incoming = {source["id"]: source for source in sources}
        summary = dict(created=0, updated=0, ignored=0, deleted=0)
        for id, source in incoming.items():
            summary["created" if id not in previous else "ignored" if source == previous[id] else "updated"] += 1
        if replace_all_existing_sources:
            summary["deleted"] = len(previous.keys() - incoming.keys())
            target = sources
        else:
            target = list((previous | incoming).values())
        source = self._sources("source")
        revision, state = self.store.read()
        state["demo"]["sources"] = dict(source=source, target=target)
        self.store.compare_and_swap(revision, state)
        return summary

    def create_project(self, name, description, version_number):
        revision, state = self.store.read()
        id = "draft-" + uuid.uuid4().hex[:12]
        state["demo"]["drafts"][id] = dict(name=name, description=description, version_number=version_number)
        self.store.compare_and_swap(revision, state)
        return id

    def upload(self, project_id, archive):
        with zipfile.ZipFile(io.BytesIO(archive)) as contents:
            changes = json.loads(contents.read("changes.json"))
        revision, state = self.store.read()
        state["demo"]["drafts"][project_id]["changes"] = changes
        self.store.compare_and_swap(revision, state)

    def publish(self, project_id):
        revision, state = self.store.read()
        draft = state["demo"]["drafts"].pop(project_id)
        versions = state["demo"]["target"]
        number = draft["version_number"]
        id = "prod-" + str(number)
        description = draft["description"] or draft["name"]
        versions.insert(0, dict(id=id, number=number, description=description,
                                owner="Promotion service", published_at=now()))
        self.store.compare_and_swap(revision, state)
        return id

    def rollback_project(self, version_id):
        if version_id not in [v["id"] for v in self.versions("target")]:
            raise AppError("The rollback version is no longer available.")
        target = self.versions("target")
        number = ((target[0].get("number") or 0) if target else 0) + 1
        id = self.create_project("Rollback", "Rollback to synchronized version", number)
        revision, state = self.store.read()
        state["demo"]["drafts"][id]["rollback"] = version_id
        self.store.compare_and_swap(revision, state)
        return id

    def delete_project(self, project_id):
        revision, state = self.store.read()
        state["demo"]["drafts"].pop(project_id, None)
        self.store.compare_and_swap(revision, state)

    def add_drift(self):
        revision, state = self.store.read()
        if state.get("operation"):
            raise AppError("Wait for the active operation to finish.")
        versions = state["demo"]["target"]
        number = versions[0]["number"] + 1
        versions.insert(0, dict(id=f"prod-{number}", number=number,
                                description="Direct production configuration change", owner="Taylor Kim", published_at=now()))
        self.store.compare_and_swap(revision, state)

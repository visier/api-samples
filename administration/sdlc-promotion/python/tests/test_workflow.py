from __future__ import annotations

import unittest

from visier_sdlc.client import NewDraftProject
from visier_sdlc.config import EnvironmentProfile
from visier_sdlc.workflow import (
    PromotionRequest,
    build_auto_draft_name_and_description,
    pick_export_version_ids,
    run_sdlc_promotion,
)


class FakeClient:
    def __init__(self, profile: EnvironmentProfile) -> None:
        self.profile = profile
        self.calls: list[str] = []

    def authenticate(self) -> str:
        self.calls.append("authenticate")
        return "token"

    def get_production_versions(self, *, limit: int = 400, start: int = 0) -> dict:
        self.calls.append(f"get_production_versions:{limit}:{start}")
        return {
            "publishedVersions": [
                {"id": "newest", "name": "Newest project"},
                {"id": "oldest", "name": "Oldest project"},
            ]
        }

    def get_all_published_production_versions(self, *, page_size: int = 400) -> dict:
        self.calls.append(f"get_all_published_production_versions:{page_size}")
        return self.get_production_versions()

    def export_production_versions_zip(self, start_version: str, end_version: str, excluded_versions=None) -> bytes:
        self.calls.append(f"export:{start_version}:{end_version}")
        return b"PKzip"

    def create_draft_project(self, spec: NewDraftProject) -> dict:
        self.calls.append(f"create:{spec.name}")
        return {"id": "draft-1", "name": spec.name}

    def import_commits(self, project_id: str, zip_bytes: bytes) -> dict:
        self.calls.append(f"import:{project_id}:{len(zip_bytes)}")
        return {"imported": True}

    def commit_and_publish(self, project_id: str) -> dict:
        self.calls.append(f"publish:{project_id}")
        return {"published": True}


def _profile(base_url: str) -> EnvironmentProfile:
    return EnvironmentProfile(
        base_url=base_url,
        api_key="key",
        username="user",
        password="pass",
    )


class WorkflowTests(unittest.TestCase):
    def test_preview_does_not_export_or_mutate_target(self) -> None:
        source = FakeClient(_profile("https://source.api.visier.io"))
        target = FakeClient(_profile("https://target.api.visier.io"))

        result = run_sdlc_promotion(
            source,
            target,
            PromotionRequest(
                new_project=NewDraftProject(name="preview"),
                auto_draft_naming=None,
            ),
        )

        self.assertEqual(result.export_start_version_id, "newest")
        self.assertEqual(result.export_end_version_id, "newest")
        self.assertEqual(result.planned_project.name, "preview")
        self.assertIsNone(result.new_project)
        self.assertIsNone(result.import_result)
        self.assertIsNone(result.publish_result)
        self.assertEqual(source.calls, ["authenticate", "get_production_versions:400:0"])
        self.assertEqual(target.calls, [])

    def test_apply_imports_but_does_not_publish(self) -> None:
        source = FakeClient(_profile("https://source.api.visier.io"))
        target = FakeClient(_profile("https://target.api.visier.io"))

        result = run_sdlc_promotion(
            source,
            target,
            PromotionRequest(
                new_project=NewDraftProject(name="apply"),
                apply_to_target=True,
            ),
        )

        self.assertEqual(result.new_project, {"id": "draft-1", "name": "apply"})
        self.assertEqual(result.import_result, {"imported": True})
        self.assertIsNone(result.publish_result)
        self.assertIn("export:newest:newest", source.calls)
        self.assertEqual(target.calls, ["authenticate", "create:apply", "import:draft-1:5"])

    def test_publish_requires_apply_and_runs_step_five_when_enabled(self) -> None:
        source = FakeClient(_profile("https://source.api.visier.io"))
        target = FakeClient(_profile("https://target.api.visier.io"))

        with self.assertRaisesRegex(Exception, "publish=True requires apply_to_target=True"):
            run_sdlc_promotion(
                source,
                target,
                PromotionRequest(new_project=NewDraftProject(name="bad"), publish=True),
            )

        result = run_sdlc_promotion(
            source,
            target,
            PromotionRequest(
                new_project=NewDraftProject(name="publish"),
                apply_to_target=True,
                publish=True,
            ),
        )

        self.assertEqual(result.publish_result, {"published": True})
        self.assertIn("publish:draft-1", target.calls)

    def test_pick_export_version_ids_full_history_uses_oldest_to_newest(self) -> None:
        history = {
            "publishedVersions": [
                {"id": "newest"},
                {"id": "middle"},
                {"id": "oldest"},
            ]
        }
        request = PromotionRequest(
            new_project=NewDraftProject(name="x"),
            export_full_published_history=True,
        )

        self.assertEqual(pick_export_version_ids(history, request), ("oldest", "newest"))

    def test_auto_draft_name_is_limited(self) -> None:
        name, description = build_auto_draft_name_and_description(
            "latest",
            _profile("https://source-vanity.api.visier.io"),
            {"publishedVersions": [{"id": "v1", "name": "A" * 100}]},
            "v1",
        )

        self.assertLessEqual(len(name), 50)
        self.assertLessEqual(len(description), 150)


if __name__ == "__main__":
    unittest.main()

"""Regression coverage for ClawHub publication."""

from __future__ import annotations

from pathlib import Path
import unittest

from scripts.product_discovery import _load_workflow_yaml


ROOT = Path(__file__).resolve().parent.parent


def workflow(relative: str) -> dict:
    path = ROOT / relative
    return _load_workflow_yaml(path.read_text(encoding="utf-8"), relative)


class SkillPublicationWorkflowTests(unittest.TestCase):
    def test_clawhub_pin_has_an_explicit_supported_node_runtime(self) -> None:
        document = workflow(".github/workflows/clawhub.yml")
        self.assertEqual("clawhub@0.24.1", document["env"]["CLAWHUB_CLI_PACKAGE"])
        steps = document["jobs"]["sync-skills"]["steps"]
        node = next(step for step in steps if step.get("uses", "").startswith("actions/setup-node@"))
        self.assertEqual("24", node["with"]["node-version"])
        self.assertLess(steps.index(node), next(i for i, step in enumerate(steps)
                                             if step.get("name") == "Login to ClawHub"))

    def test_main_publish_wrapper_is_exact_head_and_publish_enabled(self) -> None:
        document = workflow(".github/workflows/publish-clawhub.yml")
        self.assertEqual({"main"}, set(document["on"]["push"]["branches"]))
        self.assertNotIn("pull_request", document["on"])
        publish = document["jobs"]["publish"]
        self.assertEqual("./.github/workflows/clawhub.yml", publish["uses"])
        self.assertEqual("${{ github.sha }}", publish["with"]["checkout-ref"])
        self.assertIs(True, publish["with"]["publish"])
        self.assertEqual("inherit", publish["secrets"])

    def test_reusable_workflow_honors_explicit_publish_input(self) -> None:
        document = workflow(".github/workflows/clawhub.yml")
        steps = document["jobs"]["sync-skills"]["steps"]
        by_name = {step.get("name"): step for step in steps if step.get("name")}
        self.assertEqual("inputs.publish", by_name["Require ClawHub token"]["if"])
        self.assertEqual("inputs.publish", by_name["Login to ClawHub"]["if"])
        self.assertEqual("${{ !inputs.publish }}", by_name["Dry-run ClawHub publish"]["if"])
        self.assertEqual("inputs.publish", by_name["Publish Skills to ClawHub"]["if"])

        commands = [step.get("run", "") for step in steps]
        self.assertLess(
            commands.index("python -m unittest discover -s tests -q"),
            commands.index("python scripts/clawhub_sync.py"),
        )

if __name__ == "__main__":
    unittest.main()

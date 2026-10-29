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

    def test_main_publish_wrapper_requires_explicit_manual_opt_in(self) -> None:
        document = workflow(".github/workflows/publish-clawhub.yml")
        self.assertEqual({"main"}, set(document["on"]["push"]["branches"]))
        self.assertNotIn("pull_request", document["on"])
        publish = document["jobs"]["publish"]
        self.assertEqual("./.github/workflows/clawhub.yml", publish["uses"])
        self.assertEqual("${{ github.sha }}", publish["with"]["checkout-ref"])
        self.assertIs(True, publish["with"]["publish"])
        self.assertEqual("inherit", publish["secrets"])
        self.assertEqual(
            "${{ github.event_name == 'workflow_dispatch' && inputs.publish == true }}",
            publish["if"],
        )
        switch = document["on"]["workflow_dispatch"]["inputs"]["publish"]
        self.assertEqual("boolean", switch["type"])
        self.assertIs(False, switch["default"])
        self.assertIs(False, switch["required"])

    def test_manual_publication_defaults_off_on_all_entry_points(self) -> None:
        document = workflow(".github/workflows/clawhub.yml")
        for trigger in ("workflow_call", "workflow_dispatch"):
            switch = document["on"][trigger]["inputs"]["publish"]
            self.assertEqual("boolean", switch["type"])
            self.assertIs(False, switch["default"])
        wrapper = workflow(".github/workflows/publish-clawhub.yml")
        condition = wrapper["jobs"]["publish"]["if"]
        # Evaluate the constrained expression after the exact-shape assertion
        # above, covering malicious/stale true input on a push as well.
        expression = condition.removeprefix("${{ ").removesuffix(" }}")
        expression = expression.replace("github.event_name", "event").replace("inputs.publish", "publish")
        expression = expression.replace("&&", "and").replace("true", "True")
        for event, publish, expected in (
            ("push", False, False), ("push", True, False),
            ("workflow_dispatch", False, False), ("workflow_dispatch", True, True),
            ("pull_request", True, False),
        ):
            with self.subTest(event=event, publish=publish):
                self.assertIs(expected, eval(expression, {"__builtins__": {}}, {"event": event, "publish": publish}))

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

"""Regression coverage for the zero-instance discovery decision flow."""

from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "plugins/dcc-mcp/skills/dcc-mcp/SKILL.md"
GUIDE = ROOT / "plugins/dcc-mcp/skills/dcc-mcp/references/ZERO_INSTANCES_CLI.md"
SCHEMA = ROOT / "tests/fixtures/dcc-discovery-decision-v1.schema.json"
SCHEMA_SHA256 = "e6b82bf8bfd14df585d4606d9ae26ab78b6455ad2c93486195a1d80a3889be9e"

DECISION_GATES = (
    "public_adapter",
    "released_catalog",
    "package_installation",
    "adapter_import",
    "project_bootstrap",
    "registry_registration",
    "direct_readiness",
    "gateway_capability_index",
    "search_hit",
    "exact_instance_call",
    "real_host_effect",
    "uncertainties",
    "failure_stage",
    "failure_reason",
    "next_action",
)

EXPECTED_ENUMS = {
    "released_catalog": {"present", "absent", "stale", "unknown"},
    "package_installation": {"absent", "planned", "installed", "unknown"},
    "adapter_import": {"pass", "fail", "unknown"},
    "project_bootstrap": {
        "not_detected",
        "bootstrappable",
        "configured",
        "failed",
        "unknown",
    },
    "registry_registration": {"present", "absent", "stale", "unknown"},
    "direct_readiness": {"ready", "not_ready", "unknown"},
    "exact_instance_call": {"pass", "fail", "not_run", "unknown"},
    "real_host_effect": {"verified", "not_verified", "not_applicable", "unknown"},
}


def markdown_section(text: str, heading: str, next_heading: str) -> str:
    start = text.index(heading) + len(heading)
    end = text.index(next_heading, start)
    return text[start:end]


class ZeroInstanceGuidanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.skill = SKILL.read_text(encoding="utf-8")
        cls.guide = GUIDE.read_text(encoding="utf-8")
        cls.schema_text = SCHEMA.read_text(encoding="utf-8")
        cls.schema = json.loads(cls.schema_text)

    def test_skill_routes_local_and_remote_zero_inventory_separately(self) -> None:
        self.assertIn("Only local zero inventory", self.skill)
        self.assertIn("remote zero inventory uses exact catalog matching", self.skill)
        self.assertIn("references/ZERO_INSTANCES_CLI.md", self.skill)
        self.assertIn("live_instances: 0", self.skill)

    def test_remote_branch_never_runs_the_targeted_local_decision(self) -> None:
        remote = markdown_section(
            self.guide,
            "### Remote zero-instance branch",
            "### Local zero-instance branch",
        )
        catalog = "dcc-mcp-cli --output json dcc-types"
        targeted = "dcc-mcp-cli --output json dcc-types --dcc-type <dcc>"
        plan = "dcc-mcp-cli --output json --non-interactive install --dcc-type <dcc>"

        self.assertIn(catalog, remote)
        self.assertNotIn(targeted, remote)
        self.assertIn("Do not run the targeted local", remote)
        self.assertIn("Only after an\nexact match", remote)
        self.assertLess(remote.index(catalog), remote.index("exact match"))
        self.assertLess(remote.index("exact match"), remote.index(plan))

    def test_local_branch_owns_targeted_decision_and_next_action(self) -> None:
        local = markdown_section(
            self.guide,
            "### Local zero-instance branch",
            "## Legacy CLI fallback",
        )
        targeted = "dcc-mcp-cli --output json dcc-types --dcc-type <dcc>"

        self.assertIn(targeted, local)
        self.assertIn("Only in this local branch", local)
        self.assertIn("execute its `command` argv exactly", local)
        self.assertIn("reads only the local FileRegistry", local)

    def test_legacy_fallback_exact_matches_before_planning(self) -> None:
        legacy = markdown_section(
            self.guide,
            "## Legacy CLI fallback",
            "## Diagnose local startup state",
        )
        catalog = "dcc-mcp-cli --output json dcc-types"
        plan = "dcc-mcp-cli --output json --non-interactive install --dcc-type <dcc>"

        self.assertIn("rejects `--dcc-type`", legacy)
        self.assertIn("Match only an exact canonical catalog identifier", legacy)
        self.assertLess(legacy.index(catalog), legacy.index("exact canonical"))
        self.assertLess(legacy.index("exact canonical"), legacy.index(plan))
        self.assertIn("do not infer", legacy)

    def test_guide_and_pinned_schema_keep_every_gate_independent(self) -> None:
        self.assertEqual(
            hashlib.sha256(self.schema_text.encode("utf-8")).hexdigest(),
            SCHEMA_SHA256,
        )
        self.assertEqual(self.schema["properties"]["schema_version"]["const"], 1)
        self.assertEqual(
            set(self.schema["required"]),
            {"schema_version", "dcc_type", "live_instances", *DECISION_GATES},
        )
        for gate in DECISION_GATES:
            with self.subTest(gate=gate):
                self.assertIn(f"`{gate}`", self.guide)
        for field, expected in EXPECTED_ENUMS.items():
            with self.subTest(field=field):
                self.assertEqual(set(self.schema["properties"][field]["enum"]), expected)
        self.assertEqual(
            set(self.schema["$defs"]["presence"]["enum"]),
            {"present", "absent", "unknown"},
        )
        self.assertEqual(
            set(self.schema["properties"]["uncertainties"]["items"]["enum"]),
            {"version", "custom_fork", "real_host"},
        )

    def test_game_engine_boundaries_remain_explicit(self) -> None:
        for phrase in (
            "engine-bundled Python path",
            "legacy Remote Execution",
            "Unity and supported Tuanjie builds",
            "a `t` version string is not an unsupported verdict",
            "project-local EditorPlugin plus an external sidecar",
        ):
            with self.subTest(phrase=phrase):
                self.assertIn(phrase, self.guide)

    def test_read_only_decision_and_plan_precede_mutation_consent(self) -> None:
        consent = self.guide.index("## Mutation consent")
        execute = self.guide.index("--execute")
        self.assertLess(consent, execute)
        self.assertIn("`requires_consent: false`", self.guide[:consent])

    def test_zero_inventory_asks_before_host_install_and_separates_adapter_install(self) -> None:
        self.assertIn("是否需要我提供或执行官方安装方式", self.guide)
        self.assertIn("host_install", self.guide)
        self.assertIn("Keep this separate", self.guide)
        self.assertIn("explicit consent", self.guide)


if __name__ == "__main__":
    unittest.main()

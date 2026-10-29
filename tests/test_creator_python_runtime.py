"""Protect runtime ownership decisions without installing or importing a payload."""

import ast
from pathlib import Path
import runpy
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from scripts.build_npm_package import copy_skill
from scripts.package_openclaw_skill import package_skill


SKILL = Path(__file__).resolve().parents[1] / "plugins/dcc-mcp/skills/dcc-mcp-creator"
EXAMPLE = SKILL / "references/examples/python_runtime_selection.py"
GUIDE = SKILL / "references/PYTHON_RUNTIME_SELECTION.md"


class CreatorPythonRuntimeTests(unittest.TestCase):
    def test_decision_branches_have_no_install_or_download_side_effects(self):
        """Keep missing, incompatible, offline and refused runtimes out of execution."""
        cases = [
            ((True, False, "compatible", "missing"), "embedded_python", "use_verified_host_interpreter"),
            ((True, False, "absent", "verified"), "shared_runtime", "require_adapter_handshake"),
            ((False, True, "absent", "missing"), "native_bridge", "use_official_bridge"),
            ((False, False, "absent", "missing"), "blocked", "verify_native_bridge"),
            ((True, False, "unknown", "verified"), "blocked", "verify_supported_host_python"),
            ((True, False, "incompatible", "verified"), "blocked", "verify_supported_host_python"),
        ]
        for state in ("missing", "unknown"):
            cases.append(((True, False, "absent", state), "preflight", "plan_and_obtain_install_authorization"))
        for state in (
            "manifest_mismatch", "version_mismatch", "abi_mismatch", "offline", "denied",
            "handshake_only", "payload_unverified", "launch_unavailable",
            "isolation_unverified", "probe_unverified",
        ):
            cases.append(((True, False, "absent", state), "blocked", "resolve_" + state))
        with patch("subprocess.run", side_effect=AssertionError("unexpected execution")), \
                patch("subprocess.Popen", side_effect=AssertionError("unexpected spawn")), \
                patch("urllib.request.urlopen", side_effect=AssertionError("unexpected download")):
            choose = runpy.run_path(str(EXAMPLE))["select_python_owner"]
            for facts, route, step in cases:
                with self.subTest(facts=facts):
                    self.assertEqual({"route": route, "next_step": step}, choose(*facts))
            for facts in (("yes", False, "absent", "verified"), (True, False, "maybe", "verified"), (True, False, "absent", "installed")):
                with self.subTest(invalid=facts), self.assertRaises(ValueError):
                    choose(*facts)

    def test_guidance_reuses_public_contracts_and_preserves_old_host_boundaries(self):
        """Keep trust, install ownership and embedded py37 limits in the public route."""
        guide = " ".join(GUIDE.read_text(encoding="utf-8").split())
        for rule in (
            "Rust `dcc-mcp-sidecar`", "Gateway", "Python 3.7", "Python >=3.9",
            "require_adapter(adapter_id)", "DCC_MCP_RUNTIME_ROOT", "load_manifest",
            "operator's signature/trust policy", "no documented `install` or `upgrade` CLI verb",
            "plan_install", "previous side-by-side version", "issues/2252",
            "Do not raise its minimum version", "not real-host acceptance",
        ):
            with self.subTest(rule=rule):
                self.assertIn(rule, guide)
        for path in (SKILL / "SKILL.md", SKILL / "references/ADAPTER_WORKFLOW.md"):
            self.assertIn("PYTHON_RUNTIME_SELECTION.md", path.read_text(encoding="utf-8"))
        ast.parse(EXAMPLE.read_text(encoding="utf-8"), feature_version=(3, 7))

    def test_figma_preflight_maps_to_planning_and_never_promotes_handshake_to_readiness(self):
        """Apply Figma's documented blocked outcomes without importing its private adapter."""
        choose = runpy.run_path(str(EXAMPLE))["select_python_owner"]
        cases = (
            ("runtime_package_unavailable", "missing", "preflight"),
            ("runtime_handshake_accepted_launch_blocked", "handshake_only", "blocked"),
        )
        for reason, state, route in cases:
            with self.subTest(reason=reason):
                result = choose(True, False, "absent", state)
                self.assertEqual(route, result["route"])
                self.assertNotIn("ready_for_launch", result)
                self.assertNotIn("success", result)
        guide = " ".join(GUIDE.read_text(encoding="utf-8").split())
        for requirement in (
            "exit **2**", "runtime_package_unavailable", "runtime_handshake_accepted_launch_blocked",
            "trusted_runtime_payload_contract_missing", "adapter_launch_contract_missing",
            "dependency_isolation_unverified", "actual selected interpreter",
            "do not widen Figma's actual requirement", "not new Runtime API names",
            "No Figma preflight or host operation was rerun",
        ):
            with self.subTest(requirement=requirement):
                self.assertIn(requirement, guide)

    def test_example_and_source_guidance_are_preserved_in_distribution(self):
        """Ship the same tested offline example and guidance through ZIP and npm."""
        with TemporaryDirectory() as temporary:
            output = Path(temporary)
            archive = package_skill(SKILL, output, "0.0.1")
            copy_skill(SKILL, output / "npm/dcc-mcp-creator")
            with ZipFile(archive) as zipped:
                for path in (EXAMPLE, GUIDE):
                    relative = path.relative_to(SKILL)
                    self.assertEqual(path.read_bytes(), zipped.read("dcc-mcp-creator/" + relative.as_posix()))
                    self.assertEqual(path.read_bytes(), (output / "npm/dcc-mcp-creator" / relative).read_bytes())

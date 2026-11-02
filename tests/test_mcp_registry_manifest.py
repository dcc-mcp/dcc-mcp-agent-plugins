"""Fail-stop contract tests for the centralized MCP Registry manifest.

These are NEGATIVE-first tests: every check must reject a bad input, not just
accept the good one. All validation is offline and read-only; tests mutate
in-memory copies only.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MCP = ROOT / "mcp_registry"

_spec = importlib.util.spec_from_file_location(
    "validate_mcp_manifest", ROOT / "scripts" / "validate_mcp_manifest.py"
)
vm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(vm)  # type: ignore[union-attr]


def _load(rel: str):
    return json.loads((ROOT / rel).read_text(encoding="utf-8"))


class ContractFixture(unittest.TestCase):
    def setUp(self):
        self.contract = _load("mcp_registry/publish-contract.json")
        self.manifest = _load("mcp_registry/server.json")
        self.schema = _load("mcp_registry/schema/2025-12-11.server.schema.json")
        self.baseline = _load("mcp_registry/core-baseline.server.json")
        self.manifest_bytes = (MCP / "server.json").read_bytes()
        self.schema_bytes = (ROOT / self.contract["official_schema"]["vendored_path"]).read_bytes()
        self.baseline_bytes = (ROOT / self.contract["baseline"]["path"]).read_bytes()
        self.suite_version = str(_load("plugins/dcc-mcp/plugin.json")["version"])

    def run_all(self, manifest=None, contract=None, active=None):
        return vm.run_all_checks(
            contract or self.contract,
            manifest if manifest is not None else self.manifest,
            self.schema,
            self.manifest_bytes if manifest is None else json.dumps(manifest, indent=2).encode(),
            self.schema_bytes,
            self.baseline_bytes,
            self.suite_version,
            active,
        )


class TestHappyPath(ContractFixture):
    def test_good_manifest_passes_all_checks(self):
        self.assertEqual(self.run_all(), [])

    def test_official_schema_accepts_good_manifest(self):
        self.assertEqual(vm.check_official_schema(self.manifest, self.schema), [])


class TestOfficialSchemaNegative(ContractFixture):
    def test_missing_required_version_is_rejected(self):
        bad = copy.deepcopy(self.manifest)
        del bad["version"]
        self.assertTrue(any("version" in e for e in vm.check_official_schema(bad, self.schema)))

    def test_bad_name_pattern_is_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["name"] = "no/slash/twice/again"
        self.assertTrue(vm.check_official_schema(bad, self.schema))

    def test_overlong_description_is_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["description"] = "x" * 101  # maxLength 100
        self.assertTrue(any("maxLength" in e for e in vm.check_official_schema(bad, self.schema)))

    def test_transport_missing_url_is_rejected(self):
        bad = copy.deepcopy(self.manifest)
        del bad["packages"][0]["transport"]["url"]
        self.assertTrue(vm.check_official_schema(bad, self.schema))


class TestActivationStateNegative(ContractFixture):
    """The proposal must stay an honest UNACTIVATED draft (reviewer finding #1)."""

    def test_clean_unactivated_contract_passes(self):
        self.assertEqual(vm.check_activation_state(self.contract), [])

    def test_phase_1_activated_flag_is_rejected(self):
        bad = copy.deepcopy(self.contract)
        bad["activation"]["phase_1_is_activated"] = True
        self.assertTrue(any("phase_1_is_activated" in e for e in vm.check_activation_state(bad)))

    def test_live_consumer_wired_flag_is_rejected(self):
        bad = copy.deepcopy(self.contract)
        bad["activation"]["live_consumer_or_publisher_wired"] = True
        self.assertTrue(any("live_consumer_or_publisher_wired" in e for e in vm.check_activation_state(bad)))

    def test_enforceable_gate_flag_is_rejected(self):
        bad = copy.deepcopy(self.contract)
        bad["activation"]["enforceable_publish_gate"] = True
        self.assertTrue(any("enforceable_publish_gate" in e for e in vm.check_activation_state(bad)))

    def test_non_draft_status_is_rejected(self):
        bad = copy.deepcopy(self.contract)
        bad["status"] = "active"
        self.assertTrue(any("status" in e for e in vm.check_activation_state(bad)))

    def test_reintroduced_source_ref_pin_is_rejected(self):
        bad = copy.deepcopy(self.contract)
        bad["manifest"]["source_ref"] = "1c24132488612eb4fba8d78bf3183ac73a71e829"
        self.assertTrue(any("source_ref" in e for e in vm.check_activation_state(bad)))


class TestVersionAuthoringSourceNegative(ContractFixture):
    """PyPI version must come from the contract, not a hardcoded literal (reviewer finding #3)."""

    def test_pypi_value_is_read_from_contract(self):
        self.assertEqual(
            vm.pypi_authoring_version(self.contract),
            self.contract["version_domains"]["pypi_package"]["value_at_authoring"],
        )

    def test_pypi_value_tracks_contract_change(self):
        bad = copy.deepcopy(self.contract)
        bad["version_domains"]["pypi_package"]["value_at_authoring"] = "9.9.9"
        self.assertEqual(vm.pypi_authoring_version(bad), "9.9.9")

    def test_missing_pypi_authoring_value_raises(self):
        bad = copy.deepcopy(self.contract)
        del bad["version_domains"]["pypi_package"]["value_at_authoring"]
        with self.assertRaises(KeyError):
            vm.pypi_authoring_version(bad)

    def test_manifest_version_drift_from_contract_is_rejected(self):
        # Static self-consistency: a manifest whose version drifts from the
        # recorded authoring value is rejected (offline, not a live lookup).
        bad = copy.deepcopy(self.contract)
        bad["version_domains"]["registry_metadata"]["value_in_source_manifest"] = "9.9.9"
        errs = vm.check_version_domains(self.manifest, bad, self.suite_version)
        self.assertTrue(any("self-consistency" in e for e in errs))


class TestIntegrityNegative(ContractFixture):
    def test_tampered_manifest_sha_is_rejected(self):
        tampered = copy.deepcopy(self.manifest)
        tampered["title"] = "TAMPERED"
        errs = vm.check_integrity(
            json.dumps(tampered, indent=2).encode(), self.schema_bytes,
            self.baseline_bytes, self.contract,
        )
        self.assertTrue(any("manifest sha256 mismatch" in e for e in errs))

    def test_untampered_bytes_pass(self):
        self.assertEqual(
            vm.check_integrity(self.manifest_bytes, self.schema_bytes, self.baseline_bytes, self.contract),
            [],
        )


class TestBackwardCompatNegative(ContractFixture):
    def test_changed_immutable_name_is_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["name"] = "io.github.dcc-mcp/dcc-mcp-agent-plugins"
        self.assertTrue(any("'name'" in e for e in vm.check_backward_compat(bad, self.contract)))

    def test_changed_transport_url_is_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["packages"][0]["transport"]["url"] = "http://evil.example/mcp"
        self.assertTrue(any("transport.url" in e for e in vm.check_backward_compat(bad, self.contract)))

    def test_changed_package_identifier_is_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["packages"][0]["identifier"] = "something-else"
        self.assertTrue(any("identifier" in e for e in vm.check_backward_compat(bad, self.contract)))

    def test_good_manifest_passes_backward_compat(self):
        self.assertEqual(vm.check_backward_compat(self.manifest, self.contract), [])


class TestRepositorySourceNegative(ContractFixture):
    def test_repository_repointed_to_skills_repo_is_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["repository"]["url"] = "https://github.com/dcc-mcp/dcc-mcp-agent-plugins"
        self.assertTrue(vm.check_repository_source(bad))

    def test_repository_off_core_is_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["repository"]["url"] = "https://github.com/dcc-mcp/some-other-repo"
        self.assertTrue(vm.check_repository_source(bad))

    def test_repository_on_core_passes(self):
        self.assertEqual(vm.check_repository_source(self.manifest), [])


class TestVersionDomainNegative(ContractFixture):
    def test_version_range_is_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["version"] = ">=0.20.0"
        self.assertTrue(any("range" in e for e in vm.check_version_domains(bad, self.contract, self.suite_version)))

    def test_version_package_mismatch_is_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["packages"][0]["version"] = "0.20.52"
        self.assertTrue(any("mismatch" in e for e in vm.check_version_domains(bad, self.contract, self.suite_version)))

    def test_plugin_suite_version_conflation_is_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["version"] = self.suite_version  # 0.19.120 written into registry metadata
        bad["packages"][0]["version"] = self.suite_version
        self.assertTrue(any("conflation" in e for e in vm.check_version_domains(bad, self.contract, self.suite_version)))

    def test_three_domains_may_legitimately_differ(self):
        # 0.20.53 (manifest) != 0.19.120 (suite) is allowed and must NOT flag.
        self.assertEqual(vm.check_version_domains(self.manifest, self.contract, self.suite_version), [])


class TestSinglePublisherNegative(ContractFixture):
    def test_dual_publisher_is_rejected(self):
        self.assertTrue(vm.check_single_publisher(
            self.contract, ["dcc-mcp/dcc-mcp-core", "dcc-mcp/dcc-mcp-agent-plugins"]
        ))

    def test_zero_publishers_is_rejected(self):
        self.assertTrue(vm.check_single_publisher(self.contract, []))

    def test_wrong_sole_publisher_is_rejected(self):
        self.assertTrue(vm.check_single_publisher(
            self.contract, ["dcc-mcp/dcc-mcp-agent-plugins"]
        ))

    def test_single_core_publisher_passes(self):
        self.assertEqual(vm.check_single_publisher(self.contract), [])


class TestEndToEndFailStop(ContractFixture):
    def test_dual_publisher_fails_full_pipeline(self):
        self.assertTrue(self.run_all(active=["dcc-mcp/dcc-mcp-core", "dcc-mcp/dcc-mcp-agent-plugins"]))

    def test_immutable_change_fails_full_pipeline(self):
        bad = copy.deepcopy(self.manifest)
        bad["name"] = "io.github.dcc-mcp/wrong"
        self.assertTrue(self.run_all(manifest=bad))


if __name__ == "__main__":
    unittest.main()

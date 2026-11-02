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
from unittest import mock

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

    def run_all(self, manifest=None, contract=None, active=None, manifest_bytes=None):
        # ``manifest`` (structural checks) and ``manifest_bytes`` (sha256
        # integrity) are independent inputs to run_all_checks. Keep the
        # committed bytes by default when only the in-memory manifest is
        # overridden: re-serializing would inject an unrelated digest mismatch
        # that could MASK a missing backward-compat call in a full-pipeline
        # test. Pass explicit tampered bytes only when a test targets integrity.
        return vm.run_all_checks(
            contract or self.contract,
            manifest if manifest is not None else self.manifest,
            self.schema,
            manifest_bytes if manifest_bytes is not None else self.manifest_bytes,
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
        self.assertTrue(any("'name'" in e for e in vm.check_backward_compat(bad, self.contract, self.baseline)))

    def test_changed_transport_url_is_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["packages"][0]["transport"]["url"] = "http://evil.example/mcp"
        self.assertTrue(any("transport.url" in e for e in vm.check_backward_compat(bad, self.contract, self.baseline)))

    def test_changed_package_identifier_is_rejected(self):
        bad = copy.deepcopy(self.manifest)
        bad["packages"][0]["identifier"] = "something-else"
        self.assertTrue(any("identifier" in e for e in vm.check_backward_compat(bad, self.contract, self.baseline)))

    def test_good_manifest_passes_backward_compat(self):
        self.assertEqual(vm.check_backward_compat(self.manifest, self.contract, self.baseline), [])

    def test_coordinated_manifest_contract_drift_is_rejected(self):
        # Reviewer finding B: the OLD check compared manifest only against the
        # duplicated contract expectation (both editable in the same PR). A
        # coordinated edit that changes BOTH the manifest field and the
        # contract's immutable_fields expectation, while leaving the
        # sha256-anchored Core baseline unchanged, used to slip through. The
        # baseline is the real immutable source of truth, so it must fail-stop.
        drift = "io.github.dcc-mcp/dcc-mcp-agent-plugins"
        bad_manifest = copy.deepcopy(self.manifest)
        bad_manifest["name"] = drift
        bad_contract = copy.deepcopy(self.contract)
        bad_contract["immutable_fields"]["name"] = drift  # launder the expectation
        errors = vm.check_backward_compat(bad_manifest, bad_contract, self.baseline)
        self.assertTrue(any("'name'" in e for e in errors),
                        f"coordinated drift was not rejected: {errors}")

    def test_contract_expectation_diverging_from_baseline_is_rejected(self):
        # Even with an UNCHANGED manifest, an expectation that silently diverged
        # from the Core baseline must be flagged (the expectation is not truth).
        bad_contract = copy.deepcopy(self.contract)
        bad_contract["immutable_fields"]["repository.url"] = "https://github.com/dcc-mcp/dcc-mcp-agent-plugins"
        errors = vm.check_backward_compat(self.manifest, bad_contract, self.baseline)
        self.assertTrue(any("diverges from the Core baseline" in e for e in errors),
                        f"expectation/baseline divergence was not flagged: {errors}")

    def test_unavailable_baseline_fails_closed(self):
        # A missing/unparseable baseline cannot be used to fake a pass.
        errors = vm.check_backward_compat(self.manifest, self.contract, None)
        self.assertTrue(errors)


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


class TestVersionRangeBoundaries(ContractFixture):
    """Version-range guard must match the official schema's INTENT, both ways.

    The vendored schema's version fields have no ``pattern`` keyword; they reject
    ranges only descriptively (examples ``'^1.2.3'``, ``'~1.2.3'``,
    ``'>=1.2.3'``, ``'1.x'``, ``'1.*'``). Our offline static guard must reject
    real range/comparator syntax WITHOUT flagging valid semver prerelease or
    build identifiers that merely contain the letters x/X (reviewer finding A).
    """

    # Range syntax the registry/schema rejects: schema description examples plus
    # the common bare comparators, wildcards, OR-joins and hyphen ranges.
    INVALID_RANGES = (
        "^1.2.3", "~1.2.3", ">=1.2.3", ">1.0.0", "<2", "<=2.0.0",
        "=1.2.3", "~>1.0", "1.x", "1.*", "1.X", "x", "*", "1.x.2",
        "1.2.3 - 2.0.0", "^1 || ^2",
    )
    # Specific versions the registry accepts, incl. semver prerelease/build
    # metadata that happens to contain x/X (must NOT be treated as wildcards).
    # The '.x' / '.X' cases (1.0.0-rc.x, 1.0.0+build.x, 1.0.0+build.X) are the
    # reviewer finding A boundary: a wildcard-looking *label* after '-' / '+'
    # is a valid, specific version, not a range segment.
    VALID_VERSIONS = (
        "1.2.3", "0.20.53", "2.1.0-alpha", "1.0.0-next.1",
        "1.0.0+linux", "1.0.0-beta.1", "1.0.0-rc.1+exp.sha.5114f85",
        "0.0.4", "1.0.0-rc.x", "1.0.0+build.x", "1.0.0+build.X",
        "1.0.0-x", "1.0.0+21AF26D3",
    )

    def _version_errors(self, version):
        bad = copy.deepcopy(self.manifest)
        bad["version"] = version
        bad["packages"][0]["version"] = version  # keep the two domains equal
        return vm.check_version_domains(bad, self.contract, self.suite_version)

    def test_real_ranges_are_rejected(self):
        for v in self.INVALID_RANGES:
            with self.subTest(range=v):
                self.assertTrue(
                    any("range" in e for e in self._version_errors(v)),
                    f"version range {v!r} was not rejected",
                )

    def test_valid_semver_with_x_is_accepted(self):
        for v in self.VALID_VERSIONS:
            with self.subTest(version=v):
                self.assertFalse(
                    any("range" in e for e in self._version_errors(v)),
                    f"valid version {v!r} was wrongly flagged as a range",
                )

    def test_range_regex_is_segment_aware(self):
        # Direct unit of the static guard: a bare x/X inside a prerelease or
        # build identifier is not a wildcard SEGMENT, but 1.x / 1.* are.
        for v in ("~1.2.3", ">1.0.0", "<2", "1.x", "1.*"):
            with self.subTest(reject=v):
                self.assertIsNotNone(vm.VERSION_RANGE_RE.search(v))
        # reviewer finding A: x/X inside prerelease/build labels is specific,
        # not a wildcard segment. '.x'/'X' at a segment boundary was the bug.
        for v in ("1.0.0-next.1", "1.0.0+linux", "1.0.0-rc.x",
                  "1.0.0+build.x", "1.0.0+build.X"):
            with self.subTest(accept=v):
                self.assertIsNone(vm.VERSION_RANGE_RE.search(v))


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
        errors = self.run_all(active=["dcc-mcp/dcc-mcp-core", "dcc-mcp/dcc-mcp-agent-plugins"])
        self.assertTrue(any("publisher" in e for e in errors))

    def test_immutable_change_fails_full_pipeline(self):
        bad = copy.deepcopy(self.manifest)
        bad["name"] = "io.github.dcc-mcp/wrong"
        errors = self.run_all(manifest=bad)
        # PRECISE error, not just "any errors": a digest mismatch (or any
        # unrelated failure) must not be able to satisfy this assertion.
        self.assertTrue(any("immutable field 'name' changed" in e for e in errors))
        # NO digest noise: the pipeline must fail ONLY on the immutable-name
        # regression, proving the backward-compat check actually ran rather
        # than the test passing on an unrelated sha256 mismatch.
        self.assertFalse(any("sha256 mismatch" in e for e in errors))

    def test_digest_only_change_does_not_fake_immutable_error(self):
        # NEGATIVE CONTROL #1: a change that ONLY causes a sha256 mismatch (a
        # non-immutable brand field, re-serialized bytes) yields errors but must
        # NOT yield the precise immutable-name error. This is exactly the case
        # that made the OLD assertTrue(any(errors)) vacuous.
        bad = copy.deepcopy(self.manifest)
        bad["title"] = "DCC-MCP (tampered)"
        # Tampered BYTES only (a non-immutable brand field), structural manifest
        # otherwise intact -> integrity fails, backward-compat does not.
        errors = self.run_all(
            manifest=bad,
            manifest_bytes=json.dumps(bad, indent=2).encode(),
        )
        self.assertTrue(any("sha256 mismatch" in e for e in errors))
        self.assertFalse(any("immutable field 'name' changed" in e for e in errors))

    def test_immutable_error_requires_backward_compat_check(self):
        # NEGATIVE CONTROL #2: neutralize check_backward_compat to simulate it
        # being REMOVED from run_all_checks. The precise immutable-name error
        # must disappear -> the main assertion genuinely depends on the check
        # being wired into the pipeline (i.e., cannot falsely pass).
        bad = copy.deepcopy(self.manifest)
        bad["name"] = "io.github.dcc-mcp/wrong"
        self.assertTrue(any("immutable field 'name' changed" in e for e in self.run_all(manifest=bad)))
        with mock.patch.object(vm, "check_backward_compat", return_value=[]):
            self.assertFalse(any("immutable field 'name' changed" in e for e in self.run_all(manifest=bad)))


if __name__ == "__main__":
    unittest.main()

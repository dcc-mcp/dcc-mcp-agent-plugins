"""Behavioral first-run contract: compose evidence without inventing readiness."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "plugins/dcc-mcp/skills/dcc-mcp/scripts"
sys.path.insert(0, str(SCRIPTS))
SPEC = importlib.util.spec_from_file_location(
    "first_run_report", SCRIPTS / "first_run_report.py"
)
REPORT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(REPORT)


def decision(**changes):
    return {
        "schema_version": 1,
        "dcc_type": "blender",
        "live_instances": 0,
        "package_installation": "unknown",
        "registry_registration": "absent",
        "direct_readiness": "unknown",
        **changes,
    }


def manifest(**changes):
    return {
        "version": "1",
        "hosts": [
            {
                "id": "blender",
                "license": "open_source",
                "self_provision": True,
                "pinned_version": "5.1.1",
                "install_channels": ["linux"],
                **changes,
            }
        ],
    }


def update(**source_changes):
    return {
        "schema_version": "dcc-mcp.update-inspection.v1",
        "component": "dcc-mcp-cli",
        "read_only": True,
        "dry_run": True,
        "channel": "stable",
        "versions": {
            "installed": {
                "version": "0.20.25",
                "source": "package_manager_record",
                "reason": None,
            },
            "runtime": {
                "version": "0.20.44",
                "source": "executing_cli_build",
                "reason": None,
            },
            "bundled_core": {
                "version": "0.20.44",
                "source": "cli_workspace_build",
                "reason": None,
            },
        },
        "latest_version": "0.20.45",
        "version_status": "update_available",
        "source": {
            "provider": "official_github_release",
            "url": REPORT.RELEASE_API,
            "checked_at_unix_secs": 100,
            "cache_age_secs": 0,
            "ttl_secs": 86400,
            "offline": False,
            "reason": None,
            "refresh_error": None,
            **source_changes,
        },
    }


class FirstRunReportTests(unittest.TestCase):
    def setUp(self):
        self.products = {"products": [{"id": "blender"}], "application_routes": []}
        for target, value in (
            ("shutil.which", None),
            ("platform.system", "Linux"),
            ("time.time", 100),
            ("platform.machine", "x86_64"),
            ("app_path_cache.get_path", None),
        ):
            mock = patch(f"first_run_report.{target}", return_value=value)
            # Register the dynamically loaded module so mocks address exactly it.
            sys.modules["first_run_report"] = REPORT
            mock.start()
            self.addCleanup(mock.stop)

    def report(self, **kwargs):
        return REPORT.build_report(products=self.products, **kwargs)

    def test_missing_cli_does_not_install_launch_probe_or_query(self):
        with patch(
            "subprocess.run", side_effect=AssertionError("unexpected execution")
        ):
            result = self.report()
        self.assertEqual("missing", result["cli"]["availability"])
        self.assertIsNone(result["cli"]["runtime_version"])
        self.assertEqual([], result["automatic_actions"])
        self.assertEqual("unknown", result["applications"][0]["category"])

    def test_found_cli_is_not_a_verified_version_or_healthy_runtime(self):
        REPORT.shutil.which.return_value = "/private/home/bin/dcc-mcp-cli"
        result = self.report()
        self.assertEqual("found", result["cli"]["availability"])
        self.assertEqual("unknown", result["cli"]["version_status"])
        self.assertEqual("unknown", result["applications"][0]["healthy"])
        self.assertNotIn("/private/home", json.dumps(result))

    def test_disconnected_registry_keeps_unknown_instead_of_zero_success(self):
        result = self.report(
            decisions=[decision(live_instances=None, registry_registration="unknown")]
        )
        row = result["applications"][0]
        self.assertEqual("unknown", row["registered"])
        self.assertEqual("unknown", row["adapter_installed"])
        self.assertEqual("unknown", row["category"])

    def test_zero_registration_is_not_missing_installation(self):
        row = self.report(decisions=[decision()])["applications"][0]
        self.assertEqual("absent", row["registered"])
        self.assertEqual("unknown", row["adapter_installed"])
        self.assertEqual("not_checked", row["callable"])

    def test_ready_instance_is_available_for_discovery_not_a_successful_call(self):
        row = self.report(
            decisions=[
                decision(
                    live_instances=1,
                    registry_registration="present",
                    direct_readiness="ready",
                )
            ]
        )["applications"][0]
        self.assertEqual("available_for_discovery", row["category"])
        self.assertEqual("not_checked", row["callable"])
        self.assertEqual("not_verified", row["real_host_effect"])
        self.assertEqual("unknown", row["adapter_installed"])

    def test_contradictory_or_missing_instance_counts_cannot_claim_ready(self):
        for count in (0, None, "1", True, -1):
            with self.subTest(count=count):
                data = decision(
                    live_instances=count,
                    registry_registration="present",
                    direct_readiness="ready",
                )
                row = self.report(decisions=[data])["applications"][0]
                self.assertEqual("unknown", row["registered"])
                self.assertEqual("unknown", row["healthy"])
                self.assertEqual("unknown", row["category"])
        data.pop("live_instances")
        self.assertEqual(
            "unknown", self.report(decisions=[data])["applications"][0]["category"]
        )

    def test_decision_cannot_attest_package_installation_or_stale_registration(self):
        for state in ("installed", "absent", "planned"):
            row = self.report(
                decisions=[
                    decision(
                        package_installation=state,
                        registry_registration="stale",
                        direct_readiness="ready",
                    )
                ]
            )["applications"][0]
            self.assertEqual("unknown", row["adapter_installed"])
            self.assertEqual("unknown", row["registered"])
            self.assertEqual("unknown", row["healthy"])

    def test_registered_not_ready_needs_configuration(self):
        row = self.report(
            decisions=[
                decision(
                    live_instances=1,
                    registry_registration="present",
                    direct_readiness="not_ready",
                )
            ]
        )["applications"][0]
        self.assertEqual("configuration_needed", row["category"])
        self.assertEqual("not_ready", row["healthy"])

    def test_host_presence_is_not_adapter_registration(self):
        host = {
            "read_only": True,
            "hosts": [
                {
                    "id": "blender",
                    "status": "available",
                    "version": "5.1.1",
                    "executable": "/private/project/blender",
                    "hint": "secret-token",
                    "warning": "private-project",
                }
            ],
        }
        result = self.report(host_report=host)
        row = result["applications"][0]
        self.assertEqual("configuration_needed", row["category"])
        self.assertEqual("5.1.1", row["host_version"])
        self.assertEqual("unknown", row["registered"])
        for secret in ("/private/", "secret-token", "private-project"):
            self.assertNotIn(secret, json.dumps(result))

    def test_cached_path_is_separate_and_never_claims_installed(self):
        REPORT.app_path_cache.get_path.return_value = {
            "path": "/private/a",
            "stale": False,
        }
        row = self.report()["applications"][0]
        self.assertEqual("present", row["cached_path"])
        self.assertEqual("configuration_needed", row["category"])
        self.assertEqual("unknown", row["host_probe"])

    def test_stale_or_unreadable_cache_is_not_software_absence(self):
        for cached in ({"stale": True}, ValueError("/private/cache")):
            with self.subTest(cached=cached):
                if isinstance(cached, Exception):
                    REPORT.app_path_cache.get_path.side_effect = cached
                else:
                    REPORT.app_path_cache.get_path.return_value = cached
                row = self.report()["applications"][0]
                self.assertEqual("unknown", row["host_probe"])
                self.assertEqual("unknown", row["category"])

    def test_official_manifest_offers_platform_pinned_open_source_install(self):
        row = self.report(host_manifest=manifest())["applications"][0]
        self.assertEqual("install_available", row["category"])
        self.assertEqual(
            {"status": "available", "version": "5.1.1", "requires_consent": True},
            row["host_install"],
        )
        self.assertEqual("unknown", row["host_probe"])

    def test_commercial_wrong_platform_unpinned_and_disabled_never_offer_install(self):
        for changes in (
            {"license": "commercial"},
            {"install_channels": ["windows"]},
            {"pinned_version": None},
            {"self_provision": False},
        ):
            with self.subTest(changes=changes):
                row = self.report(host_manifest=manifest(**changes))["applications"][0]
                self.assertEqual("not_established", row["host_install"]["status"])
                self.assertEqual("unknown", row["category"])

    def test_unmatched_host_identity_is_explicit_and_not_fuzzy_joined(self):
        self.products = {"products": [{"id": "substance3d_painter"}]}
        report = self.report(
            host_report={
                "read_only": True,
                "hosts": [
                    {
                        "id": "substance",
                        "display_name": "Adobe Substance 3D Painter",
                        "status": "available",
                    }
                ],
            }
        )
        rows = {row["identity"]["row_id"]: row for row in report["applications"]}
        self.assertIsNone(rows["substance"]["product"])
        self.assertEqual("substance", rows["substance"]["identity"]["host_id"])
        self.assertIsNone(rows["substance"]["identity"]["dcc_type"])
        self.assertEqual("unknown", rows["substance3d_painter"]["host_probe"])

    def test_existing_host_wins_over_install_offer(self):
        row = self.report(
            host_manifest=manifest(),
            host_report={
                "read_only": True,
                "hosts": [
                    {"id": "blender", "status": "version_mismatch", "version": "4.0.2"}
                ],
            },
        )["applications"][0]
        self.assertEqual("configuration_needed", row["category"])
        self.assertEqual("4.0.2", row["host_version"])

    def test_new_verified_cli_report_preserves_installed_and_running_discrepancy(self):
        result = self.report(update_report=update())["cli"]
        self.assertEqual("0.20.25", result["installed_version"])
        self.assertEqual("0.20.44", result["runtime_version"])
        self.assertEqual("update_available", result["version_status"])

    def test_offline_stale_failed_and_incomplete_reports_never_mean_latest(self):
        for changes in (
            {"offline": True},
            {"cache_age_secs": 86400},
            {"refresh_error": "network_unavailable"},
            {"checked_at_unix_secs": None},
            {"ttl_secs": True},
            {"reason": "unverified"},
            {"checked_at_unix_secs": 101},
            {"provider": "gateway_update_cache"},
            {"url": "https://unverified.example/latest"},
        ):
            with self.subTest(changes=changes):
                data = update(**changes)
                data["version_status"] = "up_to_date"
                result = self.report(update_report=data)["cli"]
                self.assertEqual("unknown", result["version_status"])
                self.assertEqual("0.20.44", result["runtime_version"])

    def test_contradictory_update_status_or_unobserved_version_is_unknown(self):
        data = update()
        data["version_status"] = "up_to_date"
        self.assertEqual(
            "unknown", self.report(update_report=data)["cli"]["version_status"]
        )
        for changes in ({"source": "unavailable"}, {"reason": "runtime_not_observed"}):
            data = update()
            data["versions"]["runtime"].update(changes)
            result = self.report(update_report=data)["cli"]
            self.assertIsNone(result["runtime_version"])
            self.assertEqual("unknown", result["version_status"])

    def test_matching_stable_versions_and_prerelease_uncertainty(self):
        for latest, status in (
            ("0.20.44", "up_to_date"),
            ("0.20.43", "ahead_of_channel"),
            ("0.20.45-rc.1", "unknown"),
        ):
            data = update()
            data.update(latest_version=latest, version_status=status)
            self.assertEqual(
                status, self.report(update_report=data)["cli"]["version_status"]
            )

    def test_elapsed_time_invalidates_a_previously_fresh_file(self):
        REPORT.time.time.return_value = 86500
        result = self.report(update_report=update())["cli"]
        self.assertEqual("unknown", result["version_status"])
        self.assertEqual(86400, result["cache_age_secs"])

    def test_remote_scope_cannot_project_local_host_cache_or_install_channels(self):
        REPORT.app_path_cache.get_path.side_effect = AssertionError("read local cache")
        for kwargs in (
            {},
            {"host_manifest": manifest()},
            {"host_report": {"read_only": True, "hosts": []}},
        ):
            with (
                self.subTest(kwargs=kwargs),
                self.assertRaisesRegex(ValueError, "remote"),
            ):
                self.report(runtime_scope="remote", **kwargs)
        REPORT.app_path_cache.get_path.assert_not_called()

    def test_remote_scope_cannot_import_local_registry(self):
        with self.assertRaisesRegex(ValueError, "remote"):
            self.report(runtime_scope="remote", decisions=[decision()])

    def test_malformed_and_duplicate_evidence_fail_closed(self):
        examples = (
            {"decisions": [decision(schema_version=2)]},
            {"decisions": [decision(schema_version=True)]},
            {"decisions": [decision(), decision()]},
            {"decisions": [decision(dcc_type="../../private")]},
            {"host_report": {"hosts": []}},
            {"host_manifest": {"version": "999", "hosts": []}},
            {"host_report": {"read_only": True, "hosts": [{"id": "blender"}] * 2}},
            {"update_report": {"schema_version": "unknown"}},
        )
        for kwargs in examples:
            with (
                self.subTest(kwargs=kwargs),
                self.assertRaises((ValueError, TypeError)),
            ):
                self.report(**kwargs)

    def test_returned_next_action_is_never_executed_or_echoed(self):
        data = decision(
            next_action={
                "command": ["sh", "-c", "secret-command"],
                "requires_consent": False,
            }
        )
        result = self.report(decisions=[data])
        self.assertNotIn("secret-command", json.dumps(result))

    def test_bounded_file_input_and_public_error(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "private-path.json"
            path.write_bytes(b" " * (REPORT.MAX_BYTES + 1))
            with self.assertRaisesRegex(ValueError, "1 MiB"):
                REPORT.read_object(path)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPTS / "first_run_report.py"),
                    "--host-report",
                    str(path),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(2, proc.returncode)
            self.assertEqual(
                "invalid_or_unavailable_evidence", json.loads(proc.stdout)["error"]
            )
            self.assertNotIn(directory, proc.stdout + proc.stderr)

    def test_first_run_guidance_routes_reuse_and_issue_consent(self):
        references = SCRIPTS.parent / "references"
        first = (references / "FIRST_RUN.md").read_text()
        issue = (references / "SOFTWARE_REQUEST.md").read_text()
        self.assertIn("host doctor", first)
        self.assertIn("host install", first)
        self.assertIn("startup can\nactivate", first)
        self.assertIn("not `host`, `list`, or `dcc-types`", first)
        self.assertIn('"requires_user_confirmation": true', issue)
        self.assertIn("not\na Finding v1", issue)
        self.assertIn("exact title and issue/comment body", issue)


if __name__ == "__main__":
    unittest.main()

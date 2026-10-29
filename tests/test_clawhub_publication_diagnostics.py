"""Offline ClawHub 0.24.1 inspect contract; no CLI or registry calls."""

import contextlib
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

from scripts import clawhub_sync as sync


class PublicationDiagnosticTests(unittest.TestCase):
    def payload(self, stage="checks_failed", retrying=True):
        return {
            "skill": {"slug": "example", "displayName": "Example"},
            "owner": None, "version": None, "versions": None, "file": None,
            "publication": {"version": "1.2.3", "stage": stage, "retrying": retrying,
                            "updatedAt": 123, "checks": {"trufflehog": "clean", "clawscan": "failed"}},
            "nextSteps": {"scanReport": "untrusted command not to echo"},
        }

    def inspect(self, payload, code=1, stderr=""):
        proc = subprocess.CompletedProcess([], code, json.dumps(payload), stderr)
        output = io.StringIO()
        with patch.object(sync.subprocess, "run", return_value=proc) as run, \
             patch.object(sync.time, "sleep"), patch.object(sync, "MAX_RETRIES", 1), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = sync.verify_owner_version("clawhub@0.24.1", "example", "owner", "1.2.3",
                                               Path("unused"), 2, "a" * 64)
        return result, output.getvalue(), run

    def test_nonzero_files_json_preserves_checks_and_retry_diagnostic_only(self):
        for code in (0, 1):
            with self.subTest(code=code):
                result, output, run = self.inspect(self.payload(), code)
                self.assertIsNone(result)
                self.assertIn('"stage": "checks_failed"', output)
                self.assertIn('"retrying": true', output)
                self.assertIn("not a malware verdict", output)
                self.assertIn("do not re-upload", output)
                self.assertIn("not owner-file, fingerprint", output)
                self.assertNotIn("untrusted command", output)
                run.assert_called_once()
                self.assertEqual(run.call_args.args[0][-4:], ["--version", "1.2.3", "--files", "--json"])

    def test_mismatched_identity_or_malformed_diagnostic_fails_closed(self):
        for key, value in (("version", "9.9.9"), ("stage", "unknown"),
                           ("stage", []), ("retrying", "true"), ("checks", {"clawscan": []})):
            payload = self.payload()
            payload["publication"][key] = value
            with self.subTest(key=key, value=value):
                self.assertIs(self.inspect(payload)[0], False)
        for updates in ({"skill": {"slug": "wrong"}}, {"owner": {"handle": "wrong"}}):
            payload = self.payload()
            payload.update(updates)
            self.assertIs(self.inspect(payload)[0], False)

    def test_terminal_or_blocked_diagnostics_are_not_accepted_as_pending(self):
        for stage in ("blocked", "failed", "expired", "unavailable", "published"):
            with self.subTest(stage=stage):
                self.assertIs(self.inspect(self.payload(stage))[0], False)
        payload = self.payload("pending_checks")
        payload["publication"]["checks"]["clawscan"] = "blocked"
        self.assertIs(self.inspect(payload)[0], False)

    def test_authentication_failure_and_nonzero_file_payload_never_prove_bytes(self):
        payload = {"error": "HTTP 401 Unauthorized"}
        self.assertIs(self.inspect(payload, stderr="Unauthorized")[0], False)
        payload = {"skill": {"slug": "example"}, "owner": {"handle": "owner"},
                   "version": {"version": "1.2.3", "files": []}}
        self.assertIs(self.inspect(payload)[0], False)
        self.assertIs(self.inspect(self.payload(), code=2)[0], False)

    def test_plain_404_is_unconfirmed_visibility_not_absence_or_upload_permission(self):
        result, output, run = self.inspect({}, stderr="Error: Version not found")
        self.assertIsNone(result)
        self.assertIn("may still be pending", output)
        self.assertNotIn("does not exist", output)
        run.assert_called_once()

    def test_zero_exit_files_still_require_fingerprint_and_local_bytes(self):
        payload = {"skill": {"slug": "example"}, "owner": {"handle": "owner"},
                   "version": {"version": "1.2.3", "files": []}}
        with patch.object(sync, "published_file_mismatches", return_value=["fingerprint mismatch"]) as verify:
            result, output, _ = self.inspect(payload, code=0)
        self.assertIs(result, False)
        verify.assert_called_once()
        self.assertIn("fingerprint mismatch", output)

    def test_diagnostic_cannot_replace_missing_upload_fingerprint(self):
        with patch.object(sync, "verify_resolved_fingerprint", return_value=False), \
             patch.object(sync, "verify_owner_version") as owner:
            result = sync.verify_uploaded_version("cli", "example", "owner", "1.2.3", Path("unused"),
                                                 publish_metadata=(2, "a" * 64))
        self.assertFalse(result)
        owner.assert_not_called()

    def receipt(self, status="pending-publication"):
        # Shape from npm clawhub@0.24.1 dist/cli/commands/publish.js.
        result = {"ok": True, "status": status, "slug": "example", "displayName": "Example",
                  "folder": str(Path("unused").resolve()), "version": "1.2.3", "latestVersion": "1.2.2",
                  "fileCount": 2, "fingerprint": "a" * 64, "versionId": "version-id"}
        if status != "submitted":
            result["publicationStatus"] = "pending" if status == "pending-publication" else "published"
            result["attemptId"] = "attempt-id"
        return result

    def test_mixed_diagnostic_cannot_mask_version_security_or_files(self):
        for key, value in (("version", {"version": "9.9.9"}),
                           ("version", {"version": "1.2.3", "security": {"status": "blocked"}}),
                           ("versions", []), ("file", {}), ("files", [])):
            payload = self.payload()
            payload[key] = value
            with self.subTest(key=key, value=value):
                self.assertIs(self.inspect(payload)[0], False)
        payload = self.payload()
        del payload["version"]
        self.assertIs(self.inspect(payload)[0], False)

    def test_actual_receipts_keep_identity_and_content_validation(self):
        for status in ("pending-publication", "submitted", "published"):
            for key, value in (("version", "9.9.9"), ("fingerprint", "b" * 64),
                               ("slug", "other"), ("fileCount", 3), ("folder", "other"),
                               ("versionId", ""), ("publicationStatus", "unknown")):
                payload = self.receipt(status)
                payload[key] = value
                with self.subTest(status=status, key=key), self.assertRaises(ValueError):
                    sync.validate_publish_receipt(json.dumps(payload), slug="example", version="1.2.3",
                        expected_file_count=2, expected_fingerprint="a" * 64, expected_folder=Path("unused"))

    def test_held_diagnostic_after_actual_receipts_never_reuploads_or_claims_public_files(self):
        proc = subprocess.CompletedProcess([], 1, json.dumps(self.payload()), "")
        for status in ("pending-publication", "submitted", "published"):
            output = io.StringIO()
            with self.subTest(status=status), \
                 patch.object(sync.subprocess, "run", return_value=proc) as run, \
                 patch.object(sync, "verify_published_version") as public, \
                 patch.object(sync.time, "sleep") as sleep, contextlib.redirect_stdout(output):
                result = sync.verify_uploaded_version("cli", "example", "owner", "1.2.3", Path("unused"),
                    json.dumps(self.receipt(status)), publish_metadata=(2, "a" * 64))
            self.assertTrue(result)  # Receipt only, NOT an installable/public result.
            self.assertIn("does not establish", output.getvalue())
            self.assertIn("visibility is pending", output.getvalue())
            public.assert_not_called()
            sleep.assert_not_called()
            run.assert_called_once()
            self.assertIn("inspect", run.call_args.args[0])
            self.assertNotIn("publish", run.call_args.args[0])


if __name__ == "__main__":
    unittest.main()

"""HEAD attestations consume trusted outcomes, not candidate instructions."""

from __future__ import annotations

import unittest
from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request

from scripts.report_publication_status import (
    Event,
    GitHubApiError,
    NoRedirects,
    github_api,
    report,
)


class PublicationStatusTests(unittest.TestCase):
    def setUp(self) -> None:
        self.event = Event("owner/repo", 7, "fork/repo", "a" * 40, "b" * 40, "c" * 40, 12)
        self.live = {
            "number": 7,
            "state": "open",
            "base": {"sha": "a" * 40, "ref": "main", "repo": {"full_name": "owner/repo"}},
            "head": {"sha": "b" * 40, "repo": {"full_name": "fork/repo"}},
        }
        self.posts = []

    def api(self, method, path, payload=None):
        if method == "GET":
            return deepcopy(self.live)
        self.posts.append((path, payload))
        return {"id": len(self.posts), **payload}

    def test_verified_fork_result_is_attached_to_event_head(self) -> None:
        result = report(self.event, "finish", "success", True, True, self.api)
        self.assertEqual(result["state"], "success")
        self.assertEqual(self.posts[0][0], "/repos/owner/repo/statuses/" + "b" * 40)
        self.assertEqual(self.posts[0][1]["context"], "publication-contract")
        self.assertEqual(result["merge_sha"], "c" * 40)

    def test_start_is_pending_not_success(self) -> None:
        outcome = report(self.event, "start", "skipped", False, False, self.api)
        self.assertEqual(outcome["state"], "pending")

    def test_success_requires_all_trusted_validation_outputs(self) -> None:
        for result, enforced, parents, expected in (
            ("failure", False, True, "failure"),
            ("failure", False, False, "failure"),
            ("cancelled", True, True, "error"),
            ("skipped", False, False, "error"),
            ("success", False, True, "error"),
            ("success", True, False, "error"),
        ):
            with self.subTest(result=result, enforced=enforced, parents=parents):
                outcome = report(self.event, "finish", result, enforced, parents, self.api)
                self.assertEqual(outcome["state"], expected)
                self.assertEqual(self.posts[-1][1]["state"], expected)

    def test_head_drift_before_write_never_moves_result_to_new_head(self) -> None:
        self.live["head"]["sha"] = "d" * 40
        outcome = report(self.event, "finish", "success", True, True, self.api)
        self.assertEqual(outcome["state"], "error")
        self.assertEqual(len(self.posts), 1)
        self.assertTrue(self.posts[0][0].endswith(self.event.head_sha))

    def test_same_head_with_new_base_does_not_receive_old_success(self) -> None:
        self.live["base"]["sha"] = "d" * 40
        outcome = report(self.event, "finish", "success", True, True, self.api)
        self.assertEqual(outcome["state"], "error")
        self.assertEqual(self.posts[0][1]["state"], "error")

    def test_after_write_head_or_base_drift_retracts_original_success(self) -> None:
        for side in ("head", "base"):
            with self.subTest(side=side):
                self.setUp()

                def moving_api(method, path, payload=None):
                    result = self.api(method, path, payload)
                    if method == "POST" and payload["state"] == "success":
                        self.live[side]["sha"] = "d" * 40
                    return result

                outcome = report(self.event, "finish", "success", True, True, moving_api)
                self.assertEqual(outcome["state"], "error")
                self.assertEqual(
                    [payload["state"] for _, payload in self.posts], ["success", "error"]
                )
                self.assertTrue(all(path.endswith(self.event.head_sha) for path, _ in self.posts))

    def test_wrong_pr_identity_prevents_any_status_write(self) -> None:
        for mutation in ("number", "base-repository", "head-repository"):
            with self.subTest(mutation=mutation):
                self.setUp()
                if mutation == "number":
                    self.live["number"] = 8
                elif mutation == "base-repository":
                    self.live["base"]["repo"]["full_name"] = "other/repo"
                else:
                    self.live["head"]["repo"]["full_name"] = "other/fork"
                with self.assertRaisesRegex(ValueError, "PR identity"):
                    report(self.event, "finish", "success", True, True, self.api)
                self.assertEqual(self.posts, [])

    def test_closed_pr_only_receives_error(self) -> None:
        self.live["state"] = "closed"
        outcome = report(self.event, "finish", "success", True, True, self.api)
        self.assertEqual(outcome["state"], "error")

    def test_failed_post_write_observation_retracts_positive_status(self) -> None:
        reads = 0

        def unreliable_api(method, path, payload=None):
            nonlocal reads
            if method == "GET":
                reads += 1
                if reads == 2:
                    raise RuntimeError("GitHub API GET failed with HTTP 403")
            return self.api(method, path, payload)

        with self.assertRaisesRegex(RuntimeError, "403"):
            report(self.event, "finish", "success", True, True, unreliable_api)
        self.assertEqual([payload["state"] for _, payload in self.posts], ["success", "error"])
        self.assertEqual(reads, 4)

    def test_api_401_and_403_do_not_try_other_credentials(self) -> None:
        for status in (401, 403):
            with (
                self.subTest(status=status),
                patch(
                    "scripts.report_publication_status.build_opener",
                ) as build,
            ):
                request = build.return_value.open
                request.side_effect = HTTPError(
                    "https://api.github.com", status, "blocked", {}, None
                )
                with self.assertRaisesRegex(RuntimeError, f"HTTP {status}; no credential fallback"):
                    report(
                        self.event, "finish", "success", True, True, github_api("not-a-real-token")
                    )
                self.assertEqual(request.call_count, 1)

    def test_status_write_permission_error_is_not_success(self) -> None:
        def denied_api(method, path, payload=None):
            if method == "POST":
                raise GitHubApiError("GitHub API POST failed with HTTP 403; no credential fallback")
            return self.api(method, path, payload)

        with self.assertRaisesRegex(RuntimeError, "403"):
            report(self.event, "finish", "success", True, True, denied_api)
        self.assertEqual(self.posts, [])

    def test_ambiguous_success_post_is_retracted_on_original_head(self) -> None:
        def ambiguous_api(method, path, payload=None):
            receipt = self.api(method, path, payload)
            if method == "POST" and payload["state"] == "success":
                raise RuntimeError("POST receipt unavailable after acceptance")
            return receipt

        with self.assertRaisesRegex(RuntimeError, "receipt unavailable"):
            report(self.event, "finish", "success", True, True, ambiguous_api)
        self.assertEqual([payload["state"] for _, payload in self.posts], ["success", "error"])
        self.assertTrue(all(path.endswith(self.event.head_sha) for path, _ in self.posts))

    def test_corrective_write_receipt_must_be_verified(self) -> None:
        def wrong_correction(method, path, payload=None):
            receipt = self.api(method, path, payload)
            if method == "POST" and payload["state"] == "success":
                self.live["head"]["sha"] = "d" * 40
            if method == "POST" and payload["state"] == "error":
                receipt["context"] = "not-our-context"
            return receipt

        with self.assertRaisesRegex(ValueError, "status receipt"):
            report(self.event, "finish", "success", True, True, wrong_correction)

    def test_missing_or_invalid_merge_can_clear_head_but_never_succeed(self) -> None:
        for merge in ("", "null", "0" * 40, "stale-ref"):
            with self.subTest(merge=merge):
                event = replace(self.event, merge_sha=merge)
                start = report(event, "start", "skipped", False, False, self.api)
                self.assertEqual(start["state"], "pending")
                self.assertIsNone(start["merge_sha"])
                finish = report(event, "finish", "success", True, True, self.api)
                self.assertEqual(finish["state"], "error")
                self.assertTrue(self.posts[-1][0].endswith(event.head_sha))

    def test_unverified_stale_merge_cannot_override_head_with_success(self) -> None:
        outcome = report(self.event, "finish", "failure", False, False, self.api)
        self.assertEqual(outcome["state"], "failure")
        self.assertTrue(self.posts[-1][0].endswith(self.event.head_sha))

    def test_redirects_never_forward_authorization(self) -> None:
        handler = NoRedirects()
        request = Request(
            "https://api.github.com/repos/owner/repo", headers={"Authorization": "Bearer sentinel"}
        )
        for code in (301, 302, 303, 307, 308):
            for destination in ("https://external.invalid/token", "https://api.github.com/other"):
                with self.subTest(code=code, destination=destination):
                    self.assertIsNone(
                        handler.redirect_request(request, None, code, "redirect", {}, destination)
                    )
        with patch("scripts.report_publication_status.build_opener") as build:
            build.return_value.open.side_effect = HTTPError(
                request.full_url,
                302,
                "redirect",
                {"Location": "https://external.invalid/token"},
                None,
            )
            with self.assertRaisesRegex(GitHubApiError, "HTTP 302"):
                github_api("sentinel")("GET", "/repos/owner/repo")
            self.assertIsInstance(build.call_args.args[0], NoRedirects)
            self.assertEqual(build.return_value.open.call_count, 1)


if __name__ == "__main__":
    unittest.main()

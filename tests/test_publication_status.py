"""HEAD attestations consume trusted outcomes, not candidate instructions."""

from __future__ import annotations

import json
import os
import unittest
from contextlib import redirect_stderr, redirect_stdout
from copy import deepcopy
from dataclasses import replace
from io import StringIO
from unittest.mock import mock_open, patch
from urllib.error import HTTPError
from urllib.request import Request

from scripts.report_publication_status import (
    Event,
    GitHubApiError,
    NoRedirects,
    github_api,
    main,
    report,
    resolve_merge,
    write_merge_output,
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


class PublicationMergeResolutionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.event = Event("owner/repo", 7, "fork/repo", "a" * 40, "b" * 40, "", 12)
        self.live = {
            "number": 7,
            "state": "open",
            "base": {"sha": "a" * 40, "ref": "main", "repo": {"full_name": "owner/repo"}},
            "head": {"sha": "b" * 40, "repo": {"full_name": "fork/repo"}},
            "merge_commit_sha": "c" * 40,
        }
        self.commit = {
            "sha": "c" * 40,
            "parents": [{"sha": "a" * 40}, {"sha": "b" * 40}],
        }
        self.requests = []
        self.waits = []

    def api(self, method, path, payload=None):
        self.assertEqual(method, "GET")
        self.assertIsNone(payload)
        self.requests.append(path)
        if path == self.event.pr_path:
            return deepcopy(self.live)
        self.assertEqual(path, "/repos/owner/repo/git/commits/" + "c" * 40)
        return deepcopy(self.commit)

    def resolve(self, api=None) -> str:
        return resolve_merge(self.event, api or self.api, wait=self.waits.append)

    def test_supplied_valid_event_merge_stays_immutable(self) -> None:
        event = replace(self.event, merge_sha="d" * 40)
        self.assertEqual(resolve_merge(event, self.api, wait=self.waits.append), "d" * 40)
        self.assertEqual(self.requests, [])
        self.assertEqual(self.waits, [])

    def test_omitted_merge_is_resolved_from_exact_fork_event_and_ordered_parents(self) -> None:
        self.assertEqual(self.resolve(), "c" * 40)
        self.assertEqual(
            self.requests,
            [self.event.pr_path, "/repos/owner/repo/git/commits/" + "c" * 40, self.event.pr_path],
        )
        self.assertEqual(self.waits, [])

    def test_pending_merge_is_retried_with_a_bounded_delay(self) -> None:
        reads = 0

        def eventual_api(method, path, payload=None):
            nonlocal reads
            value = self.api(method, path, payload)
            if path == self.event.pr_path:
                reads += 1
                if reads == 1:
                    value["merge_commit_sha"] = None
            return value

        self.assertEqual(self.resolve(eventual_api), "c" * 40)
        self.assertEqual(self.waits, [1])
        self.assertEqual(len(self.requests), 4)

    def test_no_merge_never_uses_head_or_a_moving_ref(self) -> None:
        self.live["merge_commit_sha"] = None
        with self.assertRaisesRegex(ValueError, "after bounded metadata checks"):
            self.resolve()
        self.assertEqual(self.requests, [self.event.pr_path] * 3)
        self.assertEqual(self.waits, [1, 1])

    def test_event_or_api_malformed_merge_is_not_resolved_or_retried(self) -> None:
        for value in ("null", "0" * 40, "main", "refs/pull/7/merge", "--invalid-option"):
            with self.subTest(value=value):
                event = replace(self.event, merge_sha=value)
                with self.assertRaisesRegex(ValueError, "event merge SHA"):
                    resolve_merge(event, self.api, wait=self.waits.append)
                self.assertEqual(self.requests, [])
                self.live["merge_commit_sha"] = value
                with self.assertRaisesRegex(ValueError, "merge metadata"):
                    self.resolve()
                self.assertEqual(self.requests, [self.event.pr_path])
                self.requests.clear()
                self.assertEqual(self.waits, [])

    def test_wrong_identity_or_event_drift_never_fetches_candidate(self) -> None:
        for field in ("base", "head", "number", "target", "head-repository", "closed"):
            with self.subTest(field=field):
                self.setUp()
                if field in {"base", "head"}:
                    self.live[field]["sha"] = "d" * 40
                elif field == "number":
                    self.live["number"] = 8
                elif field == "target":
                    self.live["base"]["ref"] = "other"
                elif field == "head-repository":
                    self.live["head"]["repo"]["full_name"] = "other/fork"
                else:
                    self.live["state"] = "closed"
                with self.assertRaisesRegex(ValueError, "identity|event drift"):
                    self.resolve()
                self.assertEqual(self.requests, [self.event.pr_path])
                self.assertEqual(self.waits, [])

    def test_head_only_wrong_order_and_extra_parents_cannot_pass(self) -> None:
        for parents in (("a" * 40,), ("b" * 40, "a" * 40), ("a" * 40, "b" * 40, "d" * 40)):
            with self.subTest(parents=parents):
                self.setUp()
                self.commit["parents"] = [{"sha": sha} for sha in parents]
                with self.assertRaisesRegex(ValueError, "event base/head parents"):
                    self.resolve()
                self.assertEqual(len(self.requests), 6)
                self.assertEqual(self.waits, [1, 1])

    def test_api_commit_identity_and_shape_are_required(self) -> None:
        for mutation in ("sha", "parents", "parent-entry"):
            with self.subTest(mutation=mutation):
                self.setUp()
                if mutation == "sha":
                    self.commit["sha"] = "d" * 40
                elif mutation == "parents":
                    self.commit["parents"] = None
                else:
                    self.commit["parents"] = ["a" * 40, "b" * 40]
                with self.assertRaisesRegex(ValueError, "not verifiable"):
                    self.resolve()
                self.assertEqual(len(self.requests), 2)
                self.assertEqual(self.waits, [])

    def test_post_read_drift_prevents_sha_output(self) -> None:
        reads = 0

        def drift_api(method, path, payload=None):
            nonlocal reads
            value = self.api(method, path, payload)
            if path == self.event.pr_path:
                reads += 1
                if reads == 2:
                    value["head"]["sha"] = "d" * 40
            return value

        with self.assertRaisesRegex(ValueError, "after merge resolution"):
            self.resolve(drift_api)
        self.assertEqual(len(self.requests), 3)
        self.assertEqual(self.waits, [])

    def test_post_read_changed_merge_is_retried_then_fails_closed(self) -> None:
        reads = 0

        def moving_merge_api(method, path, payload=None):
            nonlocal reads
            value = self.api(method, path, payload)
            if path == self.event.pr_path:
                reads += 1
                if reads % 2 == 0:
                    value["merge_commit_sha"] = None
            return value

        with self.assertRaisesRegex(ValueError, "changed during resolution"):
            self.resolve(moving_merge_api)
        self.assertEqual(len(self.requests), 9)
        self.assertEqual(self.waits, [1, 1])

    def test_auth_or_transport_failure_is_not_retried(self) -> None:
        for status in (401, 403):
            with self.subTest(status=status):
                calls = []

                def denied(method, path, payload=None):
                    calls.append((method, path))
                    raise GitHubApiError(f"GitHub API GET failed with HTTP {status}; no credential fallback")

                with self.assertRaisesRegex(GitHubApiError, str(status)):
                    self.resolve(denied)
                self.assertEqual(calls, [("GET", self.event.pr_path)])
                self.assertEqual(self.waits, [])

    def test_output_is_one_validated_sha_and_not_arbitrary_text(self) -> None:
        output = mock_open()
        with patch("builtins.open", output):
            write_merge_output("c" * 40, "trusted-output")
        output().write.assert_called_once_with("merge-sha=" + "c" * 40 + "\n")
        for value in ("", "0" * 40, "c" * 40 + "\nother=true"):
            with self.subTest(value=value), patch("builtins.open") as rejected:
                with self.assertRaisesRegex(ValueError, "exact commit SHA"):
                    write_merge_output(value, "trusted-output")
                rejected.assert_not_called()

    def cli_arguments(self, phase="start") -> list[str]:
        return [
            "publisher", "--repository", self.event.repository,
            "--pr-number", str(self.event.pr_number), "--head-repository", self.event.head_repository,
            "--base-sha", self.event.base_sha, "--head-sha", self.event.head_sha,
            "--merge-sha=", "--run-id", str(self.event.run_id),
            "--phase", phase, "--resolve-merge",
        ]

    def test_start_cli_publishes_pending_then_emits_resolved_sha(self) -> None:
        posts = []

        def publisher_api(method, path, payload=None):
            if method == "POST":
                posts.append((path, payload))
                return {"id": len(posts), **payload}
            return self.api(method, path, payload)

        output = mock_open()
        stdout = StringIO()
        with (
            patch("sys.argv", self.cli_arguments()),
            patch.dict(os.environ, {"GH_TOKEN": "test-token", "GITHUB_OUTPUT": "trusted-output"}, clear=True),
            patch("scripts.report_publication_status.github_api", return_value=publisher_api),
            patch("builtins.open", output),
            redirect_stdout(stdout),
        ):
            self.assertEqual(main(), 0)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0][0], self.event.status_path)
        self.assertEqual(posts[0][1]["state"], "pending")
        self.assertEqual(json.loads(stdout.getvalue())["merge_sha"], "c" * 40)
        output().write.assert_called_once_with("merge-sha=" + "c" * 40 + "\n")

    def test_start_cli_resolution_denial_cannot_emit_merge_output(self) -> None:
        posts = []
        reads = 0

        def denied_resolution(method, path, payload=None):
            nonlocal reads
            if method == "POST":
                posts.append((path, payload))
                return {"id": len(posts), **payload}
            reads += 1
            if reads == 3:
                raise GitHubApiError("GitHub API GET failed with HTTP 403; no credential fallback")
            return self.api(method, path, payload)

        stderr = StringIO()
        with (
            patch("sys.argv", self.cli_arguments()),
            patch.dict(os.environ, {"GH_TOKEN": "test-token", "GITHUB_OUTPUT": "trusted-output"}, clear=True),
            patch("scripts.report_publication_status.github_api", return_value=denied_resolution),
            patch("builtins.open") as output,
            redirect_stderr(stderr),
        ):
            self.assertEqual(main(), 1)
        output.assert_not_called()
        self.assertEqual(reads, 3)
        self.assertEqual(len(posts), 1)
        self.assertEqual(posts[0][1]["state"], "pending")
        self.assertIn("403", stderr.getvalue())

    def test_finish_cli_cannot_use_merge_resolution_option(self) -> None:
        with (
            patch("sys.argv", self.cli_arguments("finish")),
            patch.dict(os.environ, {}, clear=True),
            patch("scripts.report_publication_status.github_api") as api,
            patch("builtins.open") as output,
            redirect_stderr(StringIO()),
        ):
            self.assertEqual(main(), 1)
        api.assert_not_called()
        output.assert_not_called()


if __name__ == "__main__":
    unittest.main()

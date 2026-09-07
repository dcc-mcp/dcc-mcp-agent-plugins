"""Keep the trusted workflow's permission and revision boundaries executable."""

from __future__ import annotations

import os
import subprocess
import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from unittest.mock import mock_open, patch

import yaml

WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/publication-gates.yml"
BOOTSTRAP = "213194ff992c28951fbbb37473199c33af6ebfb2"


class PublicationGateWorkflowTests(unittest.TestCase):
    def setUp(self) -> None:
        # BaseLoader preserves GitHub's `on` key instead of YAML 1.1 booleans.
        self.workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
        self.jobs = self.workflow["jobs"]
        self.validation = self.jobs["publication-gates"]

    def step(self, step_id: str) -> dict:
        return next(step for step in self.validation["steps"] if step.get("id") == step_id)

    def execute_inline(self, step: dict) -> None:
        source = step["run"].split("<<'PY'\n", 1)[1].split("\nPY", 1)[0]
        exec(compile(source, str(WORKFLOW), "exec"), {})

    def test_all_main_changes_trigger_the_three_job_contract(self) -> None:
        self.assertEqual(set(self.workflow["on"]), {"pull_request_target", "push"})
        for event in self.workflow["on"].values():
            self.assertEqual(event["branches"], ["main"])
            self.assertNotIn("paths", event)
            self.assertNotIn("paths-ignore", event)
        self.assertEqual(set(self.jobs), {"status-start", "publication-gates", "status-finish"})

    def test_only_isolated_publishers_receive_status_write_and_api_token(self) -> None:
        self.assertEqual(self.workflow["permissions"], {"contents": "read"})
        self.assertEqual(self.validation["permissions"], {"contents": "read"})
        self.assertNotIn("env", self.workflow)
        token_jobs = []
        for name, job in self.jobs.items():
            if name != "publication-gates":
                self.assertEqual(
                    job["permissions"],
                    {
                        "contents": "read",
                        "pull-requests": "read",
                        "statuses": "write",
                    },
                )
            for value in job.get("env", {}).values():
                self.assertNotIn("github.token", value)
                self.assertNotIn("secrets.", value)
            for step in job["steps"]:
                self.assertNotIn("continue-on-error", step)
                self.assertNotIn("github.token", step.get("run", ""))
                self.assertNotIn("secrets.", step.get("run", ""))
                for key, value in step.get("env", {}).items():
                    if "github.token" in value or "secrets." in value:
                        self.assertEqual((key, value), ("GH_TOKEN", "${{ github.token }}"))
                        self.assertIn('python3 -I "$publisher"', step["run"])
                        self.assertIn("scripts/report_publication_status.py", step["run"])
                        token_jobs.append(name)
        self.assertCountEqual(token_jobs, ["status-start", "status-finish"])

    def test_checkouts_use_only_trusted_base_without_persistent_credentials(self) -> None:
        for name, job in self.jobs.items():
            checkouts = [
                step
                for step in job["steps"]
                if step.get("uses", "").startswith("actions/checkout@")
            ]
            self.assertEqual(len(checkouts), 1)
            checkout = checkouts[0]
            expected = (
                "${{ steps.revisions.outputs.base }}"
                if name == "publication-gates"
                else "${{ github.event.pull_request.base.sha }}"
            )
            self.assertEqual(checkout["with"]["ref"], expected)
            self.assertEqual(checkout["with"]["persist-credentials"], "false")
            self.assertEqual(checkout["with"]["submodules"], "false")
            self.assertGreater(job["steps"].index(checkout), 0)
            for step in job["steps"]:
                if "uses" in step:
                    self.assertRegex(
                        step["uses"], r"^actions/(checkout|setup-python)@[0-9a-f]{40}$"
                    )
        self.assertEqual(
            next(step for step in self.validation["steps"] if "uses" in step)["with"][
                "fetch-depth"
            ],
            "0",
        )

    def test_candidate_is_fetched_as_objects_and_only_baseline_code_runs(self) -> None:
        candidate = self.step("candidate")["run"]
        self.assertIn('"fetch", "--no-tags"', candidate)
        self.assertIn('"--no-recurse-submodules", "origin", candidate', candidate)
        self.assertIn('"--no-replace-objects"', candidate)
        commands = "\n".join(
            step.get("run", "") for job in self.jobs.values() for step in job["steps"]
        )
        for forbidden in (
            "git checkout",
            "git switch",
            "setup_released_core",
            "requirements.txt",
            "unittest",
            "pytest",
        ):
            self.assertNotIn(forbidden, commands)
        self.assertIn(
            'python -I "$GITHUB_WORKSPACE/scripts/check_publication_gates.py"',
            self.step("policy")["run"],
        )
        installs = [
            step["run"] for step in self.validation["steps"] if "-m pip " in step.get("run", "")
        ]
        self.assertEqual(len(installs), 1)
        for required in (
            "python -I",
            "--isolated",
            "--no-deps",
            "--only-binary=:all:",
            "PyYAML==6.0.3",
        ):
            self.assertIn(required, installs[0])
        for name in ("status-start", "status-finish"):
            commands = "\n".join(step.get("run", "") for step in self.jobs[name]["steps"])
            self.assertNotIn("pip ", commands)
            self.assertNotIn('"fetch"', commands)
            self.assertIn('[[ ! -f "$publisher" || -L "$publisher" ]]', commands)
            self.assertIn("candidate fallback is forbidden", commands)

    def test_push_bypasses_skipped_start_but_pr_requires_start_success(self) -> None:
        self.assertEqual(
            self.jobs["status-start"]["if"], "github.event_name == 'pull_request_target'"
        )
        self.assertEqual(self.validation["needs"], "status-start")
        self.assertEqual(
            " ".join(self.validation["if"].split()),
            "${{ !cancelled() && (github.event_name == 'push' || needs.status-start.result == 'success') }}",
        )

    def test_final_status_runs_after_failures_and_consumes_false_by_default(self) -> None:
        finish = self.jobs["status-finish"]
        self.assertEqual(set(finish["needs"]), {"status-start", "publication-gates"})
        self.assertEqual(
            finish["if"], "${{ always() && github.event_name == 'pull_request_target' }}"
        )
        self.assertEqual(
            self.validation["outputs"],
            {
                "policy-enforced": "${{ steps.policy.outputs.enforced || 'false' }}",
                "parents-verified": "${{ steps.candidate.outputs.verified || 'false' }}",
            },
        )
        self.assertEqual(
            finish["env"]["VALIDATION_RESULT"], "${{ needs.publication-gates.result }}"
        )
        for key, output in (
            ("POLICY_ENFORCED", "policy-enforced"),
            ("PARENTS_VERIFIED", "parents-verified"),
        ):
            self.assertEqual(
                finish["env"][key],
                "${{ needs.publication-gates.outputs." + output + " || 'false' }}",
            )
        command = finish["steps"][-1]["run"]
        for argument in (
            "--phase finish",
            '--validation-result "$VALIDATION_RESULT"',
            '--policy-enforced "$POLICY_ENFORCED"',
            '--parents-verified "$PARENTS_VERIFIED"',
        ):
            self.assertIn(argument, command)

    def test_true_outputs_follow_successful_policy_and_parent_checks(self) -> None:
        policy = self.step("policy")
        self.assertEqual(policy["if"], "steps.checker.outputs.enabled == 'true'")
        self.assertLess(
            policy["run"].index("check_publication_gates.py"), policy["run"].index("enforced=true")
        )
        candidate = self.step("candidate")["run"]
        self.assertLess(
            candidate.index("parents != [candidate, base, head]"), candidate.index("verified=true")
        )
        self.assertNotIn("enforced=true", self.step("checker")["run"])

    def test_unavailable_merge_does_not_block_status_but_validation_rejects_it(self) -> None:
        for merge in ("", "null", "0" * 40, "stale-ref", "--invalid-option"):
            with self.subTest(merge=merge):
                for name in ("status-start", "status-finish"):
                    with patch.dict(
                        os.environ,
                        {"BASE_SHA": "a" * 40, "HEAD_SHA": "b" * 40, "MERGE_SHA": merge},
                        clear=True,
                    ):
                        self.execute_inline(self.jobs[name]["steps"][0])
                    self.assertIn('--merge-sha="$MERGE_SHA"', self.jobs[name]["steps"][-1]["run"])
                env = {
                    "EVENT_NAME": "pull_request_target",
                    "PR_BASE_SHA": "a" * 40,
                    "PR_HEAD_SHA": "b" * 40,
                    "PR_MERGE_SHA": merge,
                }
                with (
                    patch.dict(os.environ, env, clear=True),
                    self.assertRaisesRegex(SystemExit, "PR_MERGE_SHA"),
                ):
                    self.execute_inline(self.step("revisions"))

    def test_status_jobs_reject_invalid_base_or_head_before_checkout(self) -> None:
        for name in ("status-start", "status-finish"):
            for key in ("BASE_SHA", "HEAD_SHA"):
                with self.subTest(job=name, field=key):
                    env = {"BASE_SHA": "a" * 40, "HEAD_SHA": "b" * 40, key: "--invalid-option"}
                    with (
                        patch.dict(os.environ, env, clear=True),
                        self.assertRaisesRegex(SystemExit, key),
                    ):
                        self.execute_inline(self.jobs[name]["steps"][0])

    def test_only_exact_missing_checker_baseline_gets_visible_bootstrap(self) -> None:
        for base, is_file, symlink, exists, rejected in (
            (BOOTSTRAP, False, False, False, False),
            ("a" * 40, False, False, False, True),
            (BOOTSTRAP, True, True, True, True),
            (BOOTSTRAP, False, False, True, True),
            ("a" * 40, True, False, True, False),
        ):
            with self.subTest(base=base, is_file=is_file, symlink=symlink, exists=exists):
                output = mock_open()
                stdout = StringIO()
                env = {
                    "BASE_SHA": base,
                    "GITHUB_OUTPUT": "output",
                    "GITHUB_STEP_SUMMARY": "summary",
                }
                with (
                    patch.dict(os.environ, env, clear=True),
                    patch("builtins.open", output),
                    patch.object(Path, "is_file", return_value=is_file),
                    patch.object(Path, "is_symlink", return_value=symlink),
                    patch.object(Path, "exists", return_value=exists),
                    redirect_stdout(stdout),
                ):
                    if rejected:
                        with self.assertRaisesRegex(SystemExit, "missing or not a regular file"):
                            self.execute_inline(self.step("checker"))
                        output.assert_not_called()
                    else:
                        self.execute_inline(self.step("checker"))
                        written = "".join(call.args[0] for call in output().write.call_args_list)
                        self.assertIn(f"enabled={'true' if is_file else 'false'}\n", written)
                        if not is_file:
                            self.assertIn("BOOTSTRAP NOT ENFORCED", written)
                            self.assertIn("::warning", stdout.getvalue())

    def test_pr_candidate_requires_exactly_the_ordered_base_and_head_parents(self) -> None:
        base, head, candidate = "a" * 40, "b" * 40, "c" * 40
        for parents in ((base, head), (head, base), (base,), (base, head, "d" * 40)):
            with self.subTest(parents=parents):
                replies = [base, "", candidate, " ".join((candidate, *parents))]
                env = {"BASE_SHA": base, "HEAD_SHA": head, "CANDIDATE_SHA": candidate}
                with (
                    patch.dict(os.environ, env, clear=True),
                    patch("subprocess.check_output", side_effect=replies),
                    patch("subprocess.run") as ancestry,
                ):
                    if parents == (base, head):
                        self.execute_inline(self.step("candidate"))
                    else:
                        with self.assertRaisesRegex(
                            SystemExit, "exactly the event base/head parents"
                        ):
                            self.execute_inline(self.step("candidate"))
                    ancestry.assert_not_called()

    def test_push_candidate_must_descend_from_event_before(self) -> None:
        base, candidate = "a" * 40, "c" * 40
        env = {"BASE_SHA": base, "HEAD_SHA": "", "CANDIDATE_SHA": candidate}
        for rejected in (False, True):
            with (
                self.subTest(rejected=rejected),
                patch.dict(os.environ, env, clear=True),
                patch("subprocess.check_output", side_effect=[base, "", candidate]),
                patch("subprocess.run") as ancestry,
            ):
                if rejected:
                    ancestry.side_effect = subprocess.CalledProcessError(1, "git")
                    with self.assertRaises(subprocess.CalledProcessError):
                        self.execute_inline(self.step("candidate"))
                else:
                    self.execute_inline(self.step("candidate"))
                ancestry.assert_called_once_with(
                    ["git", "--no-replace-objects", "merge-base", "--is-ancestor", base, candidate],
                    check=True,
                )


if __name__ == "__main__":
    unittest.main()

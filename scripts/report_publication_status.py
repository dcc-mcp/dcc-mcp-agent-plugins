"""Publish a trusted policy outcome on the exact PR HEAD, with drift checks.

Run only from the trusted baseline in an isolated status-writing job. This
module uses only stdlib and never reads candidate files or dependencies.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, Request, build_opener

CONTEXT = "publication-contract"
DESCRIPTIONS = {
    "pending": "Checking publication content against the trusted baseline",
    "success": "Trusted publication contract verified",
    "failure": "Trusted publication contract rejected",
    "error": "Publication contract not verified; see workflow evidence",
}
SHA_RE = re.compile(r"[0-9a-f]{40}")
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")


@dataclass(frozen=True)
class Event:
    repository: str
    pr_number: int
    head_repository: str
    base_sha: str
    head_sha: str
    merge_sha: str
    run_id: int

    def __post_init__(self) -> None:
        if any(
            not REPOSITORY_RE.fullmatch(name) for name in (self.repository, self.head_repository)
        ):
            raise ValueError("repository identity must be owner/name")
        if any(type(value) is not int or value <= 0 for value in (self.pr_number, self.run_id)):
            raise ValueError("PR and run identifiers must be positive integers")
        if any(not valid_sha(sha) for sha in (self.base_sha, self.head_sha)):
            raise ValueError("event revisions must be exact nonzero 40-hex commit SHAs")

    @property
    def pr_path(self) -> str:
        return f"/repos/{self.repository}/pulls/{self.pr_number}"

    @property
    def status_path(self) -> str:
        # Never replace this with a head read from a later PR response.
        return f"/repos/{self.repository}/statuses/{self.head_sha}"

    def payload(self, state: str) -> dict:
        return {
            "state": state,
            "context": CONTEXT,
            "description": DESCRIPTIONS[state],
            "target_url": f"https://github.com/{self.repository}/actions/runs/{self.run_id}",
        }


def valid_sha(value: str) -> bool:
    return bool(SHA_RE.fullmatch(value)) and value != "0" * 40


class GitHubApiError(RuntimeError):
    """A rejected write need not be retried as an uncertain accepted write."""

    def __init__(self, message: str, *, ambiguous_write: bool = False) -> None:
        super().__init__(message)
        self.ambiguous_write = ambiguous_write


class NoRedirects(HTTPRedirectHandler):
    """Never forward an authenticated request, even to another HTTPS host."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def drifted(event: Event, live: dict) -> bool:
    """Validate PR identity first; only revision/state drift permits correction."""
    try:
        identity_matches = (
            type(live["number"]) is int
            and live["number"] == event.pr_number
            and live["base"]["repo"]["full_name"] == event.repository
            and live["base"]["ref"] == "main"
            and live["head"]["repo"]["full_name"] == event.head_repository
        )
    except (KeyError, TypeError):
        identity_matches = False
    if not identity_matches:
        raise ValueError("GitHub PR identity does not match the trusted event")
    return (
        live.get("state") != "open"
        or live["base"].get("sha") != event.base_sha
        or live["head"].get("sha") != event.head_sha
    )


def github_api(token: str):
    """Use only the isolated job token, with no credential or endpoint fallback."""
    opener = build_opener(NoRedirects())

    def request(method: str, path: str, payload: dict | None = None) -> dict:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        req = Request(
            "https://api.github.com" + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "Content-Type": "application/json",
                "User-Agent": "dcc-mcp-publication-contract",
            },
        )
        try:
            with opener.open(req, timeout=20) as response:
                result = json.load(response)
        except HTTPError as error:
            raise GitHubApiError(
                f"GitHub API {method} failed with HTTP {error.code}; no credential fallback",
                ambiguous_write=method == "POST" and error.code >= 500,
            ) from None
        except (URLError, OSError, ValueError):
            raise GitHubApiError(
                f"GitHub API {method} response was not verifiable",
                ambiguous_write=method == "POST",
            ) from None
        if not isinstance(result, dict):
            raise GitHubApiError(
                "GitHub API response must be an object", ambiguous_write=method == "POST"
            )
        return result

    return request


def desired_state(
    phase: str, validation_result: str, policy_enforced: bool, parents_verified: bool
) -> str:
    if phase == "start":
        return "pending"
    if phase != "finish":
        raise ValueError("unknown publication-status phase")
    if validation_result == "failure":
        return "failure"
    if validation_result == "success" and policy_enforced is True and parents_verified is True:
        return "success"
    return "error"


def report(
    event: Event,
    phase: str,
    validation_result: str,
    policy_enforced: bool,
    parents_verified: bool,
    api,
) -> dict:
    state = desired_state(phase, validation_result, policy_enforced, parents_verified)
    if state == "success" and not valid_sha(event.merge_sha):
        state = "error"
    if drifted(event, api("GET", event.pr_path)):
        state = "error"
    posted = False
    try:
        receipt = api("POST", event.status_path, event.payload(state))
        posted = True
        validate_receipt(event, state, receipt)
        changed = drifted(event, api("GET", event.pr_path))
    except (ValueError, RuntimeError) as error:
        # If observation fails after a positive write, do not leave our success
        # as verified evidence. Correction is bound to the original event HEAD.
        uncertain_write = not isinstance(error, GitHubApiError) or error.ambiguous_write
        if state in {"pending", "success"} and (posted or uncertain_write):
            correct_to_error(event, api)
        raise
    if changed and state != "error":
        correct_to_error(event, api)
        state = "error"
    return {
        "state": state,
        "context": CONTEXT,
        "head_sha": event.head_sha,
        "base_sha": event.base_sha,
        "merge_sha": event.merge_sha if valid_sha(event.merge_sha) else None,
        "run_id": event.run_id,
    }


def validate_receipt(event: Event, state: str, receipt: dict) -> None:
    if (
        receipt.get("context") != CONTEXT
        or receipt.get("state") != state
        or receipt.get("target_url") != event.payload(state)["target_url"]
        or type(receipt.get("id")) is not int
        or receipt["id"] <= 0
    ):
        raise ValueError("GitHub status receipt does not match this run")


def correct_to_error(event: Event, api) -> None:
    # Revalidate identity before corrective writes too. Drift never retargets
    # this event's status, and no subsequent success is emitted.
    drifted(event, api("GET", event.pr_path))
    validate_receipt(event, "error", api("POST", event.status_path, event.payload("error")))
    drifted(event, api("GET", event.pr_path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--pr-number", type=int, required=True)
    parser.add_argument("--head-repository", required=True)
    parser.add_argument("--base-sha", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--merge-sha", required=True)
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument("--phase", choices=("start", "finish"), required=True)
    parser.add_argument(
        "--validation-result",
        choices=("success", "failure", "cancelled", "skipped"),
        default="skipped",
    )
    parser.add_argument("--policy-enforced", choices=("true", "false"), default="false")
    parser.add_argument("--parents-verified", choices=("true", "false"), default="false")
    args = parser.parse_args()
    try:
        event = Event(
            args.repository,
            args.pr_number,
            args.head_repository,
            args.base_sha,
            args.head_sha,
            args.merge_sha,
            args.run_id,
        )
        token = os.environ.get("GH_TOKEN")
        if not token:
            raise ValueError("missing isolated status-job token; no credential fallback")
        outcome = report(
            event,
            args.phase,
            args.validation_result,
            args.policy_enforced == "true",
            args.parents_verified == "true",
            github_api(token),
        )
    except (ValueError, RuntimeError) as error:
        print(f"Publication HEAD status not verified: {error}", file=sys.stderr)
        return 1
    print(json.dumps(outcome, sort_keys=True))
    return 0 if outcome["state"] in {"pending", "success"} else 1


if __name__ == "__main__":
    raise SystemExit(main())

# Publication gates

The `Publication gates` workflow checks canonical Skill publication coverage
and content/version changes before publication. It does not publish Skills,
change versions, or verify registry visibility.

## What maintainers must change

- Register every canonical Skill under `plugins/dcc-mcp/skills/` in the
  ClawHub publication manifest. Missing, duplicate, or stale
  entries fail the gate; a newly added Skill cannot remain invisible to the
  publication lists.
- Increase the suite version when packaged Skill content changes relative to
  the event baseline, including added or removed Skills. Keep plugin,
  marketplace, ClawHub, and `metadata.dcc-mcp.version` values consistent.
  Keeping every file at the same old version is not sufficient; version
  decreases are also rejected.
- Increase the suite version for changes to `scripts/package_openclaw_skill.py`
  as well, even when canonical Skill files are unchanged. This conservative
  rule covers changes to packaging policy: the trusted checker never executes
  the candidate packager to decide whether its output would stay equivalent.
  The same rule covers `.gitattributes` at the repository root, `plugins/`,
  `plugins/dcc-mcp/`, and `plugins/dcc-mcp/skills/`: checkout attributes can
  change archive bytes without changing a Skill's Git blob. Attributes inside
  individual Skills already count as packaged content. This guard covers these
  controlled packaging inputs, not arbitrary candidate CI code; existing
  workflow review and independent CI remain necessary.
- Keep the repository's existing validation and release checks. This gate is
  an additional content/revision contract, not a replacement for tests,
  packaging checks, registry immutability checks, or publication approval.

Use the existing version-bump workflow described in the
[README](../README.md#skill-suite). Gate-only changes do not require editing
public Skill bytes or manufacturing a Skill release, provided the packager
policy is unchanged too.

## Trusted baseline, untrusted candidate

The workflow runs for pull requests targeting `main` and every push to `main`,
without path filters. It uses the existing pinned checkout and Python actions,
and no publication secrets. The validation job has only `contents: read`.
Two isolated PR status jobs add only `statuses: write`, not `checks: write`;
they also have `pull-requests: read` for PR identity verification. Their API
token is provided only to the status-publisher step. Credentials are
not persisted; submodules are disabled.

| Event | Executed checker | Candidate read as Git objects |
|---|---|---|
| `pull_request_target` | Exact event `pull_request.base.sha` | Event merge SHA, or a bounded API resolution when omitted, with exactly the event base and head as its two parents |
| `push` to `main` | Exact event `before` | Exact `github.sha`, which must descend from `before` |

Every revision must be a nonzero, lowercase 40-hex commit SHA before Git uses
it. If the event omits its merge SHA, the trusted start publisher makes at most
three metadata attempts using its existing read permissions. Each attempt binds
the open PR, repository, target branch, base SHA, head SHA, and head repository
to the event. A candidate must have exactly the ordered base/head parents in
GitHub commit metadata, and a second PR read must retain the same identity and
merge SHA. Only that validated scalar reaches the read-only gate, which fetches
the immutable commit and repeats the exact-parent check using Git. An unavailable
merge commit, identity drift, malformed metadata, or API error fails closed.
There is no head-only check or candidate-code fallback. A supplied valid event
merge SHA remains unchanged; rerunning an old event does not change its baseline.
Update the PR to obtain a fresh event after its base or head changes.

Only the trusted baseline is checked out. Fetching the candidate adds Git
objects; it does not place candidate files in the working tree. The baseline
checker reads both trees as data, including candidate manifests and Skill
content. It never imports or runs candidate scripts, tests, local actions,
dependency declarations, or setup helpers.

The only installed checker dependency is `PyYAML==6.0.3`, requested directly
from PyPI without candidate requirements. Python runs with `-I`; the checker
adds only its own trusted baseline helper directory to its import path. No
candidate checkout, `PYTHONPATH`, or current-directory import can supply code.
These boundaries address the untrusted-code execution risk documented in
[GitHub's `pull_request_target` guidance](https://docs.github.com/en/actions/reference/security/securely-using-pull_request_target)
and use [Python isolated mode](https://docs.python.org/3/using/cmdline.html#cmdoption-I).

## Status belongs to the PR HEAD

Do not infer the executed checker revision from an automatic Actions check or
run's commit association. Separate status jobs publish the
`publication-contract` commit status on the exact event HEAD, while recording
the trusted base and synthetic merge SHA separately as validation evidence.

Before validation, the trusted publisher retrieves the current PR and verifies
the repository, PR identity, base SHA, head SHA, and head repository against
the event. Matching forks are supported. Only then does it post `pending`.
Validation runs only if that start job succeeds. Push events skip both status
jobs and run the read-only validation directly.

Status jobs require exact base and head SHAs, but an unavailable or malformed
synthetic merge SHA does not prevent `pending` on that HEAD. The publisher
normalizes unavailable merge metadata and forbids success without it. After
publishing pending, the start publisher resolves an omitted merge SHA against
the unchanged event or fails without emitting an output. The read-only
validation and terminal publisher consume that SHA; validation still rejects
a missing or invalid SHA and never relaxes its exact-parent check. The final
job reports `failure` or `error` on the original event HEAD when resolution or
validation fails.

The final status job uses `always()` after both the start and validation jobs,
so failed candidate fetches and failed or skipped validation still reach the
status publisher. It repeats the live PR identity/revision check before each
write and checks again afterward. Detected drift or verification errors retract
a positive status to `error` on the original event HEAD if the API permits the
corrective write; the publisher never writes to the new HEAD.

| Validation outcome | Terminal status |
|---|---|
| Successful job, checker enforcement, and exact merge parents explicitly verified | `success` |
| Validation failure | `failure` |
| Cancelled, skipped, bootstrap, or other non-enforced result | `error` |
| PR drift | `error` on the event HEAD; publisher fails |

Only a successful baseline checker execution sets the enforcement output to
`true`. A separate output records successful candidate fetch and exact-parent
verification; both default to `false`. A successful job that merely reports
bootstrap cannot publish success.
Both status jobs execute only the standard-library publisher checked out from
the exact trusted base, using isolated Python and no installed dependencies.
They never fetch candidate objects or run candidate code. A missing publisher
or API permission error fails closed; the workflow never falls back to the
candidate publisher. Authenticated API requests do not follow redirects,
including redirects to another path on the same host. Cancellation before the
terminal job runs leaves pending, not verified success. The API does not offer
an atomic write-and-recheck operation: persistent network failure or permission
loss after an accepted positive write can prevent its correction. A failed
status job therefore means unverified evidence even if the remote status could
not be cleared; it is not new validation proof.

The resolution change must itself be accepted into a trusted baseline before
an event can execute it. A resolver present only in the proposed PR cannot fix
that PR's old baseline workflow; its local contract tests are source-review
evidence, not proof that the revised gate has run in GitHub Actions.

## Activation and changes to the gate

The first PR introducing this workflow cannot be protected by a checker that
does not yet exist on the trusted baseline. Its ordinary PR self-tests and
independent review must establish the initial implementation. A green self-test
is not evidence that the trusted publication gate ran.

There is one explicit bootstrap exception: if the checker is absent at baseline
`213194ff992c28951fbbb37473199c33af6ebfb2`, the workflow validates the revision
relationship but skips publication-policy enforcement. It emits an Actions
warning and a job summary headed `Publication gates: BOOTSTRAP NOT ENFORCED`.
This includes the introducing merge's push run when its `before` is that exact
commit. A missing or non-regular checker at any other baseline fails. There is
no analogous publisher fallback: a PR status job whose baseline predates the
publisher fails without publishing success. The initial PR still requires
independent self-tests and review.

For the initial bootstrap's packager refactor, require separate byte-for-byte
equality evidence for all four canonical Skill ZIPs produced before and after
the change. That evidence supports accepting the initial policy seam without
manufacturing a Skill release; it is not trusted-gate enforcement or an ongoing
waiver. After activation, packager-only changes require a suite version increase.

After the introducing change is accepted on `main`, subsequent events execute
the checker from their trusted baseline. A PR that edits or deletes the checker,
its helpers, or this workflow cannot use its proposed checker to validate
itself. Gate changes take effect only after acceptance on `main`; the push
comparison still uses the previous baseline's checker.

After live verification, maintainers can configure repository rules to require
the HEAD-bound `publication-contract` commit status, not merely the base-SHA
workflow check. This change does not configure branch protection or prove any
required-status rule is active; it cannot prevent an authorized bypass. A push
failure is post-merge evidence; this standalone workflow does not order or cancel the
separate publishing workflows. Registry upload acceptance, moderation state,
exact-version public visibility, and a registry's `latest` pointer remain
separate checks.

## Read back a PR's publication evidence

Use an authenticated GitHub CLI with read access. Run this Bash example with
the PR number you are reviewing; it performs only reads:

```bash
set -euo pipefail
repo=dcc-mcp/dcc-mcp-agent-plugins
read -r -p 'PR number: ' pr
before=$(gh pr view "$pr" --repo "$repo" --json headRefOid,baseRefOid \
  --jq '"\(.headRefOid) \(.baseRefOid)"')
read -r head base <<< "$before"
printf 'Expected HEAD: %s\nExpected base: %s\n' "$head" "$base"
status_path="repos/$repo/commits/$head/status?per_page=100"
read_receipt() {
  gh api "$status_path" --jq '[.sha, (.statuses[] |
    select(.context == "publication-contract") | .id, .state, .target_url)] | @tsv'
}
receipt=$(read_receipt)
read -r reported_head status_id state run_url <<< "$receipt"
printf 'HEAD/status ID/state/target_url: %s\n' "$receipt"
[[ "$reported_head" == "$head" && "$state" == success ]] || {
  printf '%s\n' 'Missing, non-success, or mismatched HEAD status; not verified.' >&2; exit 1;
}
case "$run_url" in
  "https://github.com/$repo/actions/runs/"*) ;;
  *) printf '%s\n' 'No publication workflow receipt; not verified.' >&2; exit 1 ;;
esac
run_id=${run_url##*/}
[[ "$run_id" =~ ^[0-9]+$ ]]
read_run() {
  gh api "repos/$repo/actions/runs/$run_id" \
    --jq '[.path, .event, .head_sha, .run_attempt, .status, .conclusion] | @tsv'
}
run=$(read_run)
read -r workflow event run_head attempt run_status conclusion <<< "$run"
[[ "$workflow" == .github/workflows/publication-gates.yml && "$event" == pull_request_target ]]
[[ "$run_status" == completed && "$conclusion" == success ]]
gh run view "$run_id" --repo "$repo" --attempt "$attempt" --json jobs
gh run view "$run_id" --repo "$repo" --attempt "$attempt" --log
after=$(gh pr view "$pr" --repo "$repo" --json headRefOid,baseRefOid \
  --jq '"\(.headRefOid) \(.baseRefOid)"')
[[ "$after" == "$before" ]] || { printf '%s\n' 'PR revisions changed; not verified.' >&2; exit 1; }
[[ "$(read_receipt)" == "$receipt" && "$(read_run)" == "$run" ]] || {
  printf '%s\n' 'Status or run attempt changed; not verified.' >&2; exit 1;
}
```

Require the returned `sha` to equal the full expected HEAD and the latest
`publication-contract` status to be `success`. Its `target_url` must identify
the same completed, successful run whose three gate jobs succeeded. Do not
select an older green status from its history. If more than 100 distinct status
contexts exist, paginate the combined-status endpoint before deciding that a
context is absent. In the captured run attempt's logs, verify the baseline
checker actually executed, with the expected
base and candidate, and the terminal publisher's JSON reports matching
`base_sha`, `head_sha`, `merge_sha`, and `run_id`. The candidate must be the
same exact synthetic merge whose event base/head parents passed verification;
`BOOTSTRAP NOT ENFORCED`, skipped policy, or missing evidence is not acceptance.

Actions run/check metadata can associate `pull_request_target` runs with the
PR HEAD; that association does not prove which code was executed. The explicit
trusted checkout and checker/publisher SHA evidence establish that boundary.
If the captured merge was unavailable or stale, preserve the failed run and
obtain a fresh PR event after correcting
the cause. Blindly rerunning the old event does not refresh its revisions.
This readback verifies one event's evidence; it neither configures nor proves
an active ruleset or required-status rule.

## ClawHub 0.24.1 held-version diagnostics

The publisher pins `clawhub@0.24.1` and its workflow selects Node.js 24. Upstream
requires Node.js `^22.13.0 || >=24`; a runner's incidental default is not the
runtime contract. This change does not authorize a publish or release any
paused version bump.

Authenticated `inspect @owner/slug --version VERSION --files --json` can return
exit code 1 with a `publication` object when the submitted version is held.
The helper retains the bounded `stage`, `checks`, and `retrying` diagnostic
rather than discarding stdout. It matches the requested slug/version and any
returned owner; upstream can omit the owner, so the owner-qualified command is
request context, not an additional ownership attestation. Unknown/mismatched
responses fail closed. Upstream `nextSteps` and free-form messages are not
executed or treated as instructions.

A `checks_failed` stage means required checks could not complete, not proof of
malware. `retrying: true` describes the existing upload's check retry; it never
requests another upload. Blocked/failed/expired/unavailable stages fail
verification. A `published` label without readable exact-version files is not
file verification either.

Keep evidence levels separate: authenticated upload receipt or immutable
fingerprint, owner-readable matching files, and public matching files. Held
publication diagnostics establish none of these. The existing upload-verifier
may report receipt/fingerprint-backed upload evidence with visibility pending;
that is **not** public availability or installability. An owner/public 404 alone
remains unconfirmed visibility, never proof that the version is absent or safe
to re-upload. No live Skill queries are needed for the mocked regressions.

Upstream contract reviewed:
[inspect.ts](https://github.com/openclaw/clawhub/blob/5f3b6e9855c2f8378245c35e3b4d4183893f4fb1/packages/clawhub/src/cli/commands/inspect.ts)
and [publication schema](https://github.com/openclaw/clawhub/blob/5f3b6e9855c2f8378245c35e3b4d4183893f4fb1/packages/clawhub/src/schema/schemas.ts).

ClawHub 0.24.1 upload receipts may say `pending-publication` (with
`publicationStatus: pending`), `submitted` (status not reported), or `published`.
All require the same exact slug/version, file count, folder, fingerprint and
version ID validation. None alone proves owner-readable bytes or public
installability, and a held receipt is not a reason to upload again. Mixed
publication diagnostics carrying version/file evidence are rejected rather than
allowed to hide a version mismatch or security block.

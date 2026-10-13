# Version and Update Evidence

Use this workflow when asked whether DCC-MCP is current, which release contains
a fix, whether an upgrade is compatible, or why an adapter embeds an older Core.
Read-only inspection does not authorize an installation, upgrade, rollback,
server restart, or issue submission.

## Select a Safe Entry Point

The new `dcc-mcp-cli update inspect` command requires a CLI build containing
the read-only inspection entry point. Until that build is released, use the
explicitly selected candidate in an isolated test environment. Do not assume
an arbitrary installed CLI supports it.

Older CLI builds can apply a previously staged update **before parsing any
arguments**, including `--help`, `--version`, and `update check`. Do not run
those commands as capability probes when the task requires no installation
changes. Inspect package/release metadata without launching the binary, and
report the runtime version as unknown. If a newer CLI is required, present the
exact official artifact and obtain approval through the existing verified
installation workflow first.

For a verified inspection-capable binary:

```bash
dcc-mcp-cli --output json update inspect
dcc-mcp-cli --output json update inspect --offline
```

## Keep Version Observations Separate

- The executing CLI version identifies the selected binary, not every copy on
  PATH and not the version of a running gateway or DCC adapter.
- A package manager's installed version is a receipt. It can differ from the
  binary after self-update; preserve the source and the discrepancy.
- Bundled Core identifies the code shipped in the selected build. An adapter's
  declared minimum Core requirement is not its bundled or loaded Core version.
- A runtime version requires evidence from that concrete running process.
  Preserve `unknown` and its reason when no supported observation is available;
  never substitute the latest release or a package receipt.

Report the provider, source URL, retrieval time, source time when available,
cache age/TTL, and offline or stale status. A cached value is not proof that
upstream has no newer release. Do not call a failed check “up to date”.

## Evaluate a Candidate

Present the current observation, candidate, channel, official release/changelog
links, compatibility evidence, and the reasons for the recommendation. A stable
release or matching platform asset does not prove host compatibility. Treat
missing host/runtime/Core constraints as unknown. Preserve user/operator pins;
report a conflict without editing or ignoring the pin.

Only explicit upstream fix evidence can support a version/fix relation. A
release note's explicit issue-closing reference means the release declares the
fix; it does not prove the user's runtime is fixed. Similar wording, an issue
being closed, or an unreleased merged PR is insufficient. Without exact
evidence, return “fix not established” and the official issue/release links.

Inspection is a dry run. Before changing anything, show the specific component,
source and target versions, environment, compatibility gaps, and rollback
availability, then obtain approval. Use the owning install/update path. Do not
turn a pinned candidate into an unpinned `latest` install. Cancelling a staged
update is different from rolling back an already activated binary; do not invent
a rollback command when the installation owner provides no verified path.

## Discover the Ecosystem

Reuse the official catalog and marketplace providers. On a CLI whose startup
behavior has been verified safe for the requested operation, use `dcc-types`
for supported applications/adapters and `marketplace search` / `inspect` for
Skills and plugin packages. Catalog discovery does not require a live host.
An empty live inventory is not evidence that the ecosystem has no matching
adapter. A catalog entry is not proof that the component is installed, loaded,
compatible, or newly published.

Keep official source identity and freshness with each result. Respect the
signed catalog's validity and withdrawal policy. Offline discovery may use only
the existing supported cache/bundled path; report unavailable sources explicitly.
Do not maintain a second hardcoded list of supported software in this workflow.

## Prepare an Issue Without Publishing It

Reuse `feedback route`, `feedback bundle`, and the plan-only `feedback file`
workflow when the selected CLI's entry point is safe. Collect only the fields
needed to explain the failure: version observations, loading-origin category,
bounded error classification/stack frames, minimal reproduction, and expected
versus actual behavior. Prefer a small synthetic reproduction.

Use a minimum-field allowlist. By default exclude credentials, usernames,
machine names, absolute home/project paths, private repository contents, chat
transcripts, environment dumps, raw logs, screenshots, and sensitive assets.
Show the actual projected JSON/issue body and which categories were omitted.
Pattern redaction and a `public_safe` flag do not guarantee that arbitrary text
contains no secrets; inspect the retained fields and disclose that limitation.

Search for duplicate issues only in the routed official repository, using a
sanitized fingerprint or narrowly reviewed public terms. A failed lookup is
unknown, not “no duplicates”. Present the candidate issues and the exact draft
title/body before asking whether to create an issue or comment on one.

Do not submit automatically. After explicit approval of the concrete content,
reuse the existing `feedback file` authorization binding for the finding path
and digest, fingerprint, repository, and catalog path/digest. If those values
or the draft change, produce a fresh preview. Never upload the complete local
diagnostic bundle or private source tree as an attachment by default.

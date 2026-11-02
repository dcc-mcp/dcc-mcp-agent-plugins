# ADR 0004: Centralize the MCP Registry manifest in Agent Plugins

- Status: **Proposed (Phase 1, draft — not activated)**
- Date: 2026-11-02
- Builds on: [ADR 0003](0003-agent-plugins-source-of-truth.md)
- Supersedes: nothing (this is additive; it does not change Skill ownership)

## Context

ADR 0003 made `dcc-mcp-agent-plugins` the single source of truth for the four
public Agent Skills. Registration of the MCP server itself, however, was still
driven from `dcc-mcp/dcc-mcp-core`: Core owns `server.json` and the
`publish-mcp-registry.yml` workflow that publishes it to the official MCP
Registry (`io.github.dcc-mcp/dcc-mcp-core`).

The product direction (2026-11-02) is to **unify registration management in the
Agent Plugins repository** — the same place that already owns public
distribution metadata (`.github/distribution.json`) and the brand assets —
rather than registering from many places.

Two hard constraints shape the design:

1. The official `server.json` schema treats `repository` as metadata about the
   **MCP server source code**. That source is `dcc-mcp-core`, not the skills
   repo. Centralizing the *manifest* must not be confused with claiming the
   *server source* lives here — `repository` must stay on Core.
2. Three version domains must never be conflated:
   - the **Registry metadata version** (`server.json.version` and
     `packages[0].version`, stamped together by the Core release),
   - the **PyPI package version** (`dcc-mcp-server`, provenance via the
     `mcp-name:` marker in its published README),
   - the **Agent Plugins suite version** (`plugins/dcc-mcp/plugin.json`,
     currently `0.19.120`).
   At authoring time these are `0.20.53` / `0.20.53` / `0.19.120`, while the
   live Registry `isLatest` is `0.20.51`. That gap is a separate Core re-release
    and is explicitly out of scope.

## Decision

### Phase 1 (this change) — centralize the manifest, keep the sole publisher

- Add `mcp_registry/server.json` here as the **single source of truth** for the
  MCP Registry entry, and centralize the **brand** fields here: `title`
  (`DCC-MCP`), `description`, `icons` (logo), `websiteUrl`.
- Keep **immutable** the identity/wiring fields: `name`
  (`io.github.dcc-mcp/dcc-mcp-core`), `packages[0].identifier`
  (`dcc-mcp-server`), `registryType`, `registryBaseUrl`, `transport`, and
  `environmentVariables`. `repository` stays pointed at the real server source,
  `dcc-mcp/dcc-mcp-core` — never the skills repo.
- `dcc-mcp/dcc-mcp-core` remains the **sole publisher** in Phase 1. Its existing
  `publish-mcp-registry.yml` is the only thing that mints the OIDC token the
  Registry accepts for the `io.github.dcc-mcp/*` namespace; that capability does
  not move in this phase.
- The publisher consumes the manifest from a **pinned full 40-hex commit SHA**
  (never a moving branch/tag) and verifies a **sha256 integrity digest** before
  use. `mcp_registry/publish-contract.json` records the pin, the digests, the
  immutable-field expectations, the version-domain rules, and the single active
  publisher.
- `scripts/validate_mcp_manifest.py` is a **read-only, stdlib-only fail-stop
  gate**, run as a dry-run before any publish. It validates:
  - conformance to the **vendored official schema** (`2025-12-11`, offline, so a
    moving upstream URL cannot change validation semantics),
  - pinned-SHA + sha256 integrity of manifest / schema / Core baseline,
  - backward compatibility of every immutable field against a verbatim Core
    `server.json` snapshot,
  - that `repository` still points at Core,
  - the three **version domains separately** (rejects ranges,
    `version != packages[0].version`, and any plugin-suite-version conflation),
  - that there is **exactly one** active publisher.
  If any check fails it exits non-zero and publishing must not proceed.
- No change is made to `.github/distribution.json` channel automation, no
  registry write, no OAuth, no new publish workflow, no trigger, and no change
  to credentials or security settings. This ADR and the Draft PR are the
  deliverable; nothing is cut over.

### Phase 2 (plan only — NOT implemented in this change)

Migration of the **publisher role** itself to Agent Plugins, so registration is
managed entirely where the manifest lives. Required ordering (reviewed
separately):

1. Disable the old Core `publish-mcp-registry.yml` `release` / `workflow_dispatch`
   triggers **first**.
2. Only then enable the new publisher here. **Cross-repo GitHub Actions
   `concurrency` groups are per-repository and do not serialize writers in two
   different repos** — two simultaneously active publishers would double-write
   the same registry name. The `single active publisher` check exists precisely
   to catch this.
3. Confirm the Registry still accepts the `io.github.dcc-mcp/*` namespace from
   the new publisher's OIDC identity, and keep the "no badge before the entry is
   queryable" gate.

This phase is deliberately left as a documented plan; executing it requires its
own review, its own exact-head approval, and must not be bundled with the Core
0.20.53 re-release.

## Consequences

- One owner and one review path for MCP registration metadata (brand fields),
  consistent with ADR 0003.
- A moving upstream schema or a mutable source ref cannot silently change what
  gets published: both are pinned and hash-verified offline.
- The Core server source remains the authoritative `repository`; centralization
  is about *registration metadata*, not relocating runtime code.
- Until Phase 2, the Core repo still publishes; this repo only prepares and
  validates the manifest. Phase 2 needs a coordinated cutover because
  cross-repo concurrency cannot prevent a double-write.

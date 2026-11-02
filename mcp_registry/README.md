# Centralized MCP Registry manifest (Phase 1 — draft, not activated)

This directory is the **single source of truth** for the `server.json` that
describes `io.github.dcc-mcp/dcc-mcp-core` on the official MCP Registry. It
lives in the skills/agent-plugins repo (which already owns public distribution
metadata and brand assets) per ADR 0004, while `dcc-mcp/dcc-mcp-core` remains
the **sole publisher** in Phase 1.

> Nothing in this directory publishes, registers, authenticates, or writes to
> any external service. It is data plus a read-only validator. Activating
> publication is a separate, reviewed Phase-2 action.

## Files

| Path | Purpose |
| --- | --- |
| `server.json` | The centralized manifest. Brand fields (`title`, `description`, `icons`, `websiteUrl`) are owned here; identity/wiring fields are immutable and match Core. |
| `publish-contract.json` | Machine-readable contract: pinned full-SHA source, sha256 digests, official-schema pin, immutable-field expectations, version-domain rules, single active publisher, Phase-2 plan. |
| `schema/2025-12-11.server.schema.json` | Vendored copy of the official `server.json` schema, so validation is offline and deterministic. |
| `core-baseline.server.json` | Verbatim snapshot of Core's `server.json` used for backward-compatibility checks. |
| `../scripts/validate_mcp_manifest.py` | Stdlib-only, read-only fail-stop validator + dry-run CLI. |
| `../tests/test_mcp_registry_manifest.py` | Negative-first contract tests (schema, integrity, backward-compat, version-domain, publisher). |
| `../docs/adr/0004-mcp-registry-centralized-manifest.md` | The two-phase design decision. |

## What is centralized here vs. kept immutable

- **Centralized (owned here):** `title` = `DCC-MCP`, `description`, `icons`
  (logo), `websiteUrl`.
- **Immutable (must equal Core baseline):** `name`
  (`io.github.dcc-mcp/dcc-mcp-core`), `packages[0].identifier`
  (`dcc-mcp-server`), `registryType`, `registryBaseUrl`, `runtimeHint`,
  `transport`, `environmentVariables`, and `repository` (which must stay on
  `dcc-mcp/dcc-mcp-core` — the real server source — and never point at a skills
  repo).

## Three version domains (validated separately, never conflated)

| Domain | Source | At authoring |
| --- | --- | --- |
| Registry metadata | `server.json.version` + `packages[0].version` (stamped together at publish) | `0.20.53` |
| PyPI package | `dcc-mcp-server` wheel (provenance via `mcp-name:` marker) | `0.20.53` |
| Agent Plugins suite | `plugins/dcc-mcp/plugin.json` | `0.19.120` |

The live Registry `isLatest` was `0.20.51` at authoring; that gap is the separate
Core 0.20.53 re-release and is out of scope here.

## Run the no-publish dry-run

```bash
# Read-only. No network/registry/OAuth/publish writes. Exits 0 on pass.
python scripts/validate_mcp_manifest.py
```

```bash
# Negative-first contract tests.
python -m pytest tests/test_mcp_registry_manifest.py -q
```

## Phase 1 gate (how the sole publisher consumes this)

`dcc-mcp/dcc-mcp-core`'s existing `publish-mcp-registry.yml` fetches
`mcp_registry/server.json` at the **pinned full 40-hex commit SHA** recorded in
`publish-contract.json`, verifies its sha256, runs `validate_mcp_manifest.py`
as a fail-stop gate, and only then publishes. A single active publisher is
enforced; cross-repo `concurrency` groups do not prevent double-write, which is
why the Phase-2 cutover requires disabling the old trigger before enabling a
new one. That cutover is **not** performed in Phase 1.

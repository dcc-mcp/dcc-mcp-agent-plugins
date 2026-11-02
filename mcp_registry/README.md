# Centralized MCP Registry manifest (Phase 1 — UNACTIVATED draft proposal)

This directory is a **proposed single source of truth** for the `server.json`
that would describe `io.github.dcc-mcp/dcc-mcp-core` on the official MCP
Registry. It lives in the skills/agent-plugins repo (which already owns public
distribution metadata and brand assets) per ADR 0004.

> **This change is an UNACTIVATED Phase-1 proposal.** It is DATA plus an
> offline, read-only validator. Nothing here publishes, registers,
> authenticates, or writes to any external service. **There is NO live consumer
> and NO enforceable publish gate**: `dcc-mcp/dcc-mcp-core`'s live
> `publish-mcp-registry.yml` does NOT fetch this repo's manifest and does NOT
> run this validator. The "sole publisher" / "single active publisher" rules
> below are a *design declaration* for a future reviewed Phase-2 integration,
> not enforcement of any live publish. An earlier draft falsely claimed the
> publisher already consumed `server.json` at a pinned commit SHA; that claim
> has been removed (the pinned SHA was the PR base, where `mcp_registry/` did
> not exist).

## Files

| Path | Purpose |
| --- | --- |
| `server.json` | The proposed centralized manifest. Brand fields (`title`, `description`, `icons`, `websiteUrl`) are owned here; identity/wiring fields are immutable and match Core. |
| `publish-contract.json` | Machine-readable contract: explicit activation flags (all false), sha256 digests, official-schema pin, immutable-field expectations, static version-domain rules, single-publisher design declaration, Phase-2 plan. **No source_ref fetch pin.** |
| `schema/2025-12-11.server.schema.json` | Vendored copy of the official `server.json` schema, so validation is offline and deterministic. |
| `core-baseline.server.json` | Verbatim snapshot of Core's `server.json` used for backward-compatibility checks. |
| `../scripts/validate_mcp_manifest.py` | Stdlib-only, offline, read-only dry-run validator + CLI. |
| `../tests/test_mcp_registry_manifest.py` | Negative-first contract tests (schema, activation-state, integrity, backward-compat, version-domain, publisher). |
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
- Note: `server.json`'s `icons[].src` is an immutable raw URL pinned to commit
  `1c24132` (the PR base) where the `plugins/dcc-mcp/assets/logo.png` asset
  actually exists — a valid asset pin, **not** a claim that any publisher
  fetches `mcp_registry/server.json` at that SHA. The removed `source_ref` was
  that false claim; the logo pin is unrelated and stays untouched (so the
  manifest's sha256 remains valid).

## Three version domains (validated separately, never conflated)

All three values below are **STATIC authoring-time snapshots**, not live state.
The offline validator only checks self-consistency against the contract; it
does NOT (and cannot, being stdlib-only and offline) query the live PyPI wheel
or the live Registry. "Version domains validated" means static data integrity
only — not dynamic/live version consistency.

| Domain | Source | At authoring |
| --- | --- | --- |
| Registry metadata | `server.json.version` + `packages[0].version` | `0.20.53` |
| PyPI package | `dcc-mcp-server` wheel (provenance via `mcp-name:` marker) | `0.20.53` |
| Agent Plugins suite | `plugins/dcc-mcp/plugin.json` | `0.19.120` |

The live Registry `isLatest` was `0.20.51` at authoring; that gap is the separate
Core 0.20.53 re-release and is out of scope here. The validator does not verify
either live value.

## Run the no-publish dry-run

```bash
# Offline, read-only. No network/registry/OAuth/publish writes. Exits 0 on pass.
python scripts/validate_mcp_manifest.py
```

```bash
# Negative-first contract tests.
python -m pytest tests/test_mcp_registry_manifest.py -q
```

## No live Phase-1 gate is wired

`check_activation_state` in the validator keeps the contract locked to
`status=draft-do-not-activate` with all activation flags false and rejects any
reintroduced `source_ref` pin. This is a guard on the proposal's own honesty —
it is NOT invoked by any publish workflow and does not gate any live publish.

A single active publisher is a *design declaration* checked over this repo's
contract data only; it does not enforce who can actually publish, because no
consumer is wired. Cross-repo `concurrency` groups do not prevent double-write,
which is why a future Phase-2 cutover requires disabling the old trigger before
enabling a new one.

Wiring a real consumer (so a publisher reads the manifest, verifies sha256, and
only then publishes) is a **separate Phase-2 change**: it needs hallong's
explicit activation decision, its own independent review, and an end-to-end
test proving the consumer reads the pinned content and verifies the sha256.
None of that is implemented, enabled, or authorized by this proposal.

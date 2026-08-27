# ADR 0002: Skill sync direction and drift control

- Status: Proposed (supersedes ADR 0001)
- Date: 2026-08-23

## Context

ADR 0001 made this repository the source of truth for the three public Agent
Skills and declared `dcc-mcp-core`'s copies frozen compatibility mirrors, to be
removed in one coordinated Core change. That migration never happened, and
practice inverted the decision:

- Core kept editing its copies through 2026-08-22, while this repository's
  snapshot stayed at 2026-08-06.
- 11 of the 17 shared Skill files diverged.
- The published `0.19.92` release therefore distributed superseded guidance —
  removed environment-variable names and the retired `windows-ui-control-host`
  architecture — while missing newer Core rules, including detached Sigstore
  provenance verification, SHA-256-verified `update apply`, immutable
  marketplace source pinning, and the DCC-CUA routing boundary.

Nothing detected any of this: the copy was manual and no job compared the two
sides. A higher release number shipped older content.

## Decision

Record the direction that practice already follows, and make the copy
mechanical instead of manual.

`dcc-mcp-core` authors the three public Skills, next to the runtime, validators,
and tests that the guidance describes:

- `dcc-mcp`
- `dcc-mcp-creator`
- `dcc-mcp-skills-creator`

This repository owns distribution: vendor manifests, standalone archives, GitHub
Releases, ClawHub, and Smithery publication. Files under
`plugins/dcc-mcp/skills/**` are copies except for the bounded distribution
metadata below. Fixes to Skill instructions are made in Core and pulled in; an
instructional change committed here alone is drift, not a fix.

This repository owns released-product discovery because it must keep every
installable channel and generated catalog identical. The canonical source is
`plugins/dcc-mcp/skills/dcc-mcp/references/PRODUCTS.json`, derived from the
released `dcc-mcp-cli dcc-types --output json` result and reconciled with the
owning adapter repositories. It records one canonical `dcc_type`, bounded
aliases, bilingual routing examples, owner identity, install availability, and
the shared DCC-CUA/UI Control provider contract for every released product.

The generator `scripts/sync_product_discovery.py` owns only:

- the default Skill's description, `search-hint`, and tags;
- the default Skill's bounded generated product/UI routing block;
- `plugins/dcc-mcp/skills/dcc-mcp/agents/openai.yaml`;
- the default Skill's `references/PRODUCTS.json`;
- vendor manifest descriptions/keywords and generated distribution metadata.

The remainder of the default Skill body remains Core-owned. DCC-CUA is a conditional UI route,
not a hard dependency for every typed-tool task, so the generated frontmatter
does not add `metadata.dcc-mcp.depends`. Shared canonical Skill behavior remains
in Core; current decision-contract ownership is tracked by
[`dcc-mcp-core#2383`](https://github.com/dcc-mcp/dcc-mcp-core/issues/2383).

The copy is a command, and CI enforces it:

- `scripts/sync_core_skills.py --source <core-checkout>` copies the Skill
  directories and records the Core commit in `.github/core-skills-sync.json`.
- `.github/workflows/core-sync.yml` runs `--check` against that pinned commit on
  every push and pull request, so any edit outside the explicit distribution
  ownership set fails CI.
- `scripts/sync_product_discovery.py --check` rejects drift across all generated
  manifests and interfaces. Required CI and release jobs add
  `--check-core-catalog` to compare all 35 identities, owners, repositories, and
  install availability against the catalog at the immutable Core commit recorded
  in `PRODUCTS.json`; this prevents a coordinated source/product rename from
  remaining merely self-consistent. `--check-cli` additionally verifies the
  installed released CLI's exact result without silently rewriting human-reviewed
  aliases.
- The same workflow compares against Core's default branch weekly, so newer
  upstream content surfaces as a scheduled failure instead of silent staleness.

Skill suite versions stay decoupled from Core release numbers. Skill content can
be re-published without a Core release, and Core can release without changing
Skill content, so `metadata.dcc-mcp.version` in each `SKILL.md` is
repository-owned and is the one field the sync preserves rather than copies.
The bounded default-Skill discovery fields above are also preserved and
regenerated from `PRODUCTS.json`; every other field is compared to Core.
Published Skill versions are immutable, so any content change requires a bump.

Core's remaining top-level Skills are not distributed here:

| Skill | Owner |
|---|---|
| `asset-source` | Core; Marketplace/example ownership review |
| `dcc-cua` | Core; ships with the DCC UI Control runtime it documents |
| `spatial-interchange` | Core; ships with the interchange runtime it documents |
| `marketplace-create-extension` | Core marketplace tooling until its API contract is decoupled |
| `marketplace-publish-extension` | Core marketplace tooling until its API contract is decoupled |
| `.agents/skills/dcc-mcp-core` | Core repository maintenance only |

Adding one of these to the distributed suite means adding it to
`.github/core-skills-sync.json`, the ClawHub and Smithery manifests, and this
table.

## Consequences

- Skill guidance is written once, where its runtime lives, and cannot silently
  diverge from what it documents.
- Released-product identities and aliases are written once in the distribution
  catalog and projected into every installable plugin/Skill surface.
- Drift is a CI failure with a named remedy instead of an unnoticed stale
  release.
- Contributors who want to change Skill instructions are sent to `dcc-mcp-core`;
  this repository reviews bounded discovery metadata, packaging, manifests, and
  release mechanics.
- ADR 0001's planned removal of Core's copies is abandoned. Core's `skills/`
  directory remains canonical for instructions, not release debt.
- Discovery/catalog/CI evidence remains distinct from licensed real-host
  validation and cannot promote a product to that state.

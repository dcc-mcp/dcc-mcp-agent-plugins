# ADR 0003: Agent Plugins owns public Skills

- Status: Accepted
- Date: 2026-09-04
- Supersedes: [ADR 0002](0002-skill-sync-direction.md)

## Context

The four public Agent Skills have independent versions, manifests, tests, and
publication channels in this repository. Keeping authoring copies in
`dcc-mcp-core` made ownership ambiguous and required a reverse copy workflow.
That workflow also prevented Core from removing compatibility mirrors after the
distribution repository became self-sufficient.

## Decision

`dcc-mcp-agent-plugins` is the sole source of truth for:

- `dcc-mcp`
- `dcc-mcp-creator`
- `dcc-mcp-skills-creator`
- `dcc-cua`

All instruction bodies, helpers, tests, versions, vendor manifests, archives,
and publication workflows for those Skills are maintained here. Changes land
here and publish from the validated `main` commit. The repository no longer
copies Skill bodies from Core or pins a Core commit for that purpose.

Core remains authoritative for runtime code, schemas, CLI behavior, the
released product catalog, and Core-owned/runtime Skills. Product discovery may
still validate against an exact released Core catalog and CLI; that read-only
compatibility check does not transfer Skill ownership back to Core.

## Consequences

- Public Skill changes have one owner and one review path.
- Core can remove the four compatibility mirrors without breaking a sync job.
- Runtime or schema changes that require guidance updates need coordinated PRs
  in both repositories, with each repository reviewing its own contract.
- Product discovery and release validation continue to pin released Core
  artifacts independently from Skill authoring.

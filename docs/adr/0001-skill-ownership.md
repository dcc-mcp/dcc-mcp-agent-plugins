# ADR 0001: Agent Skill ownership

- Status: Accepted
- Date: 2026-08-06

## Context

`dcc-mcp-core` historically owned runtime code and public Agent Skills in one
release. Agent hosts now need different manifests and release channels, while
Skill content can evolve without changing the Core ABI.

## Decision

This repository is the source of truth for the three public Agent Skills:

- `dcc-mcp`
- `dcc-mcp-creator`
- `dcc-mcp-skills-creator`

It also owns vendor manifests, standalone archives, GitHub Releases, and
ClawHub publication. All vendor packages consume the same Skill directories.

`dcc-mcp-core` continues to own runtime code, schemas, validators, examples,
and repository-local maintainer Skills. Its copies of the three public Skills
are compatibility mirrors until Core documentation, tests, and release jobs
consume this repository. The mirrors must then be removed in one coordinated
Core change. Submodules are not used because they make packaged wheels,
Windows checkouts, and offline source archives fragile.

The remaining Core top-level Skills are not migrated here yet:

| Skill | Owner |
|---|---|
| `asset-source` | DCC-MCP Marketplace/example ownership review |
| `marketplace-create-extension` | Core marketplace tooling until its API contract is decoupled |
| `marketplace-publish-extension` | Core marketplace tooling until its API contract is decoupled |
| `.agents/skills/dcc-mcp-core` | Core repository maintenance only |

## Release contract

A tag builds one plugin archive and three standalone Skill archives. The same
commit is validated for Codex, Claude Code, CodeBuddy, WorkBuddy, and ClawHub.
ClawHub is published by CI with `CLAWHUB_TOKEN`; OpenAI and Claude directory
submission remains human-reviewed.

## Consequences

- Skill releases can move independently from Core binaries.
- Agent hosts receive identical instructions from one source.
- The temporary Core mirror is deliberate release debt and must not be edited
  independently.

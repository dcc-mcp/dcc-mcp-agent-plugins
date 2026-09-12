---
name: dcc-mcp-skills-creator
description: >-
  Infrastructure skill - create, validate, scaffold, and review DCC-MCP skills
  for the dcc-mcp-core ecosystem. Use when authoring SKILL.md, tools.yaml,
  scripts, groups, prompts, or skill taxonomy. Not for creating a full DCC-MCP
  adapter repository - use dcc-mcp-creator.
license: MIT-0
allowed-tools: Bash Read Write Edit
metadata:
  dcc-mcp:
    dcc: python
    version: "0.19.104"
    layer: infrastructure
    compatibility: "Python 3.7+, dcc-mcp-core 0.17+"
    search-hint: "create dcc mcp skill, validate skill, scaffold skill, SKILL.md, tools.yaml, scripts, groups, prompts, skill taxonomy, long-running main-thread tools"
    tools: tools.yaml
    prompts: prompts.yaml
    skill-reference-docs:
      - "references/*.md"
  openclaw:
    homepage: https://github.com/dcc-mcp/dcc-mcp-agent-plugins/blob/main/plugins/dcc-mcp/skills/dcc-mcp-skills-creator/SKILL.md
---

# DCC-MCP Skills Creator

A first-class meta-skill for creating, validating, and reviewing DCC-MCP skill
packages. It bundles scaffold/validation tools together with agent-facing
authoring guidance for `SKILL.md`, `tools.yaml`, scripts, groups, prompts, and
progressive-loading taxonomy.

Use `dcc-mcp-creator` when the task is to create a full adapter repository for
a host such as Nuke, Blender, 3ds Max, Unreal, ZBrush, Houdini, or Maya. Use
this skill when the task is to create or improve the skill packages loaded by
those adapters.

## Install and Route

Install from an explicitly reviewed, full Git commit using the
[verified installation procedure](references/VERIFIED_INSTALL.md), then start
a new agent turn. It verifies the pinned Git objects before exporting the
Skill and does not execute a downloaded installer. Obtain the commit ID from
your trusted review record; a mutable branch, tag, or registry `latest` is not
an integrity pin. Treat each upgrade as a new review and pin.

## Distribution Boundary

A Skill remains the runtime and authoring unit. Use an Agent Plugin only as a
distribution unit when several Skills share release, compatibility, trust, and
uninstall boundaries:

```text
my-plugin/
|-- plugin.json
`-- skills/
    |-- inspect/SKILL.md
    `-- act/SKILL.md
```

The root manifest targets
`https://agent-plugins.org/schemas/1.0.0/plugin.schema.json`. Do not move
independently versioned or optional Skills into one plugin merely because they
share a repository. Existing DCC-MCP packages with multiple explicit
`source.skillRoots` remain valid `skill-bundle` packages.

Use [`dcc-mcp`](https://clawhub.ai/loonghao/skills/dcc-mcp) to operate an
existing DCC and
[`dcc-mcp-creator`](https://clawhub.ai/loonghao/skills/dcc-mcp-creator) to build
a complete adapter. A repository checkout may load this directory directly;
`DCC_MCP_SKILL_PATHS` and `extra_paths` are runtime paths for DCC adapters, not
installation instructions for an agent host.

## CLI-First Control Path

Use the `dcc-mcp` skill and `dcc-mcp-cli` for skill discovery, loading,
validation, and live calls whenever the agent can run shell commands. Start a
live validation with `dcc-mcp-cli list`: if the process launches, the CLI is
installed and the result checks the gateway plus DCC/MCP inventory. Diagnose a
failed health/inventory result with `dcc-mcp-cli doctor`; do not reinstall the
CLI, probe `import dcc_mcp_core`, or read server internals to infer readiness.

Only a shell-level command-not-found result means the CLI is missing. Ask for
consent; after explicit approval, immediately run the verified `dcc-mcp` helper
`python scripts/check_cli.py --ensure-cli --pretty` from that Skill's directory.
It installs the official CLI and rechecks health/inventory in the same attempt,
without a second confirmation. Keep it current with `dcc-mcp-cli update check`,
then `dcc-mcp-cli update apply`; apply stages the next CLI launch and does not
replace a running server binary.

## Quick Start

### Create a new skill

```python
# Call the loaded MCP tool:
# dcc_mcp_skills_creator__create_skill(
#     name="maya-rigging",
#     parent_dir="/path/to/skills/dir",
#     dcc="maya",
#     tool_name="create_locator",
#     affinity="main",
# )
```

### Validate an existing skill

```bash
dcc-mcp-cli lint /path/to/my-skill
```

The CLI loads the sibling `tools.yaml` table and invokes every declaration
through Core's real router with deterministic mock handlers. CI fails if a
sync declaration produces a job envelope or an async declaration produces a
direct result. Adapter/DCC code is never imported or executed by this probe.

### Get a SKILL.md template

```python
# Call the loaded MCP tool:
# dcc_mcp_skills_creator__skill_template()
```

## Skill Directory Structure

```
my-skill/
|-- SKILL.md              # Required: metadata frontmatter + instructions
|-- tools.yaml            # Required when metadata.dcc-mcp.tools points here
|-- scripts/              # Optional: tool implementation scripts
|   `-- create_locator.py
`-- references/           # Optional: recipes, examples, and long-form docs
    |-- RECIPES.md
    `-- NOTES.md
```

## Current Tool Contract

Read [references/TOOL_RUNTIME_CONTRACT.md](references/TOOL_RUNTIME_CONTRACT.md) when this workflow applies.

## Authoring Workflow

1. Decide whether the skill is infrastructure, domain, thin-harness, or example.
2. Give the skill a kebab-case name and each local tool a snake_case name.
3. Keep host API calls inside scripts, with lazy imports so discovery works without the host running.
4. Import same-directory helper modules directly; in-process runners expose the executing script's directory only for the call, so scripts must not mutate `sys.path` for sibling imports. In particular, do not repeat the legacy pattern shown in [houdini#157](https://github.com/dcc-mcp/dcc-mcp-houdini/pull/157/changes#diff-20f6c4a5b206da54475e771ac54351c25975cbcb533595f074c7f26d07ad09a2R11-R13):

   ```python
   script_dir = str(Path(__file__).resolve().parent)
   if script_dir not in sys.path:
       sys.path.insert(0, script_dir)
   ```

   That mutates process-global import state and leaks across skills. Script-directory lifetime is runtime ownership; use a direct sibling import and let the executor scope resolution to the current call.
5. Import dependency-light runtime helpers from `dcc_mcp_core.skills_helper` first: JSON/YAML codecs, bounded HTTP helpers, safe file/path helpers, validation, cancellation checks, and result helpers.
6. Declare `metadata.dcc-mcp.depends` for prerequisite skills, then declare `execution`, `affinity`, `timeout_hint_secs`, schemas, annotations, and failure recovery chains in `tools.yaml`. Do not rely on runtime Python introspection for missing schemas. For high-frequency tools, add `call_examples` so agents can copy argument payloads without trial-and-error.
7. Put long examples, recipes, and host-specific notes under `references/`.
8. Validate with `validate_skill_dir` or `dcc_mcp_core.validate_skill()` before
   loading it in an adapter. For discovery/load performance regressions, assert
   deterministic backend operation counts; use elapsed-time thresholds only as
   supplemental evidence.
9. If the desired behavior requires parsing core internals or adapter-private YAML at runtime, stop and request a core API instead.

## Improve Skills From Completed Tasks

Use retained gateway evidence only after the user-visible task and its
validation are complete. Keep one stable `session_id` in call metadata, then
query the narrowest useful slice:

```bash
dcc-mcp-cli stats --range 24h --dcc-type <dcc> --session-id <session-id>
```

Get the `review_skill_improvement` prompt from this skill and supply the stats
JSON plus bounded task and validation summaries. Treat `total_calls == 0` as
missing evidence, not success. Never include hidden reasoning, raw prompts,
credentials, or unredacted payloads.

The Core `ObservabilityQuery.get_repeated_scripts()` helper is an internal,
read-only evidence query. It is not an agent/gateway/CLI promotion entry point.
Its `candidate_id` is a stable identity for the canonical tuple
`sha256 + reuse_key + dcc_type + tool_name`; the result is always
`decision=manual_review` and `recommended_action=human_review_only`. Candidate
data must be reviewed and explicitly authorized by the task owner before any
skill is edited, published, or otherwise promoted. Never infer authorization
from a candidate or automate that transition.

Prefer `no_change`, then improving an existing skill, and create a new skill
only for a repeated, reusable workflow that no current skill owns. Validate any
accepted change with `validate_skill_dir` or `dcc-mcp-cli lint` before loading
it. Statistics inform a proposal; they never authorize editing or publishing a
skill without the task owner's requested scope.

For a failed task, first use the `dcc-mcp` recovery flow: retain the
`request_id`, run `doctor` for runtime/readiness faults, query
`stats --status failure --session-id <session-id>`, and record structured
feedback through the gateway-owned `dcc-mcp-cli feedback` command. A live
adapter's `dcc_feedback__report` is only a shared Core forwarder to that same
gateway contract. The public-safe
`/v1/debug/issue-reports/<request_id>` payload is suitable for a reviewed issue;
never publish `?mode=raw` automatically.

Published Skills should declare `metadata.dcc-mcp.links.repo` and
`metadata.dcc-mcp.links.issues`. Copy those exact values into Finding v1
`evidence.routing` before using `dcc-mcp-cli feedback route`; never infer a
tracker from a package name. Missing, non-canonical, or conflicting ownership
must fail closed, and resolving a route never authorizes issue creation.

Fix this Skill only when the evidence identifies its schema, script,
description, next-tool, or workflow contract. Route adapter/runtime failures to
`dcc-mcp-creator` and shared CLI/gateway/core failures to `dcc-mcp-core`. A
one-off tool bug is not evidence for creating another Skill.

When reviewing existing skills, reject top-level DCC-MCP extension keys such
as `dcc`, `version`, `tags`, `tools`, `groups`, `depends`, `search-hint`,
`runtimes`, `prompts`, and `resources`. Move them under
`metadata.dcc-mcp.*`; for version metadata, use
`metadata.dcc-mcp.version: "1.0.0"`. Validate the installable skill directory
that contains the `SKILL.md` loaded by adapters, not only mirrored repository
docs or marketplace metadata.

Read [AUTHORING_WORKFLOW.md](references/AUTHORING_WORKFLOW.md) and
[DCC_TOOL_CONTRACTS.md](references/DCC_TOOL_CONTRACTS.md) before changing a
production skill package.

## Gateway-Facing Tag Taxonomy

Read [references/TAXONOMY_COMPATIBILITY.md](references/TAXONOMY_COMPATIBILITY.md) when this workflow applies.

## Validation Rules

The validator checks:

- **SKILL.md** exists and is readable
- **YAML frontmatter** is well-formed
- **Required fields**: `name`, `description`
- **Name format**: kebab-case, <=64 chars, matches directory name
- **Field lengths**: description <=1024, compatibility <=500
- **Tool declarations**: non-empty names, no duplicates, snake_case client-safe format
- **Script files**: `source_file` references exist in `scripts/`
- **Sidecar files**: `metadata.dcc-mcp.tools/groups/prompts` references exist
- **Dependencies**: `metadata.dcc-mcp.depends` consistency
- **Spec compliance**: non-standard top-level keys are frontmatter errors; dcc-mcp-core extensions must live under `metadata.dcc-mcp.*` and point to sibling files
- **Version metadata**: `metadata.dcc-mcp.version` is accepted and projected
  to `SkillMetadata.version`; top-level `version` fails with an actionable
  migration hint
- **Skill helper adoption**: `validate_skill_dir` emits `skill-helper-adoption` warnings when scripts import avoidable dependencies covered by `dcc_mcp_core.skills_helper`, such as `requests`, `httpx`, PyYAML, or local JSON/HTTP/file/path helper modules

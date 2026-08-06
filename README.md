# DCC-MCP Agent Plugins

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="./plugins/dcc-mcp/assets/logo-dark.png">
  <img alt="DCC-MCP Agent Plugins" src="./plugins/dcc-mcp/assets/logo.png">
</picture>

The official distribution repository for DCC-MCP Agent Skills across Codex,
Claude Code, CodeBuddy, WorkBuddy, OpenClaw, ClawHub, Gemini CLI, GitHub
Copilot, Cursor, Windsurf, OpenCode, Cline, Roo Code, Kiro, Amp, and other
Agent Skills-compatible hosts.

One canonical Skill suite lives under `plugins/dcc-mcp/skills/`. Vendor
manifests are thin adapters; they do not fork instructions or runtime behavior.

## Install

### Most agents (recommended)

Install the default `dcc-mcp` Skill with one command. The installer detects
supported agents in the current workspace and lets you choose the target:

```bash
npx --yes skills@1.5.22 add dcc-mcp/dcc-mcp-agent-plugins --skill dcc-mcp
```

This covers Gemini CLI, GitHub Copilot, Cursor, Windsurf, OpenCode, Cline, Roo
Code, Kiro CLI, Amp, OpenHands, Continue, Replit, and other Agent
Skills-compatible hosts. Start a new agent session if the host discovers Skills
only at startup. Use `--global` for a user-level installation or
`--agent <id> --yes` for a non-interactive explicit target; see the installer's
[supported-agent list](https://github.com/vercel-labs/skills#supported-agents).

After installation, prompts only need to describe the work:

```text
Use the dcc-mcp Skill to <describe the DCC task>.
```

The Skill handles DCC discovery, typed tool selection, and approval boundaries.
Install `dcc-mcp-creator` or `dcc-mcp-skills-creator` only when developing an
adapter or authoring a reusable DCC-MCP Skill.

### Portable Agent Plugin

GitHub Release archives include a root `plugin.json` conforming to the
[Agent Plugins 1.0.0 specification](https://agent-plugins.org/) and the same
canonical `skills/` directory. Compatible clients can load the archive as a
skills-only portable plugin; installation and distribution remain
client-defined by the standard.

### Native plugin marketplaces (optional)

Use a native marketplace when the host provides one. It installs the same
canonical Skills.

#### Codex

```powershell
codex plugin marketplace add dcc-mcp/dcc-mcp-agent-plugins
codex plugin add dcc-mcp@dcc-mcp
```

#### Claude Code

```text
/plugin marketplace add dcc-mcp/dcc-mcp-agent-plugins
/plugin install dcc-mcp@dcc-mcp
```

#### CodeBuddy

```powershell
codebuddy plugin marketplace add dcc-mcp/dcc-mcp-agent-plugins
codebuddy plugin install dcc-mcp@dcc-mcp
```

#### WorkBuddy

Add this repository URL from **Plugins > +**, or upload a standalone Skill ZIP
from the GitHub Release to **Skills > Add skill > Upload skill**.

#### OpenClaw and ClawHub

```bash
openclaw skills install @loonghao/dcc-mcp
openclaw skills install @loonghao/dcc-mcp-skills-creator
openclaw skills install @loonghao/dcc-mcp-creator
```

Direct ClawHub installs are also supported:

```bash
npx --yes clawhub@0.23.1 install @loonghao/dcc-mcp
npx --yes clawhub@0.23.1 install @loonghao/dcc-mcp-skills-creator
npx --yes clawhub@0.23.1 install @loonghao/dcc-mcp-creator
```

### Smithery Skills

The three canonical Skills are mapped to Smithery's GitHub-backed Skills
Registry. Search and install them with the Smithery CLI:

```bash
npm install -g smithery@latest
smithery skill search "dcc-mcp"
smithery skill add loonghao/dcc-mcp --agent claude-code
```

Maintainers can validate the mapping locally, then publish only with an
explicit flag and `SMITHERY_API_KEY`:

```bash
python scripts/smithery_sync.py
SMITHERY_API_KEY=... python scripts/smithery_sync.py --publish
```

### PulseMCP

PulseMCP is an MCP Server directory, not a raw Agent Skills registry. This
repository therefore does not publish Skill ZIPs there. Submit a hosted or
local DCC-MCP Server from the owning adapter/core release through
[`pulsemcp.com/submit`](https://www.pulsemcp.com/submit); keep Agent Skills on
Smithery, ClawHub, or an Agent Skills-compatible host.

## Skill suite

| Skill | Purpose |
|---|---|
| `dcc-mcp` | Operate live DCC applications through structured tools |
| `dcc-mcp-skills-creator` | Create and validate DCC-MCP Skills |
| `dcc-mcp-creator` | Create and modernize DCC-MCP adapters |

The suite was migrated from `dcc-mcp-core` at version `0.19.91`. New Skill
releases are maintained here; Core keeps a compatibility mirror only during the
consumer migration described in
[`docs/adr/0001-skill-ownership.md`](docs/adr/0001-skill-ownership.md).

## Development

```powershell
python -m pip install "dcc-mcp-core==0.19.91"
python scripts/validate_repository.py
npx --yes skills@1.5.22 add . --list
./scripts/build-packages.ps1

codex plugin marketplace add .
codex plugin add dcc-mcp@dcc-mcp

claude plugin validate . --strict
codebuddy plugin validate ./plugins/dcc-mcp
```

Tagging `v<version>` creates a GitHub Release, uploads the plugin and standalone
Skill archives, then publishes the three immutable Skill versions to ClawHub.
The repository secret `CLAWHUB_TOKEN` is required for live ClawHub publication.

OpenAI and Claude public directories require human review; CI builds and
validates their submission artifacts but does not bypass those review portals.
See [`SUBMISSION.md`](SUBMISSION.md).

## Security boundary

The plugin ships no public MCP server. It connects to the user's local DCC-MCP
gateway through `dcc-mcp-cli`; a public multi-tenant MCP endpoint is a separate
security and deployment product.

## License

Repository code is MIT. Published Skill content is MIT-0 as declared by each
`SKILL.md` and required by ClawHub.

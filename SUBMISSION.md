# Publication checklist

Channel status, automation, and ready-to-paste directory entries are generated
into [`docs/DISTRIBUTION.md`](docs/DISTRIBUTION.md) from
[`.github/distribution.json`](.github/distribution.json) and the released Skill
suite. Regenerate it with `python scripts/build_geo_site.py` before submitting
anywhere by hand; CI fails when it is stale.

## OpenAI Plugin Directory

Submit as **Skills only** in the OpenAI Platform plugin submission portal.

Required before submission:

- Verify the DCC-MCP developer or business identity in the OpenAI Platform.
- Grant the submitter **Apps Management: Write**.
- Publish support, privacy policy, and terms URLs under `https://dcc-mcp.github.io/`.
- Upload the final Skill bundle and production logo.
- Select supported countries and add release notes.

Positive review cases:

1. List live DCC-MCP instances without changing scene state.
2. Search for a Blender modeling tool, describe it, then call it with valid arguments.
3. Search for a Maya read-only inspection tool and explain its safety annotations before calling it.
4. Detect that no DCC instance is running and follow the documented zero-instance recovery flow.
5. Install a known DCC-MCP marketplace Skill and reload the matching live adapter after user approval.

Negative review cases:

1. Refuse to invent a tool slug when search returns no match; report the typed-tool gap.
2. Do not execute an adapter install plan with `--execute` without explicit user approval.
3. Do not switch to generic Computer Use after a policy, authorization, security, or user-interruption failure.

## Claude community marketplace

Run `claude plugin validate ./plugins/dcc-mcp --strict`, then submit the repository through the Claude plugin submission form. Approved third-party plugins are published to `claude-community`, not Anthropic's curated official marketplace.

## CodeBuddy and WorkBuddy

Validate the CodeBuddy plugin and marketplace locally before publishing the repository. WorkBuddy supports local Skill upload today; use `scripts/build-packages.ps1` to produce the upload archive from the same canonical Skill.

## Universal Agent Skills hosts

Run `npx --yes skills@1.5.22 add . --list` in CI and
`npx --yes skills@1.5.22 add dcc-mcp/dcc-mcp-agent-plugins --list` against the public
repository. This is the shared distribution path for Gemini CLI, GitHub
Copilot, Cursor, Windsurf, OpenCode, Cline, Roo Code, Kiro, Amp, and other
Agent Skills-compatible hosts. Add a vendor-native manifest only when it adds a
real capability beyond Skill discovery.

## Smithery Skills

Smithery supports GitHub-backed Skills under a namespace and slug. The
repository keeps the three source paths in `.github/smithery-skills.json` and
validates them in CI. The default command is read-only; publish only after
reviewing the target paths:

```bash
python scripts/smithery_sync.py
SMITHERY_API_KEY=... python scripts/smithery_sync.py --publish
```

## npm

`v<version>` publishes the canonical Skill suite as `@dcc-mcp/skills` with npm
provenance. The package ships instructions only, no runtime code. Configure the
`NPM_TOKEN` repository secret with publish rights on the `@dcc-mcp` scope, and
create the scope on npmjs.com before the first release.

```bash
python scripts/build_npm_package.py
npm pack ./dist/npm --dry-run
```

## skills.sh

skills.sh has no publish API or submission form. It indexes public repositories
and ranks them from anonymous telemetry emitted by the `skills` CLI, so the only
honest action is keeping the public repository installable. `release.yml`
installs all three Skills from the public repository on Linux, macOS, and
Windows with telemetry disabled and asserts the released version. Do not
generate install telemetry to influence ranking.

## GEO surface

Each release deploys `site/` to GitHub Pages: per-Skill pages with
`schema.org/SoftwareApplication` JSON-LD, `catalog.json`, `llms.txt`,
`llms-full.txt`, `sitemap.xml`, and a `robots.txt` that explicitly allows the
AI crawlers listed in `.github/distribution.json`. Enable **Settings > Pages >
Source: GitHub Actions** once; the deployment is automated after that.

## LobeHub and awesome lists

LobeHub's Skills marketplace and the awesome-list ecosystem index public
repositories. Submit the repository URL and paste the generated entry for the
Skill from `docs/DISTRIBUTION.md` so the description, version, and install
command match the release exactly.

## PulseMCP

PulseMCP currently catalogs MCP Servers and exposes a read-only registry API;
it is not a direct `SKILL.md` upload target. Submit a DCC-MCP Server through
[`pulsemcp.com/submit`](https://www.pulsemcp.com/submit) only when the owning
Core/adapter release provides a public MCP endpoint or supported server
package. Do not represent an Agent Skill ZIP as an MCP Server.

## ClawHub

Pull requests dry-run the official ClawHub CLI. A `v<version>` tag publishes
the three entries in `.github/clawhub-skills.json` after GitHub Release
creation. Configure `CLAWHUB_TOKEN` before pushing a release tag.

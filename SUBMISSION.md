# Publication checklist

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

Run `npx --yes skills add . --list` in CI and
`npx --yes skills add dcc-mcp/dcc-mcp-agent-plugins --list` against the public
repository. This is the shared distribution path for Gemini CLI, GitHub
Copilot, Cursor, Windsurf, OpenCode, Cline, Roo Code, Kiro, Amp, and other
Agent Skills-compatible hosts. Add a vendor-native manifest only when it adds a
real capability beyond Skill discovery.

## ClawHub

Pull requests dry-run the official ClawHub CLI. A `v<version>` tag publishes
the three entries in `.github/clawhub-skills.json` after GitHub Release
creation. Configure `CLAWHUB_TOKEN` before pushing a release tag.

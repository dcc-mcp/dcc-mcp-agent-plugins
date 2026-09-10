<!-- dcc-mcp-agent-quickstart:start -->
## Use {{DCC_NAME}} with AI agents

Install the official DCC-MCP Agent Skill. Codex users can use the native plugin
marketplace:

```powershell
codex plugin marketplace add dcc-mcp/dcc-mcp-agent-plugins
codex plugin add dcc-mcp@dcc-mcp
```

For Claude Code, CodeBuddy, Cursor, Gemini CLI, and other supported agents, use
the [official installation guide]({{INSTALL_GUIDE_URL}}). Start {{DCC_NAME}},
enable this adapter, and verify that the running instance is registered:

```powershell
dcc-mcp-cli list
```

Then ask your agent:

```text
{{SMOKE_PROMPT}}
```

The list must include `dcc_type={{DCC_TYPE}}`. If it does not, follow the
[connection troubleshooting guide]({{TROUBLESHOOTING_URL}}).
<!-- dcc-mcp-agent-quickstart:end -->

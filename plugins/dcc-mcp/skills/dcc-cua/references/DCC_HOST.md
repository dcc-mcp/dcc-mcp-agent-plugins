## DCC-host route

For a registered DCC instance, use the DCC-MCP UI Control tools or their CLI
projection:

```bash
dcc-mcp-cli load-skill ui-control --instance-id <instance-id> --output toon
dcc-mcp-cli ui-control snapshot --instance-id <instance-id> --json '{"session_id":"ui","process_id":1234,"window_handle":5678}'
dcc-mcp-cli ui-control act --instance-id <instance-id> --json '{"session_id":"ui","control_id":"ok","action":"click","snapshot_id":"<snapshot-id>"}'
dcc-mcp-cli ui-control act --instance-id <instance-id> --json '{"session_id":"ui","action":"invoke_menu","menu_path":["Window","Arrange","Left"]}'
dcc-mcp-cli ui-control stop --instance-id <instance-id> --json '{"session_id":"ui"}'
```

Use the same exact instance and session throughout the action chain. Do not
switch to another DCC process because it looks similar.


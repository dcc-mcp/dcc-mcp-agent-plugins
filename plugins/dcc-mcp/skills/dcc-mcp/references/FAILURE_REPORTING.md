## Step 5 — Analyze Failures and Report Bugs

Do not guess a root cause or blindly replay a mutation. Preserve `request_id`, `trace_id`, `job_id`, tool slug, instance id, sanitized arguments, error code, and validation result.

```bash
dccmcp doctor
dccmcp stats --range 24h --status failure --session-id task-42
dccmcp feedback --tool-name maya_geometry__create_sphere --intent "Create a sphere" \
  --blocker "Radius was ignored" --severity blocked \
  --dcc-type maya --instance-id <live-or-dead-instance-id> \
  --request-id <request-id>
```

Use `doctor` for profile, registry, daemon, binary, and readiness failures. For a tool failure, refresh `describe`, compare the schema/annotations with the attempt, inspect failure-only stats, and call the gateway-owned `feedback` command. Its severity is `blocked`, `workaround_found`, or `suggestion`; it remains available after the target instance exits, records a bounded entry in `resources://gateway/events`, and does not create an external issue. Instance-level `dcc_feedback__report` is only a live-adapter compatibility entry point and Core forwards it to the same gateway contract; it has no local-success fallback. Review persisted reports newest first with `feedback list`, or request the largest bounded structured window with `feedback export`; both accept `--range`, `--dcc`, `--severity`, `--limit`, and `--json`. Treat `skipped_invalid` and `deduplicated` as source-set evidence, and treat any read or capacity error as an incomplete export.

For a gateway-routed failure, use the CLI-returned `request_id` to read `/v1/debug/agent-traces/<request_id>` and public-safe `/v1/debug/issue-reports/<request_id>`. The latter supplies a bounded summary and suggested GitHub title/body. Never publish `?mode=raw` without human review; create an external issue only with user authorization.

Route schema/script/Skill defects to the owning package and `dcc-mcp-skills-creator`; dispatch/readiness/install/wiring defects to the adapter and `dcc-mcp-creator`; shared gateway/CLI/protocol defects to `dcc-mcp-core`. Include the smallest reproduction and safe report, not hidden reasoning.

### Review Reusable Friction

```bash
dccmcp stats --range 24h --dcc-type maya --session-id task-42
```

Only after acceptance, inspect `stats_coverage`. Gateway SQLite excludes `local_mcp_direct`; `configured_route_recorded=false` cannot support reflection. Re-run through `--require-gateway`; zero calls means missing evidence.

Load `dcc-mcp-skills-creator` and request `review_skill_improvement` with bounded task, stats, validation, and existing-skill summaries. Stats are not root-cause proof; prefer `no_change`, then `update_existing`, and create only for a repeated stable workflow. The review never authorizes out-of-scope changes.


# Application UI workflows

### DCC UI Control fallback

Load the **DCC UI Control** runtime with `dcc-mcp-cli load-skill ui-control` only
when structured DCC capabilities cannot reach the required semantic UI:

1. `ui_control__snapshot` with an exact `process_id`, `window_handle`, or `window_title`.
2. `ui_control__find` and one semantic `ui_control__act` when possible. For native menus, use `invoke_menu` with an explicit `menu_path` when semantic delivery cannot prove a Qt popup opened; require `native_menu_path`, honor `verification_required`, and re-observe.
3. `ui_control__snapshot` after every action before choosing the next action.
4. `ui_control__stop_computer_use` when the fallback completes, fails, or is abandoned.
The runtime defaults to `dcc-cua` 0.4.0+; `mock` is test-only, never a production fallback. After loading, local `search --query "ui control snapshot"` returns the loaded `ui_control__*` slugs as callable tool hits.

The runtime consumes standalone `dcc-cua`; inspect `dcc-cua profiles` and
`dcc-cua profile --id <id>` before binding the exact PID/window. Keep
`browser_dom` inside `dcc-cua`, and use `fab/launcher_download` when UE's Fab
surface is unavailable. Cloudflare, authentication, purchase, and security
confirmations remain trusted human boundaries even with full agent access.

The UI Control `session_id` identifies its scoped UI session, not stats
attribution. Use `--agent-session-id <task-id>` for `_meta.agent_context.session_id`.

For reusable demonstrations, start with the gateway call's `--agent-session-id`,
use structured tools first, then `stop` and `review`. After inspecting the
redacted timeline, `compile --reviewed` creates a local Skill and `WorkflowSpec`.
`replay` requires a new `--approve-replay` grant and current tool/schema. Recorded
approvals, instance/control ids, coordinates, credentials, and secrets grant no
authority. Never skip `search`, `describe`, or post-step verification.

Do not switch UI/input paths after policy, authorization, authentication,
security, confirmation, `desktop_unavailable`, or `user_interrupted` results;
the user or environment must resolve them first. Never widen scope, reuse stale
coordinates, or resume without an explicit request. Load the runtime Skill for
the complete target-binding, system-operation, capture, and artifact contract.

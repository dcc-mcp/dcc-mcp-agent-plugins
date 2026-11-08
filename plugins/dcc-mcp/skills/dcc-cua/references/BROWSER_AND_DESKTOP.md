## Browser and non-DCC route

Browser work remains inside DCC-CUA. Use the Host's typed browser surface and
`browser_dom` capabilities, not an in-app Browser or Chrome plugin.

For a broad browser request with no target, use the same bounded discovery
phase as other applications:

1. Use read-only `list_apps`/`list_windows` metadata to find an installed or
   running application, or use `launch_app` when the user asked to open one.
2. Select the returned exact PID/HWND and exact tab/target.
3. Before the first browser-window observation or input, report
   `provider=dcc-cua runtime=<version> pid=<exact-pid> hwnd=<exact-hwnd>`.

`list_apps`, `list_windows`, and launch responses are discovery evidence; they
do not authorize a screenshot, DOM read, or input action. Do not infer a target
from a title when an exact identifier exists, and do not select the first
candidate from an ambiguous result.

- Bind the exact tab/target returned by DCC-CUA; do not infer it from a title
  alone when an exact target identifier exists.
- Keep connection-scoped sessions and capabilities on one Host connection.
- Use DOM/semantic references from the latest observation rather than stale
  coordinates.
- `browser_prepare` and existing-profile attachment require both the Host grant
  and the session task grant advertised by the runtime contract.
- Authentication challenges, CAPTCHAs, purchases, account/security changes,
  and unexpected permission prompts remain trusted human boundaries.


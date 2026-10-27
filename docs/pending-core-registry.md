# Pending Core Registry Guidance

Status: draft coordination for [Core #2863](https://github.com/dcc-mcp/dcc-mcp-core/issues/2863).
Keep publication on hold until the matching Core/CLI fix is merged and released.
This note does not change published Skill content or suite versions.

Proposed addition to the `dcc-mcp-creator` runtime/registry reference and the
`dcc-mcp` local inventory troubleshooting guidance:

> Use Core's shared registry resolver for CLI inventory, gateway runners,
> sidecars, and Python lifecycle helpers. The corrected default is
> `~/.dcc-mcp/registry-live`, using the user profile on Windows. Redirecting
> `TEMP`, `TMP`, or `TMPDIR` must not select another registry. An explicit
> registry option takes precedence over `DCC_MCP_REGISTRY_DIR`, then the user
> default. If the user home cannot be resolved, supply an explicit registry.
> For mixed Core/CLI versions, pin `DCC_MCP_REGISTRY_DIR` to the directory
> already used by the live services. Do not migrate, merge, scan other
> registries, or restart a gateway/DCC to manufacture an inventory result.
> Preserve `list.registry_dir` and `doctor.local.registry_dir` as diagnostic
> provenance. A registry path or fixture test does not prove real-host readiness.

After release, confirm the shipped resolver behavior, move the approved
paragraph into the two owning Skills, and prepare a fresh coordinated suite
version through the existing publication scripts. Keep that promotion separate
from the current publication-version PR and its writer.

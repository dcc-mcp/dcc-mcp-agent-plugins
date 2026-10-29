# Pending standalone CLI verification contract

This coordinates the next Install SOP acceptance slice with Core issue
[#2252](https://github.com/dcc-mcp/dcc-mcp-core/issues/2252) and implementation
[#2862](https://github.com/dcc-mcp/dcc-mcp-core/pull/2862). It is not released
Skill guidance, and it must not be copied into published Skills until the
matching Core implementation and its supported CLI version are verified.

The pending command is:

```bash
dcc-mcp-cli verify --dcc-type <dcc> --python <target-python> --json
```

It checks a pip adapter's pinned installed distribution version and module
import in the explicitly supplied target interpreter. It reuses the bounded
doctor import probe and the Install SOP v1 report. There is no automatic PATH
interpreter fallback, factory invocation, package installation, rollback,
registry/profile lookup, gateway start or automatic update maintenance.
Imports execute module initialization; use the intended target environment.

An import/version failure or unavailable probe exits 40. Invalid plan inputs
exit 10; malformed command arguments exit 2. Successful local metadata/import
checks exit 0 but remain `status=partial`, `directly_usable=false`, with
`LIVE_DCC_VERIFICATION_REQUIRED`. Follow the separate authorized readiness
route rather than treating this as an installation/host acceptance result.
Non-pip verification remains unsupported. Preserve failure reports and the
original `not_evaluated`/pass/fail distinctions in downstream evidence.

This does not complete artifact-byte verification, target Core compatibility,
receipt-backed prior-version restoration, host enablement or native readiness.
The install tracker stays open. The companion suite metadata increment repairs
the already-merged output guidance's version collision; it does not promote
this pending verification contract into published Skills. ClawHub publication
requires a separate manual workflow dispatch with publishing enabled; merging
this source change does not publish or enable the pending contract.

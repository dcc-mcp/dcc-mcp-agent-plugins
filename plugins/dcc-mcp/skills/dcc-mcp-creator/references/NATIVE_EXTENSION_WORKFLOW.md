# Native extension workflow

Use this reference when the host has a native extension or action interface but
no released DCC-MCP adapter for the requested work. Keep the controller, native
host process, extension and gateway ownership explicit.

## Separate setup from integration

The CLI software manifest answers which executables it can detect or provision.
The adapter catalog answers which integrations it describes. An executable
version probe and archive receipt do not prove MCP registration, ready dispatch
or a native document effect.

Inspect the actual CLI build before recommending `host` commands. If the
installed release rejects them, record that fact; a reviewed development build
is source evidence. The coordinated [host deployment PR][core-host-pr] adds
Windows Inkscape portable archive handling. Read its [CLI contract][core-cli]
for the selected manifest, required checksum, extraction dependencies and
process-local destination. Reuse the user's existing setup authorization;
never change security settings or persistent consent to make a case run.

## Implement the smallest typed boundary

Place the maintained integration in its owning adapter package. The dedicated
[Inkscape adapter][inkscape-readme] supplies a Core composition root, standard
Python and CLI entry points, bundled declarative skill tools and native effect
resources. Follow its [install runbook][inkscape-install] and
[architecture contract][inkscape-architecture] at the exact reviewed commit.
Its runtime is a standalone controller invoking an Inkscape-hosted inkex effect;
a standard package does not imply persistent GUI document binding.

Keep software installation, Python package import, private-profile extension
installation, foreground service startup and real typed native effects separate.
Core's pinned Git clone verifies files, not package import or startup. The
adapter's plan-first lifecycle reports ownership, imports and already running
service readiness; a partial install is not proof of a native document effect.
The initial lifecycle uses a read-only Windows PE/hash host probe; Linux/macOS
lifecycle probing is unsupported. Actual software actions and native effects
remain separate checks. Use public Core lifecycle and deployment APIs rather
than private bindings. Preserve `readiness.version_source`; any legacy
missing-version fallback must strictly correlate the ready publication with
the live instance. Explicit registry-version conflicts remain failures.

The [standard adapter draft][inkscape-pr] owns this integration review. A draft
adapter package does not establish released product routing or official signed
install-catalog promotion.

Represent geometry with a bounded typed plan and current schema. The controller
may prepare JSON and extension configuration; native software must create,
accept and save the document. Opening an externally written SVG afterward, or
embedding a bitmap in it, does not prove native vector creation. Use the
existing Core server, declarative skill execution and isolated registry/gateway
contracts rather than introducing another executor or shared-session takeover.

Test input validation, path containment, owned-process cleanup, invocation
correlation and output-structure validation. Preserve nonce, process-parent
evidence, native argv/diagnostics, object structure and artifact hashes. Treat
these as local pipeline provenance, not cryptographic host attestation. Test
platform-specific parent-process behavior with the actual host.
On Windows, retain the extension's read-only parent handle before loading the
host extension libraries when a helper can exit during initialization. Keep
the complete native image, PID and creation/exit-time correlation mandatory;
an early handle preserves evidence rather than granting process authority.

## Validate the requested effect

Use the `dcc-mcp` operation route for inventory, search, typed calls and native
readback. Load its host deployment or native vector reference only when that
work is needed. Source-only development does not require starting a host.

Distinguish native creation/export, headless reopen and GUI visual acceptance.
A GUI launch PID or a mock test does not complete GUI QA. Preserve editable
layers/groups and a separate text-to-path release copy. Verify actual font
resolution and redistribution terms. Export transparent PNGs through software;
ICO/ICNS container packaging and size/hash checks may be separate scripts.

Inspect paint after native text-to-path conversion: live-text `currentColor`
can resolve to a fixed color. For a dynamic monochrome release, read the native
outlined glyph path data and rebuild it with explicit `currentColor` through a
new typed native plan and software export. Preserve the editable master and
readback evidence; do not rewrite the software-generated SVG externally.

Document missing persistent GUI binding, unvalidated platforms and cancellation
limits. Keep source-only examples and adapter drafts out of released product
routing until that support is reviewed through its owning catalog and release
process. A draft PR or a valid ICNS container does not establish a released
macOS integration.

[core-host-pr]: https://github.com/dcc-mcp/dcc-mcp-core/pull/2652
[core-cli]: https://github.com/dcc-mcp/dcc-mcp-core/blob/8228335cb25fb9acfa53a67078850b1727de131e/docs/guide/cli-reference.md
[inkscape-pr]: https://github.com/dcc-mcp/dcc-mcp-inkscape/pull/1

[inkscape-readme]: https://github.com/dcc-mcp/dcc-mcp-inkscape/blob/02a0fa6d47ce936f69e25c7a8bec5e6eebe4368a/README.md
[inkscape-install]: https://github.com/dcc-mcp/dcc-mcp-inkscape/blob/02a0fa6d47ce936f69e25c7a8bec5e6eebe4368a/install.md
[inkscape-architecture]: https://github.com/dcc-mcp/dcc-mcp-inkscape/blob/02a0fa6d47ce936f69e25c7a8bec5e6eebe4368a/docs/architecture.md

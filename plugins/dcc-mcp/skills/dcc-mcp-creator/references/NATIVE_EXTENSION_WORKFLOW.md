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

The coordinated [native Inkscape PR][core-vector-pr] is an unreleased example:
a standalone MCP controller invokes an Inkscape-hosted inkex effect. Read its
[pinned runtime contract][core-vector-readme] before reusing it. Its software
setup channel does not make it a released catalog adapter.

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

## Validate the requested effect

Use the `dcc-mcp` operation route for inventory, search, typed calls and native
readback. Load its host deployment or native vector reference only when that
work is needed. Source-only development does not require starting a host.

Distinguish native creation/export, headless reopen and GUI visual acceptance.
A GUI launch PID or a mock test does not complete GUI QA. Preserve editable
layers/groups and a separate text-to-path release copy. Verify actual font
resolution and redistribution terms. Export transparent PNGs through software;
ICO/ICNS container packaging and size/hash checks may be separate scripts.

Document missing persistent GUI binding, unvalidated platforms and cancellation
limits. Keep examples out of released product routing until that support is
reviewed through its owning catalog and release process. A draft PR or a valid
ICNS container does not establish a released macOS integration.

[core-host-pr]: https://github.com/dcc-mcp/dcc-mcp-core/pull/2652
[core-cli]: https://github.com/dcc-mcp/dcc-mcp-core/blob/8228335cb25fb9acfa53a67078850b1727de131e/docs/guide/cli-reference.md
[core-vector-pr]: https://github.com/dcc-mcp/dcc-mcp-core/pull/2651
[core-vector-readme]: https://github.com/dcc-mcp/dcc-mcp-core/blob/5a2f886cab3bd8746bd17e9042ec1ccd490f57e7/examples/native-inkscape/README.md

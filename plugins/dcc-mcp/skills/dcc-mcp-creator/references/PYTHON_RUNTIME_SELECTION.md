# Python runtime selection

Choose the runtime after the shared production-reuse gate and any relevant
template/license review. A reusable project does not establish interpreter
compatibility. Keep the task's existing evidence report for host probes,
selected versions, artifact identities and unresolved checks.

The companion [template-first catalog PR #38](https://github.com/dcc-mcp/dcc-mcp-agent-plugins/pull/38)
adds candidate license evidence to that production workflow. Keep runtime
ownership decisions here independent of template adoption or catalog availability.

## Owners and public contracts

- **DCC-MCP Runtime / Python payload:** owned by
  [dcc-mcp-runtime](https://github.com/dcc-mcp/dcc-mcp-runtime). It owns the
  external CPython/Core/adapter payload contract for a versioned side-by-side
  root with isolated `lib/site-packages`. Verify actual release payload availability.
  Preserve that isolation; do not add
  global or host `site-packages`, rewrite `PYTHONPATH`, or bundle Python again
  per adapter. Select an existing compatible verified runtime version first.
- **Rust `dcc-mcp-sidecar`:** the transport/service companion managed through
  Core's lifecycle helpers; its executable is not a Python interpreter. Preserve
  the host/adapter ownership and stop rules in [Runtime integration](RUNTIME_INTEGRATION.md).
- **Gateway:** shared discovery/routing service, not the Python payload or the
  adapter's interpreter owner. A healthy gateway does not prove either is ready.

The reviewed Runtime source is
[`3a54f666c4283bab160dbab3ac90630c9ed39087`](https://github.com/dcc-mcp/dcc-mcp-runtime/tree/3a54f666c4283bab160dbab3ac90630c9ed39087).
Its package declares version `0.2.0`; the source example manifests still declare
`0.1.0`, a null runtime digest/signature and placeholder adapter hashes. These
files are contract examples, not verified release artifacts or installation plans.
Check the actual selected release; neither a version string nor this document
proves a payload is installed or approved.

## Default decision

Use the small, offline [decision example](examples/python_runtime_selection.py)
as an authoring template for already-collected facts. It does not discover,
install, import or start a runtime. Keep actual selection, manifest handling,
negotiation and lifecycle implementation in their existing owners.

| Facts | Next step |
|---|---|
| Official JS/native bridge meets the task without Python | Use it; no Python payload is required. |
| Host Python exists and version, ABI and required dependencies are compatible | Use that host interpreter through the existing embedded adapter/dispatcher. |
| Host Python exists but is unknown or incompatible | Verify or repair the supported host profile; do not silently inject external CPython. |
| No host Python; adapter needs Python; shared Runtime is verified | Use that external runtime and the existing public handshake before registering the adapter. |
| No host Python; shared Runtime is missing or unverified | Produce installation preflight and an exact plan through the supported owner; obtain normal authorization before executing it. |
| Runtime/manifest/version mismatch, offline acquisition or denied authorization | Report the blocker; preserve the active version and never fall back to PATH Python, another download, per-adapter bundle or elevated permissions. |

Probe the real host interpreter's version/ABI and dependency availability; do
not infer them from the desktop shell. Native Python 3.7 remains an existing
LTS profile. Do not raise its minimum version or import the external Runtime
package into it. Runtime's reviewed package declares Python >=3.9; verify its
actual published interpreter/ABI requirements separately from the embedded
adapter and from native-versus-lite Core acceptance.

## Preflight, negotiation and installation

1. Bind the selected runtime and adapter identities, versions, platform,
   architecture, Python ABI, Core compatibility and capability set. Use the
   existing Runtime manifest loader and handshake, not a second adapter parser.
2. Obtain manifests and artifacts from the selected trusted release. Verify
   non-placeholder digests, the operator's signature/trust policy and actual
   bytes before importing code or activation. `load_manifest` validates shape;
   `negotiate` checks ABI and Core contract equality. Neither verifies artifact
   integrity, signature authenticity or that the running version matches the
   plan. Keep those checks with the existing installer/operator trust owner.
3. In an already verified external runtime, the public bootstrap entry is:

   ```python
   from dcc_mcp_runtime.bootstrap import require_adapter

   handshake = require_adapter(adapter_id)  # Existing configured manifest identity.
   ```

   It reads `runtime/manifest.json` and `runtime/manifests/<adapter_id>.json`
   from the runtime root, optionally configured by `DCC_MCP_RUNTIME_ROOT`.
   The variable selects a location, not trust. Reuse the configured owner; do
   not mutate a live environment or retry a rejected handshake as embedded mode.
4. The public CLI at that source only exposes `validate-manifest`; there is
   no documented `install` or `upgrade` CLI verb. The existing `plan_install`
   API produces a typed plan with operation ID, runtime ID, exact target,
   package path/digest, confirmation and rollback version. Execution belongs
   to an authorized host-owned allow-list installer. If that installer,
   verified payload or required signature is unavailable, stop at preflight.
   Do not invent a downloader or installation command to fill the gap.
5. Reuse Core's [adapter install SOP work](https://github.com/dcc-mcp/dcc-mcp-core/issues/2252)
   and the supported install/upgrade/rollback route for the actual installed
   release. The issue is a contract/work tracker, not evidence that every verb
   ships. Preserve older-peer capability checks and existing lifecycle helpers.
   Activate only after integrity, health and capability verification; failed
   activation retains/restores the previous side-by-side version.

Source unit tests and offline decision examples are not real-host acceptance.
Verify the selected interpreter, native bridge, one typed operation and shutdown
in the real host before claiming usable integration. An offline or refused
installation stays blocked; source planning may continue without changing it.

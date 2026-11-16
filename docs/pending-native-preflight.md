# Pending embedded native preflight and MotionBuilder dispatcher repair

This note coordinates Core issues [#2884][dll] / [#2885][preflight] and Mobu
issue [#15][mobu]. It is pending implementation guidance, outside packaged
Skills. Promote it only after the corresponding PRs, released versions and
exact-host acceptance are verified. It does not change publication authority.

The pending Core API is `dcc_mcp_core.verify_native_core()`. Run it in the
selected host interpreter before importing native-backed adapter server classes
or building schemas. It returns a JSON-safe report distinguishing
`native_core_available`, `native_extension_missing` and `native_load_failed`.
Failure includes the original exception, interpreter, bounded Windows DLL
directory candidates and recovery guidance. Keep local paths private. Native
loading success alone proves neither adapter readiness nor a working UI pump.

Core will retain `os.add_dll_directory()` handles for existing absolute
interpreter prefix/base-prefix/executable directories. An explicit
`DCC_MCP_PYTHON3_DLL_DIR` can expose a trusted runtime compatible with the host
Python version and architecture. This does not install, copy, rename, or prove
compatibility of a missing DLL. PATH alone cannot repair Python 3.8+ extension
dependency loading. A generic loader error does not prove `python3.dll` is the
only missing dependency. Ordinary package imports stay lazy; a broken native
JSON codec must fail explicitly rather than silently use the lite fallback.

The independent Mobu fix replaces the adapter's private queue with Core's
`HostUiDispatcherBase`. `HostExecutionBridge.resolve_host_dispatcher()` then
attaches the native HTTP queue, and `FBSystem.OnUIIdle` drains Python and native
work through the shared soft-budget pump. Workers must not call host SDK APIs
to wake it. Uninstall releases queued Python waiters; restart uses a new queue.

Verification has three separate levels:

1. Native preflight in the intended interpreter, including failure/repair retry.
2. Isolated MCP `initialize` / `tools/list` / `tools/call` with enforced main
   affinity and recorded host thread identity. This is executable host-free
   evidence, not MotionBuilder acceptance.
3. In MotionBuilder 2024 with its actual Python runtime and dependency layout,
   call the typed scene inspection/model-list tools through HTTP. Confirm the
   native loader and main-thread route both work without claiming that a green
   readiness response alone proves usability.

Long monolithic request-disconnect recovery ([Core #2883][disconnect]) remains
a separate problem. The dispatcher repair does not authorize pre-empting native
host work, restarting an artist's session, or claiming that disconnect recovery
has been fixed. The Install SOP tracker remains open until its own checklist
is satisfied.

[dll]: https://github.com/dcc-mcp/dcc-mcp-core/issues/2884
[preflight]: https://github.com/dcc-mcp/dcc-mcp-core/issues/2885
[mobu]: https://github.com/dcc-mcp/dcc-mcp-mobu/issues/15
[disconnect]: https://github.com/dcc-mcp/dcc-mcp-core/issues/2883

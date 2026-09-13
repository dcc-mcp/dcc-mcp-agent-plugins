# Runtime integration

Use only the contracts relevant to the integration being changed. The numbered
items are constraints by topic, not a required sequence for every adapter edit.

- Ownership and threading: vocabulary and items 1-6.
- Shared state, scene digest and UI binding: item 7.
- Gateway, sidecar lifecycle and readiness: items 8-9.
- Search, task metadata, recording and experiments: remaining items.

Resolve `docs/guide/` references against the matching Core source checkout if
those documents are not shipped in the installed plugin; do not infer their
contents or load the entire Core documentation tree.

## Runtime Vocabulary

- DCC startup hook: adapter code running inside the host at application startup; it prepares env/instance data and launches the service path without blocking the DCC UI/main thread.
- Per-DCC service: one registered runtime row for one concrete DCC instance; Python `DccServerBase` and Rust sidecars both participate as per-DCC services.
- Sidecar: the Rust `dcc-mcp-sidecar` child launched through the stable `dcc-mcp-server sidecar` command; it bridges host RPC to MCP/REST and exits when the watched DCC dies.
- Gateway daemon: the one machine-wide `dcc-mcp-server gateway` process that owns routing, dynamic capability search/describe/call, and Gateway Admin.
- Guardian: a lightweight loop inside daemon-backed services that probes gateway `/health` and re-ensures the daemon through `gateway-launch.lock`; it is not a separate process.
- Service heartbeat: registry freshness for the service row only. Do not describe heartbeat as the gateway restart trigger.
- Service owner: the process that owns the registry sentinel and MCP endpoint; its `pid`/sentinel prove the service itself is alive.
- Bound DCC host: optional external process identified by `host_pid`; both owner and host must stay alive. Standalone/headless services intentionally have no bound host.

## Integration contracts

1. Classify the ownership boundary before creating files:
   - Public DCC adapter: run `dcc-mcp-cli dcc-types`; improve an existing
     adapter instead of creating a duplicate. Add a genuinely new public
     adapter to `dcc-mcp-catalog.yml` and the compatibility matrix. A pip
     install entry requires the released universal wheel's exact HTTPS URL,
     catalog version, and SHA-256; omit install metadata until it is published.
   - Private non-DCC service: work in the supplied local or intranet project,
     keep its stable custom service id private, and do not require a GitHub
     repository, public catalog entry, issue, or release. Use a studio-owned
     catalog only when operators need `dcc-mcp-cli install` plans.
   - Skill package only: switch to `dcc-mcp-skills-creator`.
2. Classify the runtime integration:
   - Embedded Python host: Blender, 3ds Max Python, Houdini, Maya, Nuke.
   - External bridge host: ZBrush, Photoshop, Unity, custom tools.
   - Game/editor host with mixed Python or C++ bridge: Unreal, Unity.
   - Standalone internal service: no host bridge; use inline execution for
     ordinary service/file/API tools and keep every tool typed.
3. Read the relevant reference:
   - [ADAPTER_WORKFLOW.md](ADAPTER_WORKFLOW.md) for the build path.
   - [INTERNAL_SERVICE_WORKFLOW.md](INTERNAL_SERVICE_WORKFLOW.md) for a private non-DCC service with no public repository requirement.
   - [HOST_PATTERN_MATRIX.md](HOST_PATTERN_MATRIX.md) for host-specific wiring.
   - [CORE_ESCALATION_CHECKLIST.md](CORE_ESCALATION_CHECKLIST.md) before adding adapter-local glue.
    - [TESTING_AND_RELEASE.md](TESTING_AND_RELEASE.md) before validating or publishing.
    - **Python 3.7 policy**: native py37 is an LTS profile with no automatic calendar expiry. Verify the aggregate Python 3.7 gate is green and `requires-python = ">=3.7"` is unchanged before any release. `py37-lite` fallback does NOT satisfy release gates. Removal requires an accepted superseding ADR, a major release, and at least 180 days of notice.
    - [docs/guide/gateway.md](https://github.com/dcc-mcp/dcc-mcp-core/blob/main/docs/guide/gateway.md) for gateway daemon lifecycle details.
    - [docs/guide/adapter-install-lifecycle.md](https://github.com/dcc-mcp/dcc-mcp-core/blob/main/docs/guide/adapter-install-lifecycle.md) for sidecar launch/readiness details.
    - [docs/guide/adapter-install-sop.md](https://github.com/dcc-mcp/dcc-mcp-core/blob/main/docs/guide/adapter-install-sop.md) for the adapter-owned install, status, verify, uninstall, and upgrade contract.
    - [docs/guide/adapter-release-checklist.md](https://github.com/dcc-mcp/dcc-mcp-core/blob/main/docs/guide/adapter-release-checklist.md) for release train compliance.
    - [docs/guide/new-adapter-onboarding.md](https://github.com/dcc-mcp/dcc-mcp-core/blob/main/docs/guide/new-adapter-onboarding.md) for new adapter scaffolding.
    - [docs/guide/adapter-compatibility-matrix.md](https://github.com/dcc-mcp/dcc-mcp-core/blob/main/docs/guide/adapter-compatibility-matrix.md) for the per-DCC compatibility table.
4. Start from `DccServerBase` + `DccServerOptions.from_env(...)`.
   Classify the runtime lifetime explicitly:
   - Embedded adapter: the service owner is the DCC process; no separate host PID is needed.
   - Standard sidecar: pass `watch_pid=current_dcc_pid`; core publishes the sidecar owner and bound host as separate liveness signals.
   - Other out-of-process adapter: pass `dcc_pid=current_dcc_pid` so `McpHttpConfig.host_pid` binds discovery to the DCC lifetime.
   - Standalone/headless service: pass `instance_type="standalone"`, leave `dcc_pid` unset, and do not bind it to an optional GUI process. Runtime identity is independent from `standalone_main_thread`, which controls tool execution only.
5. Route host API calls through `HostExecutionBridge`; do not hand-roll a second script executor. Standalone services with no host-thread boundary should keep the default inline execution path.
   For file-backed typed `main(**params)` execution, publish mapping annotations
   only when their keys are strings (`Dict[str, V]`). Validate the requested
   SHA-256, derived schema, and structured params before materializing inline
   source; an invalid request must leave no script or sidecar file behind.
6. Keep service identity data-driven: `dcc_name`/custom service id, `server_name`, env-var prefix, skill names, and gateway metadata.
   Leave the instance port unset so core resolves `DCC_MCP_<DCC>_PORT` or asks the OS for a free port.
7. Use core helpers for skill discovery, `MinimalModeConfig`, project tools, resources, diagnostics, context snapshots, install lifecycle, and gateway failover before writing adapter-local wrappers. Python `DccServerBase.collect_skill_search_paths()` includes marketplace-installed skills under `~/.dcc-mcp/marketplace/<dcc>` (or `DCC_MCP_MARKETPLACE_INSTALL_ROOT/<dcc>`) when the directory exists, so adapters should not add a second marketplace path convention. Hermetic adapter tests should set `DCC_MCP_DISABLE_DEFAULT_SKILL_PATHS=1`; this excludes implicit local/platform defaults, marketplace installs, and Admin custom paths while explicit, bundled, and environment-provided skill paths remain active.
   `DccServerBase` also owns `DiagnosticRuntimeState`; do not add adapter-level
   recorder, sandbox, screenshot-capturer, dispatcher, server, or instance-context
   globals. Standalone registration code may inject one state into both
   diagnostic registration helpers.
   It also owns `feedback_store`, `script_execution_context`, and
   `checkpoint_store`; inject them into core helpers instead of creating
   adapter-level feedback buffers, persistent exec namespaces, or default stores.
   Adapters that expose `execute_python` should capability-gate cheap scene-state
   evidence by registering one host-owned callback with
   `register_state_digest_provider(..., context=server.script_execution_context)`.
   The callback returns `SceneStats` or its mapping shape (`object_count`,
   `vertex_count`, `has_mesh`, optional `extra`). Run scripts through
   `execute_with_state_digest(...)`; its native transaction pins that exact
   provider for both observations and returns public `SceneDigestSnapshot`
   values. A script cannot replace the provider used by its active transaction
   or poison the next transaction through `ScriptExecutionContext`. Pass both
   snapshots to `ScriptExecutionResult.from_value(...)`. Core bounds and redacts
   the payload, computes a deterministic fingerprint, and fails closed when the
   provider is absent, raises, returns malformed data, or supplies a mismatched
   fingerprint.
   Digest change proves only that observed state changed; leave `verified`
   omitted/false unless an adapter-owned postcondition verifies the claimed
   effect. Never turn contract-test evidence into a real-host success claim.
   The fingerprint and truncation marker detect deterministic corruption; they
   are not authentication, authorization, or proof of host identity. Core does
   not expose a Python secret, signing oracle, signed wire tag, or native factory
   that turns caller-supplied bytes into authenticated evidence. The adapter
   registers the provider before the native transaction starts, but that does
   not establish cryptographic authenticity; semantic verification remains
   adapter-owned. Pure-Python runtimes without that boundary fail closed with
   `scene_digest_custody_unavailable`. Mapping
   values beyond the bounded observation budget use a fixed sentinel, keeping
   equivalent provider mappings deterministic without unbounded reads.
   Core does not auto-register or advertise an `execute_python` route. Gate
   adapter discovery and route registration on successful provider
   registration, and expose `unavailable/provider_missing` when
   `capture_state_digest(...)` reports no provider.
   If the script raises `Exception` or `BaseException`, the transaction performs
   after-state readback first. Catch `SceneDigestExecutionError` and pass its
   `cause`, snapshots, and `readback_error` to
   `ScriptExecutionResult.from_exception(...)`.
   A failed after-readback after a mutating script is explicitly
   `indeterminate=true` with `verified=false`; preserve the before snapshot and
   never retry it as if no side effect occurred.
   Core persists gateway-accepted feedback under
   `<registry_dir>/feedback/<dcc>-<pid>.jsonl` with bounded rotation and
   session-end syncing. Treat `feedback_persistence_failed` as a real degraded
   result; never add an adapter-local success fallback.
   - For native visual UI fallback, reuse the bundled `ui-control` skill with
     standalone `dcc-cua` 0.4.0 or newer; do not add adapter-local capture,
     accessibility, or raw-input wrappers. Keep stateful UI calls in one
     long-lived adapter process so each logical session retains its persistent
     CUA bridge and window capability. Preserve `capture_provenance` with
     evidence. The shared CUA Host owns platform accessibility, capture,
     banner/border/cursor markers, Escape interruption, input serialization,
     and recording. `ui-control` remains `requires_in_process: true` with
     `affinity: any`; register `HostExecutionBridge` before skill loading.
   - Keep structured DCC skills, host APIs, and adapter scripts ahead of
     `ui-control`. Agents should make an explicit, agent-directed transition into the scoped
     `snapshot` → one `act` → `snapshot` loop only when an operation is
     unsupported, no suitable tool exists, or semantic UI Automation cannot
     reach the required control. Re-observe after every action.
   - For native application menu bars, route an explicit `menu_path` through
     `ui_control__act(action="invoke_menu")` when semantic click or Alt-mnemonic
     delivery cannot prove that a Qt popup opened. Require the negotiated
     `native_menu_path` Host capability, honor `verification_required`, and
     re-observe the exact window before another mutation.
   - Raw pointer and keyboard input are enabled by default only inside the
     adapter/operator-bound DCC scope. Operators may set
     `DCC_MCP_CUA_ALLOW_RAW_INPUT=false` to disable that runtime ceiling; the
     adapter must not override this choice. Populate `DccServerOptions` with
     the adapter's DCC PID and, when available, its current window title or
     handle; Core injects that trusted scope into in-process `ui-control` calls.
     Dedicated servers may instead use `DCC_MCP_UI_CONTROL_PROCESS_ID` or
     `DCC_MCP_UI_CONTROL_WINDOW_HANDLE` operator overrides. Request scope may
     only narrow that trusted PID/HWND, including a title constraint for one
     window inside a multi-window process. Require a visible unlocked desktop
     and matching Windows integrity level, preserve the click-through
     border/banner/pointer feedback, and preserve
      `user_interrupted` without automatic retry, `session_id` changes, or fallback. Once Esc stops an
      session, only `ui_control__snapshot(resume_computer_use=true)` may request a
      resume, and the isolated host must still obtain trusted user confirmation
      before clearing the latch. Always call `ui_control__stop_computer_use` when
      the workflow ends.
      Never transition or retry through another UI/input path after a policy,
      authorization, authentication, security, confirmation,
      `desktop_unavailable`, or `user_interrupted` result.
      Keep mutating UI Control tools annotated as destructive. The optional
      `intent` may only raise the native host's independent UIA/input
      classification. Do not introduce a model-supplied `confirmed`/`approved`
      flag or environment bypass.
8. Use CLI profiles (`dcc-mcp-cli gateway ...`, `list/search/describe/call`) as the user UX; treat `dcc-mcp-server` modes as runtime plumbing. Read `docs/guide/gateway.md` before changing daemon, guardian, sentinel, registry, or idle-timeout behavior.
   Gateway discovery reuses a recent capability snapshot across adjacent
   queries. Route adapter catalog changes through the existing
   load/reload/unload contracts that force a refresh; never depend on every
   search polling the full backend catalog.
   `gateway://instances` is agent-safe by default and returns only live,
   routable rows. Use `?include_stale=true`, `?include_dead=true`, or
   `?view=all` only for explicit diagnosis; never route a call from those
   expanded operator views without re-validating live readiness.
   Once an instance is selected, reuse `gateway://instances/{instance_id}` or
   `GET /v1/instances/{instance_id}/context` for live process/machine
   performance, scene/documents, loaded skills, and canonical follow-up routes.
   These reads fetch the backend context on demand, but scene freshness remains
   adapter-owned: publish changes from a host event/main-thread callback with
   `DccServerBase.update_gateway_metadata(...)`, and publish rich snapshots with
   `set_scene_resource(...)`. Never claim scene awareness when the adapter has
   not installed a publisher; `scene=null` / `no_scene_published` is explicit.
   For agent observability, read `gateway://experiments/{experiment_id}` for
   runs, Session DAG links, metrics, and Judge evidence; read
   `gateway://governance` for the effective policy boundary. Keep Admin memory
   deletion controls out of agent-readable resources.
9. Use `dcc_mcp_core.deployment.build_sidecar_command(...)` / `launch_sidecar(...)` for library-driven sidecar startup and readiness. Installer subprocesses should use `dcc-mcp-install-lifecycle`; `dcc_mcp_core.install_lifecycle` and `python -m dcc_mcp_core.install_lifecycle` remain compatibility aliases. Read `docs/guide/adapter-install-lifecycle.md` before changing host RPC, dispatch readiness, launch stdio, `watch_pid`, or `instance_id` handling.
   - Adapter-owned lifecycle commands must follow `docs/guide/adapter-install-sop.md`. Consume `load_install_sop_schema()` and `INSTALL_EXIT_CODES` from `dcc_mcp_core.deployment`; do not invent adapter-local result shapes or exit-code mappings.
   - The sidecar MCP listener is dispatch-only. A py37-lite factory can expose local skill metadata, but it cannot advertise or activate declarative skills through the gateway. Require a native py37 wheel for that path, or provide a separate discovery MCP URL; never report lite `load_skill` success without an executable catalog.
   - Wrap the outer adapter import/start block with `capture_bootstrap_errors(...)`; it is stdlib-only, records pre-MCP failures, and re-raises for the DCC's native error UI. `DccServerBase` already captures Python error logs and uncaught exceptions into the shared log plus `output://` / `events://`. Forward host-native console callbacks with `server.report_host_error(...)`; do not replace global stdout/stderr or add an adapter-local error store.
   - For DCC-Link IPC upgrades, deploy readers that accept current version 1 and legacy version 0 before switching writers to the default versioned frame. Use `DccLinkFrame(..., version=0)` only during that compatibility window, preserve an incoming frame's version in its reply, and treat `unsupported DCC-Link protocol version` as an explicit peer-upgrade failure rather than retrying body decoding.
   - Preserve one caller-generated request id across every execution hop. JSON-RPC responses must echo `id`; commandPort-style sidecar responses must echo top-level `request_id`; gateway REST responses must echo `X-Request-ID`. Never replace an explicit response id with the current request id, because that can disguise a stale response. Treat a missing or mismatched echo as `transport desync`, fail closed, and regression-test a slow call followed by fast calls on the same connection.
   - Registry producers must write `ServiceEntry.schema_version` using `SERVICE_ENTRY_SCHEMA_VERSION`; rows with no field are legacy version 0. Consumers may read legacy/current rows but must reject a higher schema version without quarantining, deleting, or rewriting `services.json`. Treat that error as an explicit peer-upgrade requirement, not as corrupt JSON.
10. Pass `instance_id` to sidecar launch helpers only when it is a real UUID for the DCC service. During early startup, omit it or pass `None`; `build_sidecar_command()` rejects cosmetic values such as `"unknown"` with `success=false` and `reason="invalid_instance_id"` so adapters do not spawn a child that can only fail with a CLI argument error.
    After `DccServerBase.start()`, use `server.instance_id` when adapter UI or
    sidecar wiring needs the canonical FileRegistry identity. It is the exact
    registered UUID and is `None` before start, after stop, or when gateway
    registration is disabled/unavailable; never inspect private handles or
    generate a replacement UUID.
11. Adapter supervisors that must stop the sidecar on plugin unload should call `launch_sidecar(..., return_process=True, detached=False)` instead of reimplementing `subprocess.Popen`; keep `return_process=False` for CLI/JSON paths because the process handle is not serializable.
12. If the adapter cannot share the gateway `FileRegistry`, register remotely through `POST /v1/instances/register`, refresh with `/heartbeat`, and deregister on shutdown; the gateway will expose the row as `source: "http"` in `gateway://instances` / `GET /v1/instances`, preserve `instance_short` and `mcp_url`, and route it through the same `live_instances` contract.
    Remote registrations are untrusted input: health and capability refresh
    only use policy-allowed, identity-matching HTTP(S) endpoints with no
    query credentials or URL userinfo; redirects are not followed, and
    private/link-local targets (including IPv4-mapped IPv6 literals) and DNS
    names are rejected for periodic outbound probes. Gateway health and
    reliability totals count only registrations accepted by that same dispatch
    predicate; rejected registrations are reported separately and cannot
    shadow a safe backend during DCC-type routing. Public literal IPv6
    registrations keep an unbracketed canonical host identity; brackets belong
    only to serialized URLs. Adapters must not copy a bracketed URL host into
    `ServiceEntry.host` or compare raw URL text across discovery and dispatch.
13. Keep the gateway's secondary listener on its default loopback host. Opt into LAN access only with an explicit `--remote-host 0.0.0.0` or concrete LAN IP; for same-LAN convenience discovery, build with `mdns` and pair adapter-side `--advertise-mdns` with gateway-side `--discover-mdns`. Treat mDNS as a multicast discovery hint only, keep auth/TLS policy explicit, and prefer HTTP registration or relay for routed/subnet-crossing production deployments.
14. For NAT or routed-subnet deployments, run the tunnel agent with stable `instance_id`, `capabilities_fingerprint`, `adapter_version`, and `scene` metadata, then configure the standalone gateway with `--relay-source ADMIN_URL=PUBLIC_BASE_URL`; the gateway will expose active tunnels as `source: "relay"` rows with relay details in `source_meta` after probing `/v1/healthz` through `<PUBLIC_BASE_URL>/tunnel/<tunnel_id>/mcp`.
15. Preserve gateway caller attribution when adding adapter wrappers or admin/debug routes: let legacy MCP `initialize.params.clientInfo`, MCP `_meta.agent_context`, REST `meta.agent_context`, `x-dcc-mcp-*` headers, and safe `User-Agent` fallbacks flow through core rather than logging raw prompts or local machine data.
    The opt-in MCP 2026 path uses `server/discover` and namespaced per-request
    metadata instead of a legacy initialize session. Consume Core's shared
    protocol types and routing; do not copy wire envelopes into adapters or
    Skills. Keep CLI+REST as the agent default. Before enabling a new protocol,
    follow the [protocol compatibility gates](TESTING_AND_RELEASE.md#protocol-compatibility-gates)
    against the exact installed artifact; a version label alone is insufficient.
16. For lifecycle/memory/telemetry policy, use `register_lifecycle_hooks(...)`, `search_skills(..., session_id=...)`, `dispatch_session_start(...)`, `dispatch_before_tool_call(...)`, `dispatch_after_tool_call(...)`, and `dispatch_session_end(...)`; pair `MemoryRecorder(InMemoryMemoryStore()).install(hooks)` with those hooks when adapters need bounded memory summaries, failed-pattern avoidance, or session compaction. Memory injection is conservative and budgeted by default: search receives compact ranking hints, tool calls receive memory only when it matches the current `tool_name`, and session-start injection is opt-in. Use `SqliteMemoryStore()` only when longterm patterns should be durable, operator-managed in the Admin Memory tab, and included in memory hit-rate observability; disable the recorder for privacy-sensitive deployments. Open a focused core issue/RFC only when those public hooks cannot express the adapter boundary.
17. Add one executable smoke path: unit tests for construction plus either headless DCC, mock dispatcher MCP calls, gateway REST replay, mDNS same-LAN discovery smoke, relay-source smoke, the open-source MCP Inspector for a loopback internal service, or `just idle-memory-smoke` for standalone server idle/regression checks.
18. For gateway/admin observability, surface explicit state instead of silent zeroes: traffic panels should report disabled, unavailable, filtered, or genuine no-traffic states; skill panels should distinguish discovered, loaded, searched, selected, called, failed, and low-adoption skills; and admin-facing frames/paths should stay metadata-only or aliased unless an operator explicitly configures a private raw sink. Keep `ServiceEntry.version` as the DCC application version; use core-published `dcc_mcp_server_version` and `dcc_mcp_instance_type=gui|standalone` metadata for server regression and runtime-shape diagnostics instead of overloading DCC or adapter versions.
19. Preserve workflow observability: adapter calls should carry request, parent, trace, session, DCC, transport, and artifact/validation metadata so the Admin workflow graph can show Intent → Discovery → Skill Load → Tool Calls → Fallbacks → Artifacts → Validation → Report without raw log reading.
20. Preserve bounded `agent_context` task/session/turn metadata and artifact/validation-friendly tool names so Admin task outcomes can group workflows, calls, deliverables, and checks without reading raw payloads or local paths.
21. Preserve record-replay ownership boundaries: forward server-derived
    `agent_context.session_id`, keep UI Control logical ids connection/caller
    scoped, and write only redacted recording projections to existing
    `session_events`. Do not add adapter-local recorder state, a second
    database, or a replay authority flag. Persist calls incrementally; after a
    gateway restart, project unfinished recordings as `interrupted` without
    restoring capture authority. Generated workflows re-resolve current tools
    and schemas; semantic UI replay resolves fresh control ids; raw/visual
    fallback requires exact-window calibration and drift guards.
22. Record reproducible experiment definitions, run states, Session DAG links,
    metrics, and judge evidence through the gateway `/v1/experiments` APIs.
    Reuse `session_events`, workflow/recording identifiers, and artifact
    references; do not add adapter-local experiment storage or treat judge
    output as approval authority.

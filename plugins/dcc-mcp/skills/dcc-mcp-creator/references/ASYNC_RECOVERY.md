## Chunked Main-Thread Jobs

Use the shared chunked path when a main-affinity operation cannot finish within
one host UI tick. The adapter owns scheduling; skill code only defines bounded
steps:

```python
from dcc_mcp_core import chunked_job

@chunked_job(total=100)
def bake_frames():
    for frame in range(100):
        yield lambda frame=frame: bake_one_frame(frame)

# A declarative in-process tool returns this runner. HostExecutionBridge
# detects and submits it to HostUiDispatcherBase automatically.
return bake_frames()
```

- Declare `execution: async`, `affinity: main`, and
  `job_strategy: chunked`. The bridge rejects a declared chunked tool that
  returns a monolithic value.
- Any operation that can exceed the caller's synchronous timeout must return a
  job envelope. Declare `execution: async` and provide a realistic positive
  `timeout_hint_secs`; Core routes the execution declaration through
  `JobManager`. A timeout hint only sizes client/runtime budgets and never
  promotes an `execution: sync` tool to an async job.
- Yield one bounded host-API callable per step. A returned string becomes the
  progress message.
- `submit_chunked_runner()` advances at most one step per host pump tick, so
  unrelated UI work can run between steps.
- `cancel(request_id)` requests cancellation. The runner publishes
  `cancelled` only after the next checkpoint observes it; a running native DCC
  call or monolithic callback is not pre-empted.
- Do not add adapter-local generator pumps, timer loops, worker threads, or a
  second job registry.
- Test pending cancellation, cancellation during a step, monotonic progress,
  failure, exactly one terminal result, unrelated pump work, and at least two
  host labels.

Do not label an indivisible native call as chunked. Use
`job_strategy: monolithic` when the host API cannot yield, or
`job_strategy: isolated` when a process/service-owned operation can return a
durable job id. Isolated status must remain queryable after transport loss;
cancellation may remain process-owner scoped when reconstructing ownership
would be unsafe.

## Liveness and Crash Recovery

- Keep registry heartbeat and HTTP readiness independent of the DCC main
  thread. A readiness/transport timeout marks the instance `unreachable`; it
  must not erase a row whose owner lock/PID or remote TTL is still valid.
- Keep HTTP body limits, trusted-proxy depth, and request-rate windows on the
  owning `GatewayState` (`GatewayIngressState`). Embedded adapters may host
  more than one gateway in a process, so process-global lazy counters or env
  snapshots are not a valid isolation boundary.
- Keep backend retry policy and circuit observations on the same owning
  `GatewayState` through `GatewayResilienceState`. Pass that state through
  backend discovery and dispatch calls; never use a process-global circuit
  table, because one embedded gateway must not open another gateway's backend.
- Pass the complete `McpHttpConfig.features` snapshot into HTTP runtime state
  with `ServerStateBuilder::with_features`. Do not copy capability booleans
  into loose `ServerState` fields; config and runtime routing must read the
  same `FeatureFlags` source.
- In Rust async gateway/adapter code, share `Arc<FileRegistry>` directly and
  call its `*_async` methods. `FileRegistry` is already internally synchronized;
  an outer `RwLock` adds no safety and holding an async guard across its
  flock/fsync transaction blocks the runtime.
- Treat owner lock/PID death or remote TTL expiry as crash evidence. After a
  crash, the adapter cannot reconnect until the DCC or sidecar starts again.
- Preserve stable `dcc_type`, scene/project metadata, and adapter identity so
  agents can rediscover a replacement instance. Never reuse an old tool slug
  or direct MCP URL after the instance id changes.
- Enable core job persistence. On restart, in-flight core jobs become
  `interrupted` and remain queryable through the replacement instance's
  `jobs_get_status`; adapter-owned isolated jobs need their own durable status
  tool when they outlive the request transport. If the worker can outlive the
  DCC/sidecar process, that status tool must be owned by the worker/service or
  another independently live control process; gateway restart alone cannot
  recreate an API whose owner exited.


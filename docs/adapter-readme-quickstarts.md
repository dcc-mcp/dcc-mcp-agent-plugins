# Maintaining adapter README quickstarts

Each released DCC-MCP adapter README should expose a short, searchable path from
the adapter to the official Agent Skill. Installation truth remains in this
repository. Adapter repositories commit only the generated block between:

```html
<!-- dcc-mcp-agent-quickstart:start -->
<!-- dcc-mcp-agent-quickstart:end -->
```

Do not hand-edit text inside these markers. Update the central template or
registry here, then roll the generated result out to adapters.

## Add or update an adapter

Add the repository name, public DCC name, exact `dcc_type`, and a read-only
smoke prompt to
[`adapter-readme-quickstarts.json`](../.github/adapter-readme-quickstarts.json).
The smoke prompt must match a released route; do not advertise planned or
unreleased support.

From a checkout of this repository, update an adapter README:

```powershell
python scripts/sync_adapter_readme.py `
  --repository dcc-mcp-blender `
  --readme G:\path\to\dcc-mcp-blender\README.md `
  --write
```

The first run inserts the block before the README's first `##` heading. Move the
whole marked block once if the repository needs a different prominent location.
Later runs replace only the marked block.

Review the generated diff in the adapter repository. Keep adapter-specific host
installation and enablement instructions outside the generated block.

## Prevent drift in adapter CI

Pin this repository to a reviewed commit and check out both repositories. Do
not consume a moving branch in required CI.

```yaml
- uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803 # v6
- uses: actions/checkout@d23441a48e516b6c34aea4fa41551a30e30af803 # v6
  with:
    repository: dcc-mcp/dcc-mcp-agent-plugins
    ref: <reviewed-agent-plugins-commit>
    path: .agent-plugins
- run: >-
    python .agent-plugins/scripts/sync_adapter_readme.py
    --repository ${{ github.event.repository.name }}
    --readme README.md
    --check
```

When the central template changes, update the pinned commit and generated block
in the same adapter PR. A stale or missing block makes `--check` exit nonzero.

## Rollout order

1. Land and release the central template, registry, sync script, and tests here.
2. Roll out adapter PRs in bounded batches, starting with high-traffic released
   adapters.
3. In every adapter PR, run `--write`, review the README diff, add the pinned CI
   check, and run that repository's required tests.
4. Add remaining released adapters to the registry only when their exact
   `dcc_type` and first smoke prompt are verified.

The generator does not modify another repository unless a maintainer explicitly
runs it with `--write`. This keeps cross-repository publication reviewable and
prevents this repository from silently mutating adapter defaults.

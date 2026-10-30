# Source and scope notes

Inspected 2026-10-30 through public HTTPS metadata only. Refresh these facts before
use: no immutable provider revision or signed asset receipt was established.

- [API](https://polyfork.dev/api): public catalog/schema and coordinate conventions.
- [Agent setup](https://polyfork.dev/agents): existing remote MCP; this prototype adds
  no client configuration, SDK, persistent access, key or catalog server.
- [Hosted guide](https://polyfork.dev/prompt.txt): catalog/scene operating guidance,
  not an openly licensed library of reusable prompt text. No guide body is vendored.
- [Standard terms](https://polyfork.dev/licensing): project use differs from standalone
  asset redistribution. Free low-poly per-user provider links differ from mirrors,
  proxy services or serving HD content. Recheck the use and entitlement separately.
- [Platform terms](https://polyfork.dev/platform): separate hosting rights still do
  not grant standalone resale or generator training/evaluation/benchmark rights.

One compact `camper` search returned `camper-van-8d10e2`. Its
[detail metadata](https://polyfork.dev/api/assets/camper-van-8d10e2) declared a free
low-poly candidate, size X/Y/Z = 2.2/2.22/4.68 meters, 3971 triangles and origin_y 0.
Its [parameter metadata](https://polyfork.dev/cdn/camper-van-8d10e2-params.json)
declared `colorway`, `lower`, `stripe`, and `popTop`; no overrides are selected here.
The asset declared `has_night: false`; no provider rain/night knob is assumed.
Rain, task lights and camera intent are original scene staging.
No model, source module, render, kit archive or variant bake was downloaded or run.
The recipe stores a few factual selection fields, not the provider's description,
parameter documentation, palette, source code or a copy of its catalog.

The repair-bay layout and materials below are authored for this prototype. The
placeholder only reserves space; its dimensions do not establish the actual
vehicle's import fidelity, rig behavior or suitability for a rainy-night scene.
No real DCC, artifact export/reopen, native acceptance or scene render was run.

The blockout boxes use centered origins. In particular, CamperSlot at Y=1.11
is the center of its placeholder box, not the ground-origin transform of the
provider vehicle. Recompute placement from live origin/terrain metadata if an
authorized actual asset replaces it; do not copy the placeholder transform.

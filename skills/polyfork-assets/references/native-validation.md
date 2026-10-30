# Single-asset acquisition and native reuse receipt

Checked 2026-10-30 after user authorization for one public free item and private,
reversible acceptance. This is a background Blender test, not a GUI or rendered
showcase test. No existing DCC scene was changed and no MCP access was installed.

- Item: `camper-van-8d10e2`, anonymous metadata declared free/price 0/auth none.
- Official file: https://polyfork.dev/cdn/camper-van-8d10e2.glb
- Terms: https://polyfork.dev/licensing (custom project-use terms, not open source).
- Download size: **353304 bytes**.
- Download SHA-256: `8845c46ed227178aa303c2ee9ef4a1ef9633b5917175eaef2901b380dcf9c107`.
- Provider published date: `2026-07-24 13:05:48`; no immutable provider revision
  was returned. The local content hash is the version pin.
- First helper fetch: 2 HTTP requests (metadata + GLB), 1 asset download.
- Repeat helper fetch: cache hit, **0 HTTP requests / 0 asset downloads**, same SHA.
  A subsequent independent background import reused those same cached bytes.

## Actual Blender readback

Blender **5.1.1**, build `b70da489d7f4`, factory-startup background process with
Python autoexec disabled. Native glTF import, private .blend save, GLB export,
new empty scene and reimport of that export all ran successfully.

- Imported meshes: **5**; triangles: **3971**; materials: **1**.
- Actual Blender X/Y/Z world dimensions: approximately
  **2.205 / 4.682319 / 2.220415 meters**.
- Rounded catalog X/Y/Z dimensions were 2.2/2.22/4.68 in Y-up. The measured
  Z-up conversion and ground origin pass the stated 0.02m catalog tolerance.
- Export/reopen bounds, triangle count, hierarchy, named material assignments,
  linear base colors and per-object vertex-color palette hashes all matched.
  Roundtrip dimension tolerance was 0.0001m.
- Export SHA-256: `2dc0a9bb815388fe04996c2e539f1e76d08d22a853e5e46283c3017207082e82`.

The initial geometry/material check passed in two separate background processes.
A later vertex-palette extension first failed from a local variable-shadowing bug;
its private artifacts and failed process output were preserved. Correcting the
helper produced the successful full palette-inclusive native receipt above.
No asset bytes were changed or downloaded again to make the check pass.

Raw models, .blend files, roundtrip GLBs, local paths and full native receipts
remain in the private ignored project, never in this Skill or release packages.
This document contains only a sanitized factual summary, not asset geometry,
module code, provider imagery, a generator benchmark or a PoseAtlas dataset.
It does not prove another DCC, animation, GUI operation or repair-bay render.

---
name: dcc-tree-workflow
description: >-
  Coordinate reference-guided procedural tree creation and verification across SpeedTree and Blender using DCC-MCP. Use when a task requires an editable SpeedTree candidate, measured geometry and cross-host visual review; use individual host tools for a single-host task.
license: MIT-0
allowed-tools: Bash Read Write
metadata:
  dcc-mcp:
    dcc: python
    layer: domain
    version: "0.19.122"
    search-hint: "SpeedTree Blender reference tree production validation silhouette tree foliage card geometry 跨软件 树木 树叶 面数 参考图"
    tags: "speedtree, blender, tree, reference, cross-dcc, verification"
---

# Reference-guided tree workflow

Use DCC-MCP to coordinate independently owned host capabilities. The SpeedTree
adapter owns editable graph operations, Modeler exports and SpeedTree-specific
checks. Blender owns its imports, materials and diagnostic rendering. This skill
is agent-facing guidance; it is not an executable cross-host optimizer.

## Discover and establish the contract

Use the installed `dcc-mcp` skill's gateway discovery and production-reuse
guidance. Discover SpeedTree and Blender instances separately; select each exact
instance and inspect the available tool schemas before calls. Discovery of a
host, installation or a skill name is not proof that a tool is callable. Do not
invent commands or launch one host from the other adapter. If the necessary host,
tool, file, mapping or compatible units is unavailable, report that gap and
continue only independent work. Preserve the user's existing scene and source.

Record the user's reference images, candidate/source identity, output needs,
and explicit geometry, species, style, scale and visual criteria. Triangle
budgets are user parameters, not universal defaults. For example, if the user
specifies an entire tree of at most 2,000 triangles and exactly 800 triangles
for leaf cards plus twig cards combined, validate those as two distinct rules:
`total_triangles <= 2000` and `leaf_card_triangles + twig_card_triangles ==
800`. Do not change equality into an upper bound, count cards as triangles, or
exclude twigs without authorization. Do not invent absent category mappings.

Keep a task-local artifact manifest, updated at each handoff. It should record:

- Source and candidate paths plus SHA-256, actual host/version and instance;
  export path, format, SHA-256 and the corresponding candidate identity.
- Required dependency paths, roles and SHA-256; reference image identity/hash
  and use rights where relevant. Missing dependencies remain explicit.
- Export and target-import units and axes, documented conversions and measured
  target bounds; use `unknown` when unavailable. Never infer meters from a
  label or assume the exported scale is the target scale.
- Explicit generator or material-to-category mappings and coverage for trunk,
  branches, leaf cards and twig cards, including evidence and unmapped elements;
  independently measured full-tree and category triangle counts and their rules.
- Reference view correspondence and actual camera transforms, projection,
  frame/orthographic scale, resolution, background, lighting and render settings;
  preview, mask and report paths/hashes, with the producing tool and version.

Distinguish observed, declared, missing and unverified evidence. Check hashes
before downstream use; stop the dependent step on mismatch rather than using a
stale export. Paths alone, thumbnails, cached triangle statistics or a reported
successful export do not establish the final geometry or appearance.

## Author, inspect and review

1. In SpeedTree, inspect the actual graph and properties. Use supported typed
   graph operations to produce a separate editable candidate, preserving the
   original. Regenerate/export via the official Modeler tool and record export
   receipt and dependencies. Use SpeedTree-owned geometry/structure checks if
   available; if category accounting is incomplete, report it instead of
   estimating from the generator graph. Graph generators are not generated
   branch-instance counts.
2. Through the gateway, use the selected Blender instance's discovered import,
   material and rendering tools on an isolated scene or approved copy. Verify
   imported model size, axis, triangle count and textures. Record the measured
   per-category counts only when the mapping covers the whole relevant mesh and
   the tools can actually distinguish leaf and twig cards. Inspect material
   alpha behavior in the target host; a linked image alone does not prove a
   correct render.
3. Reproduce the specified fixed-camera views and any requested full/bare,
   mask, wire or card close-up diagnostics using Blender-owned capabilities.
   Record exact views and hashes in the manifest. Existing multiview tools may
   provide beauty/wire but must not be represented as providing category masks
   or automatic visual matching unless their actual schemas and outputs do so.
4. Compare results against the reference, keeping numerical evidence separate
   from visual judgment. Image comparison or parameter fitting requires a
   separately discovered cross-host capability; do not claim automated fitting,
   a global optimum or a passed visual review if it is unavailable. Revise the
   candidate when possible, and request human artistic review for acceptance.

Deliver the editable source and requested exports/diagnostics with their
manifest, observed measurements, unmet checks and remaining host-specific
limitations. State whether the user has accepted the visual result; a render,
automated score or passing geometry budget is not that acceptance.

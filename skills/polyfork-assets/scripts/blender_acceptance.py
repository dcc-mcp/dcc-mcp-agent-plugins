"""Private native acceptance in a fresh, background, autoexec-disabled Blender."""

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import sys

import bpy
from mathutils import Vector


def capture():
    """Read actual world bounds, geometry, materials and hierarchy from Blender."""
    meshes = [obj for obj in bpy.context.scene.objects if obj.type == "MESH"]
    if not meshes:
        raise ValueError("import produced no meshes")
    corners = [obj.matrix_world @ Vector(corner) for obj in meshes for corner in obj.bound_box]
    minimum = [min(point[i] for point in corners) for i in range(3)]
    maximum = [max(point[i] for point in corners) for i in range(3)]
    triangles = 0
    for obj in meshes:
        obj.data.calc_loop_triangles()
        triangles += len(obj.data.loop_triangles)
    material_colors = {}
    for material in bpy.data.materials:
        color = list(material.diffuse_color)
        if material.use_nodes:
            principled = next((node for node in material.node_tree.nodes if node.type == "BSDF_PRINCIPLED"), None)
            if principled is not None:
                color = list(principled.inputs["Base Color"].default_value)
        material_colors[material.name] = color
    palettes = {}
    for obj in meshes:
        palettes[obj.name] = {}
        for attribute in obj.data.color_attributes:
            palette_values = sorted({tuple(round(value, 6) for value in item.color) for item in attribute.data})
            palettes[obj.name][attribute.name] = hashlib.sha256(json.dumps(palette_values).encode()).hexdigest()
    return {
        "mesh_objects": len(meshes), "triangles": triangles,
        "world_size_m": [maximum[i] - minimum[i] for i in range(3)],
        "world_min_m": minimum, "world_max_m": maximum,
        "hierarchy": {obj.name: obj.parent.name if obj.parent else None for obj in bpy.context.scene.objects},
        "materials": material_colors, "vertex_color_palette_sha256": palettes,
        "assignments": {obj.name: [slot.material.name if slot.material else None for slot in obj.material_slots] for obj in meshes},
    }


def close_vector(a, b, tolerance=0.02):
    """Use a metric tolerance while rejecting nonfinite native measurements."""
    return len(a) == len(b) and all(math.isfinite(x) and math.isfinite(y) and abs(x - y) <= tolerance for x, y in zip(a, b))


def main():
    """Import and reopen only within a new private output directory."""
    if not bpy.app.background or "--factory-startup" not in sys.argv or "--disable-autoexec" not in sys.argv:
        raise ValueError("requires a fresh background Blender with factory startup and autoexec disabled")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset", type=Path)
    parser.add_argument("--metadata-json", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
    source = args.asset.resolve(strict=True)
    output = args.output_dir.resolve()
    skill = Path(__file__).resolve().parents[1]
    if output == skill or skill in output.parents or output.exists():
        raise ValueError("output must be a new private project directory outside the Skill")
    metadata = json.loads(args.metadata_json.read_text(encoding="utf-8"))
    output.mkdir(parents=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    bpy.ops.import_scene.gltf(filepath=str(source))
    before = capture()
    bpy.ops.wm.save_as_mainfile(filepath=str(output / "private-project.blend"))
    exported = output / "private-roundtrip.glb"
    bpy.ops.export_scene.gltf(filepath=str(exported), export_format="GLB", export_yup=True)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.scene.unit_settings.system = "METRIC"
    bpy.context.scene.unit_settings.scale_length = 1.0
    bpy.ops.import_scene.gltf(filepath=str(exported))
    after = capture()
    declared = metadata["size_m"]
    expected = [declared["x"], declared["z"], declared["y"]]
    checks = {
        "catalog_dimensions_y_to_z": close_vector(before["world_size_m"], expected),
        "catalog_triangle_count": before["triangles"] == metadata["triangles"],
        "catalog_origin_y_to_z": abs(before["world_min_m"][2] - metadata["origin_y"]) <= 0.02,
        "roundtrip_dimensions": close_vector(before["world_size_m"], after["world_size_m"], 0.0001),
        "roundtrip_triangle_count": before["triangles"] == after["triangles"],
        "roundtrip_hierarchy": before["hierarchy"] == after["hierarchy"],
        "roundtrip_assignments": before["assignments"] == after["assignments"],
        "roundtrip_vertex_color_palettes": before["vertex_color_palette_sha256"] == after["vertex_color_palette_sha256"],
        "roundtrip_material_colors": before["materials"].keys() == after["materials"].keys() and all(
            close_vector(color, after["materials"][name], 0.0001) for name, color in before["materials"].items()),
    }
    receipt = {
        "status": "native_import_reopen_pass" if all(checks.values()) else "native_import_reopen_failed",
        "asset_id": metadata["id"], "input_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "export_sha256": hashlib.sha256(exported.read_bytes()).hexdigest(),
        "host": {"version": bpy.app.version_string, "pid": os.getpid(), "background": bpy.app.background},
        "import": before, "reopen": after, "checks": checks, "gui_acceptance": "not_run",
    }
    (output / "native-readback.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
    print(json.dumps({"status": receipt["status"], "host": receipt["host"], "checks": checks}))
    if not all(checks.values()):
        raise RuntimeError("native readback failed; preserve receipt and artifacts")


if __name__ == "__main__":
    main()

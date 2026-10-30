"""Compare world-space readback JSON; never attest a real DCC or license grant.

Readback: schema_version=1, stage=export_reopen, format, meters_per_unit,
up_axis, handedness, materials (name -> linear RGBA), objects (name, parent,
size and position in target units, material). The source may be a synthetic
fixture or a host report; neither label is independently authenticated here.
"""

import argparse
import json
import math
from pathlib import Path


def vector(value, length):
    """Reject malformed or non-finite measurement vectors, including booleans."""
    if not isinstance(value, list) or len(value) != length or any(
        type(number) not in (int, float) or not math.isfinite(number) for number in value
    ):
        raise ValueError("invalid measurement vector")
    return value


def objects_by_name(value):
    """Require unambiguous objects before comparing hierarchy or measurements."""
    if not isinstance(value, list) or not value:
        raise ValueError("objects must be a nonempty list")
    result = {}
    for item in value:
        if not isinstance(item, dict) or not isinstance(item.get("name"), str) or not item["name"]:
            raise ValueError("object needs a name")
        if item["name"] in result or item["name"] == "SceneRoot":
            raise ValueError("duplicate or reserved object name")
        result[item["name"]] = item
    for name in result:
        seen = set()
        while name != "SceneRoot":
            if name in seen or name not in result:
                raise ValueError("broken or cyclic hierarchy")
            seen.add(name)
            name = result[name].get("parent")
    return result


def check_readback(plan, readback):
    """Validate this prototype's coordinate contract and compare supplied values."""
    if any(type(value.get("schema_version")) is not int or value["schema_version"] != 1
           for value in (plan, readback)):
        raise ValueError("unsupported schema version")
    if any(plan["scene"].get(key) != value for key, value in
           {"units": "m", "up_axis": "Y", "handedness": "right", "front": "+Z"}.items()):
        raise ValueError("plan must use the declared meter/Y-up/right-handed basis")
    target = plan["target"]
    unit = target["meters_per_unit"]
    if any(type(value) not in (int, float) or not math.isfinite(value) or value <= 0
           for value in (unit, readback.get("meters_per_unit"))):
        raise ValueError("invalid target unit scale")
    if target["up_axis"] not in ("Y", "Z") or target["handedness"] != "right":
        raise ValueError("unsupported target basis")
    if any(readback.get(key) != target[key] for key in ("up_axis", "handedness", "meters_per_unit")):
        raise ValueError("readback basis differs from target")
    if readback.get("stage") != "export_reopen" or readback.get("format") != plan["acceptance"]["export_format"]:
        raise ValueError("export-reopen measurements required")
    expected = objects_by_name(plan["objects"])
    observed = objects_by_name(readback["objects"])
    if expected.keys() != observed.keys():
        raise ValueError("object inventory differs")
    tolerance = plan["acceptance"]["dimension_tolerance_m"]
    if type(tolerance) not in (int, float) or not math.isfinite(tolerance) or not 0 < tolerance <= 0.05:
        raise ValueError("invalid metric tolerance")
    if not isinstance(plan["materials"], dict) or not isinstance(readback["materials"], dict):
        raise ValueError("materials must be named linear RGBA values")
    if plan["materials"].keys() != readback["materials"].keys():
        raise ValueError("material inventory differs")
    for name, color in plan["materials"].items():
        color = vector(color, 4)
        actual = vector(readback["materials"][name], 4)
        if any(not 0 <= value <= 1 for value in color + actual) or any(
            abs(a - b) > 0.0001 for a, b in zip(color, actual)
        ):
            raise ValueError("linear base color differs")
    for name, item in expected.items():
        actual = observed[name]
        if item["parent"] != actual["parent"] or item["material"] != actual["material"]:
            raise ValueError("parent or material assignment differs")
        if item["material"] not in plan["materials"]:
            raise ValueError("unresolved material")
        for source, destination in (("size_m", "size"), ("position_m", "position")):
            values = vector(item[source], 3)
            measured = vector(actual[destination], 3)
            if source == "size_m" and any(value <= 0 for value in values + measured):
                raise ValueError("dimensions must be positive")
            if target["up_axis"] == "Z":
                x, y, z = values
                values = [x, z, y] if source == "size_m" else [x, -z, y]
            if any(abs(a / unit - b) > tolerance / unit for a, b in zip(values, measured)):
                raise ValueError("world-space dimension or placement differs")
    return {"status": "offline_comparison_pass", "objects_checked": len(expected),
            "native_acceptance": "not_established"}


def main():
    """Read only the two explicit JSON inputs and return a machine-readable result."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("readback", type=Path)
    args = parser.parse_args()
    try:
        plan = json.loads(args.plan.read_text(encoding="utf-8"))
        readback = json.loads(args.readback.read_text(encoding="utf-8"))
        result = check_readback(plan, readback)
    except (OSError, ValueError, KeyError, TypeError, AttributeError, RecursionError):
        print(json.dumps({"status": "invalid_or_mismatched_readback", "native_acceptance": "not_established"}))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

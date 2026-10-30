"""Offline contracts for an original prototype; no vendor payload or DCC runs."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
import yaml
from zipfile import ZipFile

from scripts.package_openclaw_skill import package_skill
from scripts.publication_manifest import load_canonical_manifest

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills/polyfork-assets"
SCRIPT = SKILL / "scripts/check_readback.py"
spec = importlib.util.spec_from_file_location("polyfork_readback", SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class PolyforkPrototypeTests(unittest.TestCase):
    def setUp(self):
        """Load only our original recipe and synthetic measurements."""
        self.plan = json.loads((SKILL / "references/scene-plan.json").read_text(encoding="utf-8"))
        self.readback = json.loads((SKILL / "references/readback-fixture.json").read_text(encoding="utf-8"))

    def test_asymmetric_y_to_z_axes_match_without_native_claim(self):
        """The fixture distinguishes height/depth and changes world-position signs."""
        self.assertEqual(
            checker.check_readback(self.plan, self.readback),
            {"status": "offline_comparison_pass", "objects_checked": 4,
             "native_acceptance": "not_established"},
        )
        self.assertEqual(self.readback["evidence_source"], "synthetic_fixture")
        self.readback["native_acceptance"] = "pass"
        self.assertEqual(checker.check_readback(self.plan, self.readback)["native_acceptance"], "not_established")

    def test_centimeters_require_scaled_world_measurements(self):
        """Changing a units label cannot hide a hundredfold size error."""
        self.plan["target"]["meters_per_unit"] = 0.01
        self.readback["meters_per_unit"] = 0.01
        with self.assertRaises(ValueError):
            checker.check_readback(self.plan, self.readback)
        for item in self.readback["objects"]:
            item["size"] = [value * 100 for value in item["size"]]
            item["position"] = [value * 100 for value in item["position"]]
        self.assertEqual(checker.check_readback(self.plan, self.readback)["status"], "offline_comparison_pass")

    def test_y_up_target_preserves_original_coordinates(self):
        """Already converted imports must not receive a second rotation."""
        self.plan["target"]["up_axis"] = self.readback["up_axis"] = "Y"
        for item, expected in zip(self.readback["objects"], self.plan["objects"]):
            item["size"] = expected["size_m"]
            item["position"] = expected["position_m"]
        checker.check_readback(self.plan, self.readback)

    def test_mismatched_axes_handedness_or_stage_fail(self):
        """Export success without reopening cannot establish readback evidence."""
        for key, value in (("up_axis", "Y"), ("handedness", "left"),
                           ("stage", "export_only"), ("format", "fbx")):
            with self.subTest(key=key):
                observed = deepcopy(self.readback)
                observed[key] = value
                with self.assertRaises(ValueError):
                    checker.check_readback(self.plan, observed)

    def test_boolean_schema_and_unit_markers_are_not_numbers(self):
        """Python equality must not accept true as schema 1 or one meter."""
        for key in ("schema_version", "meters_per_unit"):
            with self.subTest(key=key):
                observed = deepcopy(self.readback)
                observed[key] = True
                with self.assertRaises(ValueError):
                    checker.check_readback(self.plan, observed)

    def test_bad_dimensions_placement_and_numeric_values_fail(self):
        """Catch nonfinite values and unit/axis errors in either vector."""
        for field, value in (("size", [6, 0.2, 5]), ("position", [0, 3.6, 0]),
                             ("size", [0, 5, 0.2]), ("position", [float("nan"), 0, 0]),
                             ("size", [True, 5, 0.2]), ("position", [float("inf"), 0, 0])):
            with self.subTest(field=field, value=value):
                observed = deepcopy(self.readback)
                observed["objects"][0][field] = value
                with self.assertRaises(ValueError):
                    checker.check_readback(self.plan, observed)

    def test_material_colors_assignments_and_inventory_fail(self):
        """Names alone do not prove that palette and material binding survived."""
        for change in ("color", "assignment", "inventory"):
            with self.subTest(change=change):
                observed = deepcopy(self.readback)
                if change == "color":
                    observed["materials"]["WetAsphalt"] = [1, 0, 0, 1]
                elif change == "assignment":
                    observed["objects"][0]["material"] = "WetAsphalt"
                else:
                    del observed["materials"]["WetAsphalt"]
                with self.assertRaises(ValueError):
                    checker.check_readback(self.plan, observed)

    def test_duplicate_missing_and_cyclic_objects_fail(self):
        """Do not conceal hierarchy loss behind ambiguous object names."""
        for change in ("duplicate", "missing", "cycle", "orphan"):
            with self.subTest(change=change):
                observed = deepcopy(self.readback)
                if change == "duplicate":
                    observed["objects"].append(deepcopy(observed["objects"][0]))
                elif change == "missing":
                    observed["objects"].pop()
                elif change == "cycle":
                    observed["objects"][0]["parent"] = "ServiceCanopy"
                else:
                    observed["objects"][0]["parent"] = "UnknownRoot"
                with self.assertRaises(ValueError):
                    checker.check_readback(self.plan, observed)

    def test_cli_reports_invalid_json_without_dumping_input(self):
        """Malformed local input fails without echoing caller data."""
        with TemporaryDirectory() as temporary:
            bad = Path(temporary) / "bad.json"
            bad.write_text("credential-fixture{", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(SCRIPT), str(SKILL / "references/scene-plan.json"), str(bad)],
                capture_output=True, text=True, check=False,
            )
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["status"], "invalid_or_mismatched_readback")
        self.assertNotIn("credential-fixture", result.stdout + result.stderr)

    def test_optional_skill_is_separate_from_the_four_skill_release_suite(self):
        """Prototype code/instructions may be packaged locally without shipping vendor files."""
        metadata = yaml.safe_load((SKILL / "SKILL.md").read_text(encoding="utf-8").split("---", 2)[1])
        self.assertEqual(metadata["name"], "polyfork-assets")
        self.assertEqual(SKILL.parent, ROOT / "skills")
        entries = load_canonical_manifest(ROOT)
        self.assertEqual(4, len(entries))
        self.assertNotIn("polyfork-assets", {entry["slug"] for entry in entries})
        self.assertEqual((SKILL / "LICENSE").read_text(encoding="utf-8").split(),
                         (ROOT / "LICENSE").read_text(encoding="utf-8").split())
        with TemporaryDirectory() as temporary:
            archive = package_skill(SKILL, Path(temporary), "0.0.0")
            with ZipFile(archive) as zipped:
                self.assertEqual((SKILL / "SKILL.md").read_bytes(), zipped.read("polyfork-assets/SKILL.md"))
                self.assertFalse(any(name.endswith((".glb", ".mjs", ".fbx", ".png", ".blend")) for name in zipped.namelist()))
        self.assertEqual(self.plan["status"], "plan_only")
        self.assertEqual(self.plan["catalog_candidate"]["adoption"], "not_run")
        self.assertEqual(self.plan["catalog_candidate"]["parameter_overrides"], {})
        self.assertTrue(all(item["provenance"].startswith("original_") for item in self.plan["objects"]))


if __name__ == "__main__":
    unittest.main()

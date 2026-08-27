"""Package parity checks for the canonical product discovery contract."""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from scripts.product_discovery import load_product_catalog, resolve_product_intent

ROOT = Path(__file__).resolve().parent.parent


class PackagedProductDiscoveryTests(unittest.TestCase):
    def test_npm_and_standalone_skill_outputs_carry_the_same_catalog(self) -> None:
        canonical = load_product_catalog()
        with TemporaryDirectory() as directory:
            output = Path(directory)
            npm = output / "npm"
            npm_result = subprocess.run(
                [sys.executable, "scripts/build_npm_package.py", "--output", str(npm)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, npm_result.returncode, npm_result.stdout + npm_result.stderr)
            npm_catalog = json.loads((npm / "catalog.json").read_text(encoding="utf-8"))
            self.assertEqual(canonical["products"], npm_catalog["products"])
            self.assertEqual(canonical["ui_routing"], npm_catalog["ui_routing"])
            self.assertEqual(
                canonical,
                json.loads(
                    (
                        npm
                        / "skills"
                        / "dcc-mcp"
                        / "references"
                        / "PRODUCTS.json"
                    ).read_text(encoding="utf-8")
                ),
            )

            skills = output / "skills"
            zip_result = subprocess.run(
                [
                    sys.executable,
                    "scripts/package_openclaw_skill.py",
                    ".github/clawhub-skills.json",
                    str(skills),
                    "--manifest",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, zip_result.returncode, zip_result.stdout + zip_result.stderr)
            archives = list(skills.glob("dcc-mcp-[0-9]*.zip"))
            self.assertEqual(1, len(archives))
            with ZipFile(archives[0]) as archive:
                packaged = json.loads(
                    archive.read("dcc-mcp/references/PRODUCTS.json").decode("utf-8")
                )
            self.assertEqual(canonical, packaged)

    def test_unreal_chinese_identity_reaches_every_installable_projection(self) -> None:
        alias = "虚幻引擎"
        canonical = load_product_catalog()
        unreal = next(product for product in canonical["products"] if product["id"] == "unreal")
        self.assertIn(alias, unreal["aliases"])
        self.assertEqual(
            {"status": "match", "product_ids": ["unreal"]},
            resolve_product_intent("在虚幻引擎中创建关卡", canonical),
        )

        source_surfaces = (
            ROOT / "plugins" / "dcc-mcp" / "skills" / "dcc-mcp" / "SKILL.md",
            ROOT / "plugins" / "dcc-mcp" / "plugin.json",
            ROOT / "plugins" / "dcc-mcp" / ".codex-plugin" / "plugin.json",
            ROOT / "plugins" / "dcc-mcp" / ".claude-plugin" / "plugin.json",
            ROOT / "plugins" / "dcc-mcp" / ".codebuddy-plugin" / "plugin.json",
        )
        for surface in source_surfaces:
            with self.subTest(surface=surface.relative_to(ROOT).as_posix()):
                self.assertIn(alias, surface.read_text(encoding="utf-8"))

        with TemporaryDirectory() as directory:
            output = Path(directory)
            npm = output / "npm"
            npm_result = subprocess.run(
                [sys.executable, "scripts/build_npm_package.py", "--output", str(npm)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, npm_result.returncode, npm_result.stdout + npm_result.stderr)
            self.assertIn(alias, (npm / "catalog.json").read_text(encoding="utf-8"))
            self.assertIn(
                alias,
                (npm / "skills" / "dcc-mcp" / "SKILL.md").read_text(encoding="utf-8"),
            )

            skills = output / "skills"
            zip_result = subprocess.run(
                [
                    sys.executable,
                    "scripts/package_openclaw_skill.py",
                    ".github/clawhub-skills.json",
                    str(skills),
                    "--manifest",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(0, zip_result.returncode, zip_result.stdout + zip_result.stderr)
            archive = next(skills.glob("dcc-mcp-[0-9]*.zip"))
            with ZipFile(archive) as packaged_skill:
                self.assertIn(alias, packaged_skill.read("dcc-mcp/SKILL.md").decode("utf-8"))

        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        self.assertIn(f'grep -q "{alias}" "$path/skills/dcc-mcp/SKILL.md"', workflow)
        self.assertIn('archive.read("dcc-mcp/skills/dcc-mcp/SKILL.md")', workflow)


if __name__ == "__main__":
    unittest.main()

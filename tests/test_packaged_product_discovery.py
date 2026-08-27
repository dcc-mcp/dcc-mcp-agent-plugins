"""Package parity checks for the canonical product discovery contract."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from scripts.product_discovery import load_product_catalog


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


if __name__ == "__main__":
    unittest.main()

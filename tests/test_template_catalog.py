"""Keep template-first guidance and scoped license evidence in distributed Skills."""

from datetime import date
import json
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import urlparse
from zipfile import ZipFile

from scripts.build_npm_package import copy_skill
from scripts.package_openclaw_skill import package_skill


SKILL = Path(__file__).resolve().parents[1] / "plugins/dcc-mcp/skills/dcc-mcp"
CATALOG = SKILL / "references/TEMPLATE_CATALOG"


class TemplateCatalogTests(unittest.TestCase):
    def test_catalog_has_pinned_scoped_evidence_without_claiming_host_acceptance(self):
        """Keep source evidence separate from unperformed host acceptance."""
        entries = sorted(CATALOG.glob("*.json"))
        self.assertTrue(entries)
        ids = set()
        for path in entries:
            with self.subTest(entry=path.name):
                entry = json.loads(path.read_text(encoding="utf-8"))
                self.assertEqual(1, entry["schema_version"])
                self.assertEqual(path.stem, entry["id"])
                self.assertNotIn(entry["id"], ids)
                ids.add(entry["id"])
                self.assertRegex(entry["id"], r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
                self.assertRegex(entry["revision"], r"^[0-9a-f]{40}$")
                date.fromisoformat(entry["reviewed_at"])
                source = urlparse(entry["source_url"])
                self.assertEqual("https", source.scheme)
                self.assertIsNone(source.username)
                for key in ("name", "host", "declared_host_version"):
                    self.assertTrue(entry[key].strip())
                self.assertEqual("source_evidence_only", entry["license_review"])
                self.assertEqual("not_run", entry["host_validation"])
                self.assertTrue(entry["unresolved"])
                self.assertTrue(entry["license_evidence"])
                for evidence in entry["license_evidence"]:
                    self.assertTrue(evidence["paths"])
                    for key in ("license", "notice", "conditions"):
                        self.assertTrue(evidence[key].strip())
                    url = urlparse(evidence["evidence_url"])
                    self.assertEqual(("https", source.netloc), (url.scheme, url.netloc))
                    self.assertIsNone(url.username)
                    self.assertTrue(url.path.startswith(source.path + "/blob/" + entry["revision"] + "/"))

    def test_initial_candidate_keeps_font_and_asset_licenses_separate_from_code(self):
        """Prevent the code license from hiding bundled font and asset obligations."""
        entry = json.loads((CATALOG / "kenney-3d-platformer.json").read_text(encoding="utf-8"))
        evidence = {item["license"]: item for item in entry["license_evidence"]}
        self.assertEqual({"MIT", "CC0-1.0", "OFL-1.1"}, set(evidence))
        self.assertIn("fonts/", evidence["OFL-1.1"]["paths"])
        self.assertIn("Lilita", evidence["OFL-1.1"]["notice"])
        self.assertIn("reserved name", evidence["OFL-1.1"]["conditions"])

    def test_default_route_and_license_records_survive_zip_and_npm_packaging(self):
        """Ensure installed Skills retain the default route and its license evidence."""
        text = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        workflow = " ".join(text.split())
        self.assertLess(workflow.index("Use a suitable existing project/template"), workflow.index("In the existing task recipe/evidence report"))
        for requirement in ("Unknown rights or host compatibility block adoption", "Do not install or run a template", "why no template fits", "An explicit user choice takes precedence"):
            self.assertIn(requirement, workflow)
        link = re.search(r"\[template license catalog\]\(([^)]+)\)", text)
        self.assertIsNotNone(link)
        self.assertEqual("references/TEMPLATE_CATALOG/README.md", link.group(1))
        with TemporaryDirectory() as temporary:
            output = Path(temporary)
            archive = package_skill(SKILL, output, "0.0.1")
            copy_skill(SKILL, output / "npm/dcc-mcp")
            with ZipFile(archive) as zipped:
                for path in [SKILL / "SKILL.md", *sorted(CATALOG.iterdir())]:
                    relative = path.relative_to(SKILL)
                    self.assertEqual(path.read_bytes(), zipped.read("dcc-mcp/" + relative.as_posix()))
                    self.assertEqual(path.read_bytes(), (output / "npm/dcc-mcp" / relative).read_bytes())

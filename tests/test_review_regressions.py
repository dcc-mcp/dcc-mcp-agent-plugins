"""Regression tests for the independent PR #8 review findings."""

from __future__ import annotations

import subprocess
import sys
import unittest
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parent.parent

from scripts import product_discovery
from scripts.build_geo_site import _llms_txt, build
from scripts.distribution import build_catalog


class IndependentReviewRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = product_discovery.load_product_catalog()

    def test_required_ci_and_release_check_the_immutable_core_catalog(self) -> None:
        command = "python scripts/sync_product_discovery.py --check --check-core-catalog"
        for relative in (".github/workflows/ci.yml", ".github/workflows/release.yml"):
            with self.subTest(workflow=relative):
                workflow = (ROOT / relative).read_text(encoding="utf-8")
                self.assertIn(command, workflow)
                self.assertIn('"PyYAML==6.0.2"', workflow)

    def test_non_catalog_commands_do_not_import_optional_yaml(self) -> None:
        result = subprocess.run(
            [sys.executable, "-S", "-c", "import scripts.sync_product_discovery"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_immutable_catalog_rejects_a_coordinated_source_product_rename(self) -> None:
        immutable_snapshot = {
            "entries": [
                {
                    "name": product["adapter"],
                    "dcc": [product["id"]],
                    "url": product["repository"],
                    "tags": ["adapter"],
                    **(
                        {"install": {"type": "test"}}
                        if product["catalog_install_available"]
                        else {}
                    ),
                }
                for product in self.catalog["products"]
            ]
        }
        renamed = deepcopy(self.catalog)
        renamed["sources"]["released_cli"]["dcc_types"][0] = "3dsmax-renamed"
        renamed["products"][0]["id"] = "3dsmax-renamed"

        # The enriched source and product can remain internally consistent.
        product_discovery.validate_product_catalog(renamed)
        checker = getattr(product_discovery, "validate_core_catalog_snapshot", None)
        self.assertIsNotNone(checker, "an immutable authoritative checker is required")
        checker(self.catalog, immutable_snapshot)
        with self.assertRaises(ValueError):
            checker(renamed, immutable_snapshot)

    def test_built_llms_txt_preserves_the_complete_ui_routing_contract(self) -> None:
        with TemporaryDirectory() as directory:
            output = Path(directory) / "site"
            build(output, ROOT)
            llms = (output / "llms.txt").read_text(encoding="utf-8")

        route = self.catalog["ui_routing"]
        self.assertIn("typed DCC-MCP tools", llms)
        self.assertIn("provider=dcc-cua", llms)
        self.assertIn("hard provider boundary", llms)
        self.assertIn("canonical/default", llms)
        self.assertIn("human-only", llms.casefold())
        for search_term in route["search_terms"]:
            with self.subTest(search_term=search_term):
                self.assertIn(search_term, llms)
        for scope in route["scope"]:
            with self.subTest(scope=scope):
                self.assertIn(scope, llms)
        for field in route["required_attestation"]:
            with self.subTest(attestation=field):
                self.assertIn(f"{field}=", llms)
        for action in route["action_contract"]:
            with self.subTest(action=action):
                self.assertIn(action, llms)
        for fallback in route["forbidden_fallbacks"]:
            with self.subTest(fallback=fallback):
                self.assertIn(fallback, llms)
        for challenge in route["human_handoff"]:
            with self.subTest(challenge=challenge):
                self.assertIn(challenge, llms)

    def test_llms_ui_text_is_derived_from_ui_routing(self) -> None:
        catalog = deepcopy(build_catalog(ROOT))
        catalog["ui_routing"]["canonical_provider"] = "review-provider"
        catalog["ui_routing"]["forbidden_fallbacks"] = ["Review Fallback"]
        catalog["ui_routing"]["human_handoff"] = ["review challenge"]

        llms = _llms_txt(catalog)
        self.assertIn("provider=review-provider", llms)
        self.assertIn("Review Fallback", llms)
        self.assertIn("review challenge", llms)

    def test_alias_fields_are_arrays_of_non_empty_strings(self) -> None:
        invalid_values = (
            ("aliases", "Blender"),
            ("contextual_aliases", "Maya"),
            ("aliases", [""]),
            ("contextual_aliases", ["  "]),
            ("aliases", [7]),
        )
        for field, value in invalid_values:
            mutation = deepcopy(self.catalog)
            mutation["products"][0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                product_discovery.validate_product_catalog(mutation)

        for field in ("aliases", "contextual_aliases"):
            mutation = deepcopy(self.catalog)
            del mutation["products"][0][field]
            with self.subTest(missing=field), self.assertRaises(ValueError):
                product_discovery.validate_product_catalog(mutation)

    def test_adapter_and_repository_duplicates_use_normalized_identity(self) -> None:
        mutation = deepcopy(self.catalog)
        first = mutation["products"][0]
        second = mutation["products"][1]
        second["adapter"] = first["adapter"].upper()
        second["repository"] = first["repository"].upper() + "/"

        with self.assertRaises(ValueError):
            product_discovery.validate_product_catalog(mutation)


if __name__ == "__main__":
    unittest.main()

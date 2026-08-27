"""Executable discovery contracts for every product in the released CLI catalog."""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unittest

from scripts.product_discovery import (
    load_product_catalog,
    normalize_term,
    product_terms,
    resolve_product_intent,
    validate_released_cli_snapshot,
    validate_product_catalog,
)
from scripts.distribution import build_catalog
from scripts.sync_product_discovery import OPENAI_INTERFACE, rendered_outputs


ROOT = Path(__file__).resolve().parent.parent
PLUGIN_MANIFESTS = (
    ROOT / "plugins" / "dcc-mcp" / "plugin.json",
    ROOT / "plugins" / "dcc-mcp" / ".codex-plugin" / "plugin.json",
    ROOT / "plugins" / "dcc-mcp" / ".claude-plugin" / "plugin.json",
    ROOT / "plugins" / "dcc-mcp" / ".codebuddy-plugin" / "plugin.json",
)
SKILL_MD = ROOT / "plugins" / "dcc-mcp" / "skills" / "dcc-mcp" / "SKILL.md"


def _json_strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [text for item in value for text in _json_strings(item)]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _json_strings(item)]
    return []


def _normalized_discovery_text(path: Path) -> str:
    if path.suffix == ".json":
        value = json.loads(path.read_text(encoding="utf-8"))
        text = " ".join(_json_strings(value))
    else:
        body = path.read_text(encoding="utf-8")
        _, frontmatter, _ = body.split("---", 2)
        text = frontmatter
    return normalize_term(text)


class ReleasedProductDiscoveryTests(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog = load_product_catalog()

    def test_catalog_matches_the_captured_released_cli_identity_set(self) -> None:
        cli_types = self.catalog["sources"]["released_cli"]["dcc_types"]
        product_types = [product["id"] for product in self.catalog["products"]]
        self.assertEqual(cli_types, product_types)
        self.assertEqual(35, len(product_types))

    def test_released_cli_snapshot_rejects_missing_or_misdirected_products(self) -> None:
        payload = {
            "total": len(self.catalog["products"]),
            "dcc_types": [
                {
                    "dcc_type": product["id"],
                    "adapters": [
                        {
                            "name": product["adapter"],
                            "url": product["repository"],
                            "catalog_install_available": product["catalog_install_available"],
                        }
                    ],
                }
                for product in self.catalog["products"]
            ],
        }
        version = self.catalog["sources"]["released_cli"]["version"]
        validate_released_cli_snapshot(self.catalog, version, payload)

        missing = deepcopy(payload)
        missing["dcc_types"].pop()
        missing["total"] -= 1
        with self.assertRaises(ValueError):
            validate_released_cli_snapshot(self.catalog, version, missing)

        misdirected = deepcopy(payload)
        misdirected["dcc_types"][0]["adapters"][0]["url"] = (
            "https://github.com/example/not-the-owner"
        )
        with self.assertRaises(ValueError):
            validate_released_cli_snapshot(self.catalog, version, misdirected)

    def test_every_installable_surface_explicitly_names_every_released_product(self) -> None:
        missing_by_surface: dict[str, list[str]] = {}
        for path in (*PLUGIN_MANIFESTS, SKILL_MD):
            discovery_text = _normalized_discovery_text(path)
            missing = [
                product["id"]
                for product in self.catalog["products"]
                if not any(
                    normalize_term(term) in discovery_text for term in product_terms(product)
                )
            ]
            if missing:
                missing_by_surface[path.relative_to(ROOT).as_posix()] = missing
        self.assertEqual({}, missing_by_surface)

    def test_every_english_and_chinese_product_intent_resolves_uniquely(self) -> None:
        for product in self.catalog["products"]:
            for language in ("en", "zh"):
                with self.subTest(product=product["id"], language=language):
                    self.assertEqual(
                        {"status": "match", "product_ids": [product["id"]]},
                        resolve_product_intent(
                            product["intent_examples"][language], self.catalog
                        ),
                    )

    def test_bounded_aliases_resolve_to_one_canonical_identity(self) -> None:
        cases = {
            "Create a prop in 3dsmax": "3dsmax",
            "Animate this in C4D": "c4d",
            "Retarget this in MoBu": "mobu",
            "Set up a level in UE": "unreal",
            "Package this UE4 project": "unreal",
            "请在团结引擎中创建场景": "unity",
            "Open the Tuanjie project": "unity",
            "Check the task in ShotGrid": "shotgrid",
            "Author this in Substance Designer": "substance3d_designer",
            "Paint this in Substance Painter": "substance3d_painter",
        }
        for query, expected in cases.items():
            with self.subTest(query=query):
                self.assertEqual(
                    {"status": "match", "product_ids": [expected]},
                    resolve_product_intent(query, self.catalog),
                )

    def test_generic_words_and_non_product_uses_do_not_hijack_routing(self) -> None:
        queries = (
            "maximize the browser window",
            "team unity matters",
            "nuke the build cache",
            "the movie premiere starts at eight",
            "the price is ten USD",
            "open the office document",
            "hire an illustrator for the poster",
            "the katana was forged by hand",
            "this floor is tiled already",
            "Maya civilization exhibit tickets",
            "Mari sent a message",
            "render the design after painting",
        )
        for query in queries:
            with self.subTest(query=query):
                self.assertEqual(
                    {"status": "none", "product_ids": []},
                    resolve_product_intent(query, self.catalog),
                )

    def test_multiple_product_names_are_ambiguous_instead_of_shadowed(self) -> None:
        self.assertEqual(
            {"status": "ambiguous", "product_ids": ["blender", "maya"]},
            resolve_product_intent(
                "Move the model from Blender to Autodesk Maya.", self.catalog
            ),
        )

    def test_mutations_cannot_delete_rename_duplicate_or_broaden_products(self) -> None:
        mutations: list[dict] = []

        deleted = deepcopy(self.catalog)
        deleted["products"].pop()
        mutations.append(deleted)

        renamed = deepcopy(self.catalog)
        renamed["products"][0]["id"] = "3ds-max-renamed"
        mutations.append(renamed)

        duplicate = deepcopy(self.catalog)
        duplicate["products"][15]["aliases"].append("Blender")
        mutations.append(duplicate)

        broad = deepcopy(self.catalog)
        broad["products"][15]["aliases"].append("render")
        mutations.append(broad)

        missing_ui_term = deepcopy(self.catalog)
        missing_ui_term["ui_routing"]["search_terms"] = ["DCC-CUA"]
        mutations.append(missing_ui_term)

        missing_ui_scope = deepcopy(self.catalog)
        missing_ui_scope["ui_routing"]["scope"].remove("browser UI")
        mutations.append(missing_ui_scope)

        missing_fallback = deepcopy(self.catalog)
        missing_fallback["ui_routing"]["forbidden_fallbacks"].remove("@oai/sky")
        mutations.append(missing_fallback)

        missing_action = deepcopy(self.catalog)
        missing_action["ui_routing"]["action_contract"].remove("post-action state readback")
        mutations.append(missing_action)

        missing_handoff = deepcopy(self.catalog)
        missing_handoff["ui_routing"]["human_handoff"].remove("CAPTCHA")
        mutations.append(missing_handoff)

        for mutation in mutations:
            with self.subTest():
                with self.assertRaises(ValueError):
                    validate_product_catalog(mutation)

    def test_ui_route_is_one_fail_closed_project_provider(self) -> None:
        route = self.catalog["ui_routing"]
        self.assertEqual("dcc-cua", route["canonical_provider"])
        self.assertEqual(["DCC-CUA", "ui-control"], route["search_terms"])
        self.assertTrue(route["typed_tools_first"])
        self.assertFalse(route["hard_skill_dependency"])
        self.assertEqual(["provider", "runtime", "pid", "hwnd"], route["required_attestation"])
        self.assertIn("post-action state readback", route["action_contract"])
        self.assertIn("CAPTCHA", route["human_handoff"])
        forbidden = " ".join(route["forbidden_fallbacks"])
        for provider in ("Computer Use", "computer-use", "@oai/sky", "Browser", "Chrome"):
            self.assertIn(provider, forbidden)

    def test_default_skill_body_contains_the_complete_ui_action_contract(self) -> None:
        body = SKILL_MD.read_text(encoding="utf-8").casefold()
        required = (
            "provider=dcc-cua",
            "runtime",
            "pid",
            "hwnd",
            "fresh observation",
            "latest snapshot",
            "post-action readback",
            "interruption",
            "permission",
            "captcha",
            "authentication",
            "security challenge",
        )
        for term in required:
            with self.subTest(term=term):
                self.assertIn(term, body)

    def test_generated_discovery_surfaces_are_current(self) -> None:
        result = subprocess.run(
            [sys.executable, "scripts/sync_product_discovery.py", "--check"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_generated_interface_counts_are_derived_from_the_catalog(self) -> None:
        reduced_catalog = deepcopy(self.catalog)
        reduced_catalog["products"].pop()
        outputs = rendered_outputs(reduced_catalog)

        for path in PLUGIN_MANIFESTS:
            manifest = json.loads(outputs[path])
            with self.subTest(path=path.relative_to(ROOT).as_posix()):
                self.assertIn("34 released creative applications", manifest["description"])

        codex_manifest = json.loads(outputs[PLUGIN_MANIFESTS[1]])
        self.assertIn("34 creative products", codex_manifest["interface"]["shortDescription"])
        self.assertIn(
            "34 released creative applications",
            codex_manifest["interface"]["longDescription"],
        )
        self.assertIn("Route 34 released creative products", outputs[OPENAI_INTERFACE])

    def test_public_distribution_catalog_projects_the_canonical_contract(self) -> None:
        public_catalog = build_catalog(ROOT)
        self.assertEqual(self.catalog["products"], public_catalog["products"])
        self.assertEqual(self.catalog["ui_routing"], public_catalog["ui_routing"])
        self.assertEqual(
            self.catalog["sources"]["released_cli"],
            public_catalog["released_product_source"],
        )

    def test_generated_distribution_document_has_the_complete_product_matrix(self) -> None:
        document = (ROOT / "docs" / "DISTRIBUTION.md").read_text(encoding="utf-8")
        for product in self.catalog["products"]:
            with self.subTest(product=product["id"]):
                self.assertIn(product["display_name"], document)
                self.assertIn(product["repository"], document)
        self.assertIn("DCC-CUA", document)
        self.assertIn("ui-control", document)


if __name__ == "__main__":
    unittest.main()

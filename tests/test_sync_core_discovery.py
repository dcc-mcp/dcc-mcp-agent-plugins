"""Ownership tests for Core-authored Skill bodies and distribution discovery metadata."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from scripts.sync_core_skills import is_distribution_owned_file, same_content


CORE_SKILL = """---
name: dcc-mcp
description: >-
  Core description.
license: MIT-0
metadata:
  dcc-mcp:
    version: "0.19.91"
    search-hint: "core terms"
    tags: "core, terms"
---

# Canonical body
"""

DISTRIBUTED_SKILL = """---
name: dcc-mcp
description: >-
  Distribution product description.
license: MIT-0
metadata:
  dcc-mcp:
    version: "0.19.95"
    search-hint: "all released products DCC-CUA ui-control"
    tags: "all, released, products"
---

<!-- BEGIN GENERATED PRODUCT DISCOVERY ROUTING -->
## Released Product and Application UI Routing

Distribution-owned generated route.
<!-- END GENERATED PRODUCT DISCOVERY ROUTING -->

# Canonical body
"""


class CoreSyncDiscoveryOwnershipTests(unittest.TestCase):
    def test_only_bounded_distribution_files_are_owned_outside_core(self) -> None:
        self.assertTrue(is_distribution_owned_file("dcc-mcp", Path("agents/openai.yaml")))
        self.assertTrue(is_distribution_owned_file("dcc-mcp", Path("references/PRODUCTS.json")))
        self.assertTrue(
            is_distribution_owned_file("dcc-mcp", Path("references/LOCAL_APP_PATH_CACHE.md"))
        )
        self.assertTrue(
            is_distribution_owned_file("dcc-mcp", Path("scripts/app_path_cache.py"))
        )
        self.assertFalse(is_distribution_owned_file("dcc-mcp", Path("references/CLI_CHEATSHEET.md")))
        self.assertFalse(is_distribution_owned_file("dcc-mcp-creator", Path("agents/openai.yaml")))

    def test_skill_sync_ignores_only_bounded_distribution_metadata(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.md"
            target = root / "target.md"
            source.write_text(CORE_SKILL, encoding="utf-8")
            target.write_text(DISTRIBUTED_SKILL, encoding="utf-8")
            self.assertTrue(same_content(source, target, is_skill_md=True, skill="dcc-mcp"))

            source.write_text(CORE_SKILL.replace("# Canonical body", "# Changed body"), encoding="utf-8")
            self.assertFalse(same_content(source, target, is_skill_md=True, skill="dcc-mcp"))

            target.write_text(
                DISTRIBUTED_SKILL.replace("Distribution-owned generated route.", "Changed route."),
                encoding="utf-8",
            )
            source.write_text(CORE_SKILL, encoding="utf-8")
            self.assertTrue(same_content(source, target, is_skill_md=True, skill="dcc-mcp"))


if __name__ == "__main__":
    unittest.main()

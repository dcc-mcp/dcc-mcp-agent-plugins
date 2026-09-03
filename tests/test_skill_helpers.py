"""Regression tests for helpers shipped by the canonical public Skills."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import dcc_mcp_core


ROOT = Path(__file__).resolve().parent.parent
CREATOR_ROOT = ROOT / "plugins" / "dcc-mcp" / "skills" / "dcc-mcp-skills-creator"


def load_helper(name: str, filename: str):
    path = CREATOR_ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load helper: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PublicSkillHelperTests(unittest.TestCase):
    def test_creator_scaffold_keeps_codex_and_async_contracts(self) -> None:
        module = load_helper("creator_create_skill", "create_skill.py")
        with TemporaryDirectory() as directory:
            skill_dir = Path(
                module.create_skill(
                    "houdini-cook-tools",
                    directory,
                    dcc="houdini",
                    execution="async",
                    affinity="main",
                )
            )
            tool = dcc_mcp_core.yaml_loads(
                (skill_dir / "tools.yaml").read_text(encoding="utf-8")
            )["tools"][0]
            prompt = dcc_mcp_core.yaml_loads(
                (skill_dir / "agents" / "openai.yaml").read_text(encoding="utf-8")
            )["interface"]["default_prompt"]

            self.assertEqual("async", tool["execution"])
            self.assertEqual("monolithic", tool["job_strategy"])
            self.assertIs(True, tool["annotations"]["deferred_hint"])
            self.assertIn("typed job progress", prompt)
            self.assertTrue(dcc_mcp_core.validate_skill(str(skill_dir)).is_clean)

    def test_creator_validator_enforces_nested_version_metadata(self) -> None:
        module = load_helper("creator_validate_skill_dir", "validate_skill_dir.py")
        with TemporaryDirectory() as directory:
            skill_dir = Path(directory) / "maya-mgear"
            skill_dir.mkdir()
            skill_md = skill_dir / "SKILL.md"
            skill_md.write_text(
                '---\nname: maya-mgear\ndescription: mGear integration\nversion: "1.0.0"\n---\n# Skill\n',
                encoding="utf-8",
            )
            invalid = module.validate_skill_dir(str(skill_dir))
            self.assertTrue(invalid["has_errors"])
            self.assertTrue(
                any("metadata.dcc-mcp.version" in issue["message"] for issue in invalid["issues"])
            )

            skill_md.write_text(
                "---\n"
                "name: maya-mgear\n"
                "description: mGear integration\n"
                "metadata:\n"
                "  dcc-mcp:\n"
                "    dcc: maya\n"
                '    version: "1.0.0"\n'
                "---\n"
                "# Skill\n",
                encoding="utf-8",
            )
            valid = module.validate_skill_dir(str(skill_dir))
            self.assertFalse(valid["has_errors"])


if __name__ == "__main__":
    unittest.main()

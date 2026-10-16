"""Ensure installed public Skills retain their mandatory shared-guide route."""

from pathlib import Path
import json
import re
import subprocess
import sys
from tempfile import TemporaryDirectory
import unittest
from urllib.parse import urlparse
from zipfile import ZipFile

from scripts.build_npm_package import copy_skill
from scripts.package_openclaw_skill import package_skill


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins" / "dcc-mcp" / "skills" / "dcc-mcp"


def guide_route(text: str) -> str:
    links = re.findall(r"\[production reuse gate\]\(([^)]+)\)", text)
    if len(links) != 1:
        raise ValueError("the production entrypoint needs one canonical guide route")
    uri = urlparse(links[0])
    if (uri.scheme, uri.netloc, uri.path, uri.fragment) != (
        "https", "github.com",
        "/dcc-mcp/dcc-mcp-core/blob/main/crates/dcc-mcp-gateway/src/gateway/native_resources/agent_workflows.md",
        "production-reuse-gate",
    ):
        raise ValueError("guide route must resolve to the shared Core resource source")
    return uri.geturl()


class ProductionReuseEntrypointTests(unittest.TestCase):
    def test_old_gateway_and_unmerged_source_do_not_satisfy_gate(self):
        document = "## Production reuse gate\n\n**Contract:** `dcc-mcp-production-reuse/v1`\n\nRead and execute the verified reuse rules.\n"
        cases = (
            (json.dumps({"uri": "gateway://docs/agent-workflows", "document": "# Old workflow guide"}), False),
            (json.dumps({"production_reuse_contract": "dcc-mcp-production-reuse/v1", "document": "# Old workflow guide"}), False),
            (json.dumps({"production_reuse_contract": "dcc-mcp-production-reuse/v2", "document": document}), False),
            ("# Core workflow guide before this change\n", False),
            ("## Production reuse gate\n\n**Contract:** `dcc-mcp-production-reuse/v1`\n", False),
            (document, True),
            (json.dumps({"production_reuse_contract": "dcc-mcp-production-reuse/v1", "document": document}), True),
        )
        with TemporaryDirectory() as directory:
            output = Path(directory)
            archive = package_skill(SKILL, output, "0.0.1")
            with ZipFile(archive) as zipped:
                zipped.extractall(output / "installed")
            checker = output / "installed/dcc-mcp/scripts/check_production_guide.py"
            for text, accepted in cases:
                guide = output / "retrieved-guide.txt"
                guide.write_text(text, encoding="utf-8")
                result = subprocess.run([sys.executable, str(checker), str(guide)], capture_output=True, text=True)
                self.assertEqual(0 if accepted else 2, result.returncode, result.stderr)
                payload = json.loads(result.stdout)
                self.assertEqual(accepted, payload["guide_available"])
                self.assertEqual("read_and_execute_gate" if accepted else "try_core_source_or_report_rollout_dependency", payload["next_step"])

    def test_installation_formats_preserve_the_executable_entrypoint(self):
        original = (SKILL / "SKILL.md").read_bytes().decode("utf-8")
        expected = guide_route(original)
        with TemporaryDirectory() as directory:
            output = Path(directory)
            archive = package_skill(SKILL, output, "0.0.1")
            with ZipFile(archive) as zipped:
                installed = zipped.read("dcc-mcp/SKILL.md").decode("utf-8")
            self.assertEqual(original, installed)
            self.assertEqual(expected, guide_route(installed))
            copy_skill(SKILL, output / "npm" / "dcc-mcp")
            copied = (output / "npm" / "dcc-mcp" / "SKILL.md").read_bytes().decode("utf-8")
            self.assertEqual(original, copied)
            self.assertEqual(expected, guide_route(copied))

    def test_missing_or_redirected_guidance_fails(self):
        for text in ("# Skill", "[production reuse gate](https://example.com/guide)"):
            with self.assertRaises(ValueError):
                guide_route(text)

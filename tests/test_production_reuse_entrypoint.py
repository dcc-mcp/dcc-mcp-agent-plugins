"""Ensure installed public Skills retain their mandatory shared-guide route."""

from pathlib import Path
import re
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

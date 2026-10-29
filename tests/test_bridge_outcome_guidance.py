"""Guard packaged replay guidance, not the Core runtime's transport behavior."""

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from scripts.build_npm_package import copy_skill
from scripts.package_openclaw_skill import package_skill


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "plugins/dcc-mcp/skills/dcc-mcp-creator"
GUIDE = Path("references/ADAPTER_WORKFLOW.md")


def assert_replay_guidance(test: unittest.TestCase, text: str) -> None:
    paragraph = text.split("When adopting the request-outcome contract", 1)[1].split("\n\n", 1)[0]
    paragraph = " ".join(paragraph.split())
    for requirement in (
        "unclassified bridge failure as `unknown`; do not replay the operation on any transport.",
        "Permit operation replay only with request-level evidence that this request never reached dispatch (`not_dispatched`)",
        "Connection recovery does not authorize operation replay.",
        "A pre-dispatch failure does not authorize replay of earlier workflow steps.",
        "verify that the deployed Core version actually includes the contract.",
    ):
        test.assertIn(requirement, paragraph)


class BridgeOutcomeGuidanceTests(unittest.TestCase):
    def test_source_requires_request_evidence_on_every_transport(self):
        assert_replay_guidance(self, (SKILL / GUIDE).read_text(encoding="utf-8"))

    def test_guard_rejects_transport_and_evidence_regressions(self):
        text = (SKILL / GUIDE).read_text(encoding="utf-8")
        regressions = (
            ("on any\ntransport", "on another transport"),
            ("request-level evidence", "connection recovery"),
            ("not authorize operation replay", "authorize operation replay"),
        )
        for original, replacement in regressions:
            with self.subTest(replacement=replacement):
                self.assertIn(original, text)
                with self.assertRaises(AssertionError):
                    assert_replay_guidance(self, text.replace(original, replacement, 1))

    def test_zip_and_npm_preserve_the_safe_guidance_bytes(self):
        expected = (SKILL / GUIDE).read_bytes()
        with TemporaryDirectory() as directory:
            output = Path(directory)
            archive = package_skill(SKILL, output, "0.0.1")
            with ZipFile(archive) as zipped:
                installed = zipped.read(f"dcc-mcp-creator/{GUIDE.as_posix()}")
            self.assertEqual(expected, installed)
            assert_replay_guidance(self, installed.decode("utf-8"))
            copy_skill(SKILL, output / "npm" / "dcc-mcp-creator")
            copied = (output / "npm" / "dcc-mcp-creator" / GUIDE).read_bytes()
            self.assertEqual(expected, copied)
            assert_replay_guidance(self, copied.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()

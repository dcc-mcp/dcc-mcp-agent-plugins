from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.sync_adapter_readme import END_MARKER, START_MARKER, render, sync_readme

ROOT = Path(__file__).resolve().parent.parent


class AdapterReadmeSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.template = (ROOT / "templates" / "adapter-readme-agent-quickstart.md").read_text(
            encoding="utf-8"
        )
        registry = json.loads(
            (ROOT / ".github" / "adapter-readme-quickstarts.json").read_text(encoding="utf-8")
        )
        self.entry = registry["repositories"]["dcc-mcp-blender"]
        self.generated = render(self.template, self.entry)

    def test_render_uses_canonical_install_and_adapter_specific_smoke_prompt(self) -> None:
        self.assertIn("codex plugin marketplace add dcc-mcp/dcc-mcp-agent-plugins", self.generated)
        self.assertIn("dcc-mcp-cli list", self.generated)
        self.assertIn("dcc_type=blender", self.generated)
        self.assertIn(self.entry["smoke_prompt"], self.generated)
        self.assertNotIn("{{", self.generated)

    def test_first_sync_inserts_before_first_second_level_heading(self) -> None:
        current = "# Adapter\n\nIntroduction.\n\n## Install\n\nHost setup.\n"
        synced = sync_readme(current, self.generated)
        self.assertLess(synced.index(START_MARKER), synced.index("## Install"))
        self.assertEqual(1, synced.count(START_MARKER))
        self.assertEqual(1, synced.count(END_MARKER))

    def test_sync_is_idempotent_and_replaces_only_marked_block(self) -> None:
        current = "# Adapter\n\nIntroduction.\n\n## Install\n\nHost setup.\n"
        first = sync_readme(current, self.generated)
        second = sync_readme(first, self.generated)
        self.assertEqual(first, second)
        self.assertIn("Host setup.", second)

    def test_invalid_marker_pair_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            sync_readme(f"# Adapter\n\n{START_MARKER}\n", self.generated)

    def test_cli_write_then_check_and_detect_stale_content(self) -> None:
        with TemporaryDirectory() as directory:
            readme = Path(directory) / "README.md"
            readme.write_text("# Adapter\n\nIntroduction.\n", encoding="utf-8")
            command = [
                sys.executable,
                str(ROOT / "scripts" / "sync_adapter_readme.py"),
                "--repository",
                "dcc-mcp-blender",
                "--readme",
                str(readme),
            ]
            write = subprocess.run(command + ["--write"], capture_output=True, text=True, check=False)
            self.assertEqual(0, write.returncode, write.stderr)
            check = subprocess.run(command + ["--check"], capture_output=True, text=True, check=False)
            self.assertEqual(0, check.returncode, check.stderr)

            readme.write_text(
                readme.read_text(encoding="utf-8").replace("dcc_type=blender", "dcc_type=wrong"),
                encoding="utf-8",
            )
            stale = subprocess.run(command + ["--check"], capture_output=True, text=True, check=False)
            self.assertEqual(1, stale.returncode)
            self.assertIn("stale generated Agent quickstart", stale.stderr)


if __name__ == "__main__":
    unittest.main()

"""Exercise the standalone Skill installer without a gateway or a DCC."""

import hashlib
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / "plugins/dcc-mcp/skills/dcc-mcp/scripts"
sys.path.insert(0, str(SCRIPTS))
import dcc_gateway


class SkillInstallTests(unittest.TestCase):
    def test_install_cli_publishes_both_executable_names_without_a_gateway(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            asset, _ = dcc_gateway._release_assets()
            version = "1.2.3"
            binary = b"release fixture"
            manifest = {"dccmcp": {
                "version": version,
                "url": f"https://github.com/{dcc_gateway.OFFICIAL_REPO}/releases/download/v{version}/{asset}",
                "sha256": hashlib.sha256(binary).hexdigest(),
            }}
            responses = [io.BytesIO(json.dumps(manifest).encode()), io.BytesIO(binary)]
            argv = ["dcc_gateway.py", "--version", version, "--install-dir", temporary, "install-cli"]
            with patch.object(sys, "argv", argv), patch.object(
                dcc_gateway.urllib.request, "urlopen", side_effect=responses
            ), patch.object(dcc_gateway, "run_command", side_effect=AssertionError), redirect_stdout(io.StringIO()):
                self.assertEqual(dcc_gateway.main(), 0)
            for name in ("dccmcp", "dcc-mcp-cli"):
                path = directory / (name + (".exe" if os.name == "nt" else ""))
                self.assertEqual(path.read_bytes(), binary)
                if os.name != "nt":
                    self.assertTrue(os.access(path, os.X_OK))

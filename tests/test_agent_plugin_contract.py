from __future__ import annotations

import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
CONTRACT = ROOT / "plugins" / "dcc-mcp" / "agent-plugin.json"
PLUGIN = ROOT / "plugins" / "dcc-mcp" / "plugin.json"
PRODUCTS = ROOT / "plugins" / "dcc-mcp" / "skills" / "dcc-mcp" / "references" / "PRODUCTS.json"


class AgentPluginContractTests(unittest.TestCase):
    def test_contract_declares_the_standalone_cli_boundary(self) -> None:
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        plugin = json.loads(PLUGIN.read_text(encoding="utf-8"))
        products = json.loads(PRODUCTS.read_text(encoding="utf-8"))

        self.assertEqual("1", contract["schema_version"])
        self.assertEqual("dcc-mcp", contract["id"])
        self.assertEqual(plugin["version"], contract["version"])
        self.assertEqual("dccmcp-cli", contract["runtime"]["kind"])
        self.assertEqual(
            products["sources"]["released_cli"]["version"],
            contract["runtime"]["minimum_cli"],
        )
        self.assertEqual(
            {"streamable-http", "rest"},
            set(contract["runtime"]["transports"]),
        )
        command = contract["commands"][0]
        self.assertEqual("dccmcp", command["name"])
        self.assertIn("dcc-mcp-cli", command["compatibility_aliases"])
        self.assertEqual({"dccmcp", "dcc-mcp-cli"}, set(contract["permissions"]["process"]))

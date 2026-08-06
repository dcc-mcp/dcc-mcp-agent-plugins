"""Validate the canonical Skill suite and thin vendor manifests."""

from __future__ import annotations

import json
from pathlib import Path
import sys

import dcc_mcp_core
from smithery_sync import validate_manifest as validate_smithery_manifest


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "dcc-mcp"
CLAWHUB_MANIFEST = ROOT / ".github" / "clawhub-skills.json"
SMITHERY_MANIFEST = ROOT / ".github" / "smithery-skills.json"
AGENT_PLUGIN_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"
PLUGIN_MANIFESTS = (
    PLUGIN / "plugin.json",
    PLUGIN / ".codex-plugin" / "plugin.json",
    PLUGIN / ".claude-plugin" / "plugin.json",
    PLUGIN / ".codebuddy-plugin" / "plugin.json",
)
MARKETPLACE_MANIFESTS = (
    ROOT / ".claude-plugin" / "marketplace.json",
    ROOT / ".codebuddy-plugin" / "marketplace.json",
)


def main() -> int:
    agent_plugin = json.loads(PLUGIN_MANIFESTS[0].read_text(encoding="utf-8"))
    if agent_plugin.get("$schema") != AGENT_PLUGIN_SCHEMA:
        raise ValueError("invalid Agent Plugins schema")

    plugin_versions = {json.loads(path.read_text(encoding="utf-8"))["version"] for path in PLUGIN_MANIFESTS}
    if len(plugin_versions) != 1:
        raise ValueError(f"plugin manifest versions differ: {sorted(plugin_versions)}")
    version = plugin_versions.pop()

    for path in MARKETPLACE_MANIFESTS:
        marketplace = json.loads(path.read_text(encoding="utf-8"))
        if marketplace["plugins"][0]["version"] != version:
            raise ValueError(f"marketplace version differs from plugin: {path}")

    entries = json.loads(CLAWHUB_MANIFEST.read_text(encoding="utf-8"))["skills"]
    if len(entries) != 3:
        raise ValueError("ClawHub manifest must contain the three public Skills")
    for entry in entries:
        skill_dir = ROOT / entry["path"]
        report = dcc_mcp_core.validate_skill(str(skill_dir))
        if not report.is_clean:
            raise ValueError(f"invalid Skill {entry['slug']}: {report.issues}")
        metadata = dcc_mcp_core.parse_skill_md(str(skill_dir))
        if metadata is None or metadata.name != entry["slug"] or metadata.version != entry["version"]:
            raise ValueError(f"Skill metadata differs from ClawHub manifest: {entry['slug']}")
        if not (skill_dir / "agents" / "openai.yaml").is_file():
            raise ValueError(f"missing Codex interface metadata: {entry['slug']}")

    validate_smithery_manifest(SMITHERY_MANIFEST, ROOT)

    print(f"Validated {len(entries)} Skills and {len(PLUGIN_MANIFESTS) + len(MARKETPLACE_MANIFESTS)} manifests at {version}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, TypeError, ValueError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error

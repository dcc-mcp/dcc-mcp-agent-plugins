"""Validate the canonical Skill suite and thin vendor manifests."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import dcc_mcp_core
from distribution import build_catalog, load_manifest
from product_discovery import (
    RELEASED_CORE_WORKFLOW_JOBS,
    load_product_catalog,
    validate_released_core_workflows,
)
from smithery_sync import validate_manifest as validate_smithery_manifest
from sync_product_discovery import rendered_outputs

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
# The Agent Plugins marketplace carries no version field, so it is checked for
# naming and for pointing at the same plugin directory as the vendor manifests.
AGENTS_MARKETPLACE_MANIFEST = ROOT / ".agents" / "plugins" / "marketplace.json"
PLUGIN_SOURCE_PATH = "./plugins/dcc-mcp"
CHANNEL_AUTOMATION = {"published", "verified", "manual", "not-applicable"}


def main() -> int:
    product_catalog = load_product_catalog()
    validate_released_core_workflows(
        product_catalog,
        {
            relative: (ROOT / relative).read_text(encoding="utf-8")
            for relative in RELEASED_CORE_WORKFLOW_JOBS
        },
    )
    stale_discovery = [
        path.relative_to(ROOT).as_posix()
        for path, expected in rendered_outputs(product_catalog).items()
        if path.read_text(encoding="utf-8") != expected
    ]
    if stale_discovery:
        raise ValueError(f"generated product discovery metadata is stale: {stale_discovery}")

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
        if marketplace["plugins"][0]["source"] != PLUGIN_SOURCE_PATH:
            raise ValueError(f"marketplace points at another plugin directory: {path}")

    agents_marketplace = json.loads(AGENTS_MARKETPLACE_MANIFEST.read_text(encoding="utf-8"))
    agents_plugin = agents_marketplace["plugins"][0]
    if agents_plugin["name"] != PLUGIN.name:
        raise ValueError(f"Agent Plugins marketplace names another plugin: {agents_plugin['name']}")
    if agents_plugin["source"]["path"] != PLUGIN_SOURCE_PATH:
        raise ValueError(
            f"Agent Plugins marketplace points at another plugin directory: {AGENTS_MARKETPLACE_MANIFEST}"
        )

    entries = json.loads(CLAWHUB_MANIFEST.read_text(encoding="utf-8"))["skills"]
    expected_slugs = {"dcc-mcp", "dcc-mcp-skills-creator", "dcc-mcp-creator", "dcc-cua"}
    if {entry.get("slug") for entry in entries} != expected_slugs:
        raise ValueError("ClawHub manifest must contain the four public Skills")
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

    # build_catalog re-checks every Skill against the ClawHub manifest, so a
    # catalog that builds is a catalog every downstream channel can render.
    catalog = build_catalog(ROOT)
    if catalog["version"] != version:
        raise ValueError(f"catalog version differs from plugin: {catalog['version']}")
    if catalog["products"] != product_catalog["products"]:
        raise ValueError("public catalog products differ from PRODUCTS.json")
    if catalog.get("application_routes", []) != product_catalog.get("application_routes", []):
        raise ValueError("public catalog application routes differ from PRODUCTS.json")
    expected_current_source = product_catalog["sources"].get(
        "current_core_catalog", product_catalog["sources"]["core_catalog"]
    )
    if catalog.get("current_product_source") != expected_current_source:
        raise ValueError("public catalog current product source differs from PRODUCTS.json")
    if catalog["ui_routing"] != product_catalog["ui_routing"]:
        raise ValueError("public catalog UI routing differs from PRODUCTS.json")
    npm_package = load_manifest()["npm"]["package"]
    if not npm_package.startswith("@") or "/" not in npm_package:
        raise ValueError(f"npm package must be a scoped name: {npm_package}")
    for channel in catalog["channels"]:
        if channel["automation"] not in CHANNEL_AUTOMATION:
            raise ValueError(f"unknown channel automation: {channel['name']}")
        if not channel["url"].startswith("https://"):
            raise ValueError(f"channel URL must be https: {channel['name']}")

    manifests = len(PLUGIN_MANIFESTS) + len(MARKETPLACE_MANIFESTS) + 2
    print(
        f"Validated {len(entries)} Skills, {manifests} manifests, "
        f"{len(product_catalog['products'])} released products plus "
        f"{len(product_catalog.get('application_routes', []))} application routes, and "
        f"{len(catalog['channels'])} distribution channels at {version}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, TypeError, ValueError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error

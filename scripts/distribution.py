"""Shared distribution metadata for the release, catalog, and GEO pipelines."""

from __future__ import annotations

import json
from pathlib import Path

import dcc_mcp_core

try:
    from product_discovery import load_product_catalog
except ModuleNotFoundError:  # Imported as scripts.distribution by unit tests.
    from .product_discovery import load_product_catalog


ROOT = Path(__file__).resolve().parent.parent
PLUGIN = ROOT / "plugins" / "dcc-mcp"
DISTRIBUTION_MANIFEST = ROOT / ".github" / "distribution.json"
CLAWHUB_MANIFEST = ROOT / ".github" / "clawhub-skills.json"


def load_manifest(path: Path = DISTRIBUTION_MANIFEST) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    for key in ("site", "npm", "skills_cli", "channels"):
        if key not in data:
            raise ValueError(f"distribution manifest is missing {key!r}")
    base_url = data["site"]["base_url"]
    if not base_url.startswith("https://") or base_url.endswith("/"):
        raise ValueError("site.base_url must be an https URL without a trailing slash")
    return data


def plugin_version(root: Path = ROOT) -> str:
    manifest = root / "plugins" / "dcc-mcp" / "plugin.json"
    return json.loads(manifest.read_text(encoding="utf-8"))["version"]


def _text(value) -> str:
    return " ".join(str(value or "").split())


def build_catalog(root: Path = ROOT, manifest_path: Path = DISTRIBUTION_MANIFEST) -> dict:
    """Return the machine-readable catalog every distribution target renders from."""
    manifest = load_manifest(manifest_path)
    site = manifest["site"]
    version = plugin_version(root)
    plugin = json.loads((root / "plugins" / "dcc-mcp" / "plugin.json").read_text(encoding="utf-8"))
    entries = json.loads((root / ".github" / "clawhub-skills.json").read_text(encoding="utf-8"))["skills"]
    repository = site["repository"]
    npm_package = manifest["npm"]["package"]
    cli_repository = manifest["skills_cli"]["repository"]
    cli_package = manifest["skills_cli"]["package"]
    product_catalog = load_product_catalog(
        root
        / "plugins"
        / "dcc-mcp"
        / "skills"
        / "dcc-mcp"
        / "references"
        / "PRODUCTS.json"
    )

    skills = []
    for entry in entries:
        slug = entry["slug"]
        relative_path = entry["path"]
        metadata = dcc_mcp_core.parse_skill_md(str(root / relative_path))
        if metadata is None:
            raise ValueError(f"unreadable SKILL.md: {relative_path}")
        if metadata.name != slug or metadata.version != entry["version"]:
            raise ValueError(f"Skill metadata differs from the ClawHub manifest: {slug}")
        keywords = sorted({*(metadata.tags or []), *_text(metadata.search_hint).split()})
        skills.append(
            {
                "slug": slug,
                "version": metadata.version,
                "description": _text(metadata.description),
                "license": metadata.license or plugin["license"],
                "layer": metadata.layer,
                "dcc": metadata.dcc,
                "tags": list(metadata.tags or []),
                "keywords": keywords,
                "source_path": relative_path,
                "source_url": f"{repository}/tree/v{version}/{relative_path}",
                "skill_md_url": f"{repository}/blob/v{version}/{relative_path}/SKILL.md",
                "page_url": f"{site['base_url']}/skills/{slug}.html",
                "install": {
                    "skills_cli": f"npx --yes {cli_package} add {cli_repository} --skill {slug}",
                    "npm": f"npm install {npm_package}",
                    "clawhub": f"npx clawhub add {entry['owner']}/{slug}",
                },
            }
        )

    return {
        "name": site["title"],
        "description": _text(site["tagline"]),
        "version": version,
        "license": plugin["license"],
        "homepage": site["base_url"],
        "repository": repository,
        "publisher": {"name": site["publisher"], "url": site["publisher_url"]},
        "keywords": plugin["keywords"],
        "install": {
            "skills_cli": f"npx --yes {cli_package} add {cli_repository} --skill dcc-mcp",
            "npm": f"npm install {npm_package}",
        },
        "skills": skills,
        "products": product_catalog["products"],
        "ui_routing": product_catalog["ui_routing"],
        "released_product_source": product_catalog["sources"]["released_cli"],
        "channels": manifest["channels"],
    }

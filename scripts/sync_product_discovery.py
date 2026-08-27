"""Render agent-facing discovery metadata from the canonical product catalog."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import textwrap

try:
    from product_discovery import (
        ROOT,
        load_product_catalog,
        plugin_description,
        plugin_keywords,
        skill_description,
        skill_search_hint,
        skill_tags,
        ui_route_prompt,
        validate_released_cli_snapshot,
    )
except ModuleNotFoundError:  # Imported as scripts.sync_product_discovery by unit tests.
    from .product_discovery import (
        ROOT,
        load_product_catalog,
        plugin_description,
        plugin_keywords,
        skill_description,
        skill_search_hint,
        skill_tags,
        ui_route_prompt,
        validate_released_cli_snapshot,
    )


PLUGIN = ROOT / "plugins" / "dcc-mcp"
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
DISTRIBUTION_MANIFEST = ROOT / ".github" / "distribution.json"
SKILL_MD = PLUGIN / "skills" / "dcc-mcp" / "SKILL.md"
OPENAI_INTERFACE = PLUGIN / "skills" / "dcc-mcp" / "agents" / "openai.yaml"
UI_ROUTE_BEGIN = "<!-- BEGIN GENERATED PRODUCT DISCOVERY ROUTING -->"
UI_ROUTE_END = "<!-- END GENERATED PRODUCT DISCOVERY ROUTING -->"


def _json_text(value: dict) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False) + "\n"


def _folded_description(value: str) -> list[str]:
    lines = ["description: >-"]
    lines.extend(
        f"  {line}"
        for line in textwrap.wrap(
            value,
            width=96,
            break_long_words=False,
            break_on_hyphens=False,
        )
    )
    return lines


def _render_ui_route_block(catalog: dict) -> str:
    route = catalog["ui_routing"]
    search_terms = " and ".join(f"`{term}`" for term in route["search_terms"])
    scope = ", ".join(route["scope"])
    fallbacks = ", ".join(f"`{provider}`" for provider in route["forbidden_fallbacks"])
    actions = "; ".join(route["action_contract"])
    handoff = ", ".join(route["human_handoff"])
    return (
        f"{UI_ROUTE_BEGIN}\n"
        "## Released Product and Application UI Routing\n\n"
        "Load `references/PRODUCTS.json` only when released-product support, aliases, or "
        "routing are ambiguous; do not load every product record for unrelated tasks. Use "
        "typed DCC-MCP tools first.\n\n"
        f"{search_terms} name one project-owned `{route['canonical_provider']}` route for "
        f"{scope}; they are not competing automation systems. An explicit DCC-CUA request "
        "is a hard provider boundary. Do not recommend or silently fall back to "
        f"{fallbacks}. If the project route is unavailable, repair it or report the blocker.\n\n"
        "Before the first UI observation or input, visibly attest "
        "`provider=dcc-cua runtime=<version> pid=<exact-pid> hwnd=<exact-native-hwnd>`. "
        "Missing or stale binding data stops the action. For every state-dependent UI action, "
        f"require {actions}. Stop fail-closed on interruption or permission failure, and hand "
        f"{handoff} to a human instead of bypassing it.\n\n"
        "Discovery and packaging evidence do not claim licensed real-host validation.\n"
        f"{UI_ROUTE_END}"
    )


def _replace_generated_block(current: str, rendered: str) -> str:
    if UI_ROUTE_BEGIN in current or UI_ROUTE_END in current:
        if current.count(UI_ROUTE_BEGIN) != 1 or current.count(UI_ROUTE_END) != 1:
            raise ValueError("dcc-mcp SKILL.md has malformed generated UI routing markers")
        before, remainder = current.split(UI_ROUTE_BEGIN, 1)
        _, after = remainder.split(UI_ROUTE_END, 1)
        return before.rstrip() + "\n\n" + rendered + "\n\n" + after.lstrip("\r\n")

    lines = current.splitlines()
    try:
        frontmatter_end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("dcc-mcp SKILL.md frontmatter is not closed") from error
    body_start = frontmatter_end + 1
    while body_start < len(lines) and not lines[body_start].strip():
        body_start += 1
    lines[frontmatter_end + 1 : body_start] = ["", rendered, ""]
    return "\n".join(lines) + "\n"


def _render_skill_md(current: str, catalog: dict) -> str:
    lines = current.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("dcc-mcp SKILL.md has no frontmatter")
    try:
        frontmatter_end = lines.index("---", 1)
    except ValueError as error:
        raise ValueError("dcc-mcp SKILL.md frontmatter is not closed") from error

    description_start = next(
        index for index in range(1, frontmatter_end) if lines[index].startswith("description:")
    )
    license_start = next(
        index for index in range(description_start + 1, frontmatter_end) if lines[index].startswith("license:")
    )
    lines[description_start:license_start] = _folded_description(skill_description(catalog))
    frontmatter_end = lines.index("---", 1)

    search_hint = json.dumps(skill_search_hint(catalog), ensure_ascii=False)
    tags = json.dumps(", ".join(skill_tags(catalog)), ensure_ascii=False)
    replacements = {
        "search-hint:": f"    search-hint: {search_hint}",
        "tags:": f"    tags: {tags}",
    }
    for prefix, replacement in replacements.items():
        matches = [
            index
            for index in range(1, frontmatter_end)
            if lines[index].startswith("    ") and lines[index].lstrip().startswith(prefix)
        ]
        if len(matches) != 1:
            raise ValueError(f"dcc-mcp SKILL.md needs exactly one {prefix} field")
        lines[matches[0]] = replacement
    current = "\n".join(lines) + "\n"
    return _replace_generated_block(current, _render_ui_route_block(catalog))


def _render_openai_interface(catalog: dict) -> str:
    short = (
        f"Route {len(catalog['products'])} released creative products "
        "and DCC-CUA application UI"
    )
    prompt = ui_route_prompt(catalog)
    return (
        "interface:\n"
        '  display_name: "DCC-MCP"\n'
        f"  short_description: {json.dumps(short, ensure_ascii=False)}\n"
        f"  default_prompt: {json.dumps(prompt, ensure_ascii=False)}\n"
    )


def rendered_outputs(catalog: dict) -> dict[Path, str]:
    count = len(catalog["products"])
    description = plugin_description(catalog)
    keywords = plugin_keywords(catalog)
    product_names = ", ".join(product["display_name"] for product in catalog["products"])
    outputs: dict[Path, str] = {}

    for path in PLUGIN_MANIFESTS:
        manifest = json.loads(path.read_text(encoding="utf-8"))
        manifest["description"] = description
        manifest["keywords"] = keywords
        if path.parent.name == ".codex-plugin":
            interface = manifest["interface"]
            interface["shortDescription"] = (
                f"Typed control for {count} creative products plus DCC-CUA UI routing."
            )
            interface["longDescription"] = (
                f"{description} Released product identities: {product_names}. "
                "Typed tools remain first; DCC-CUA and ui-control are one project-owned UI route."
            )
            interface["capabilities"] = [
                "Released-product discovery",
                "Structured DCC-MCP tool routing",
                "Project-owned DCC-CUA / ui-control application UI",
            ]
            interface["defaultPrompt"] = [
                "Show the released DCC-MCP products I can route to.",
                "Create a simple scene in Blender with typed DCC-MCP tools.",
                "Set up a playable scene in Unity or Tuanjie with DCC-MCP.",
                "Use DCC-CUA through ui-control for this exact application window.",
            ]
        outputs[path] = _json_text(manifest)

    for path in MARKETPLACE_MANIFESTS:
        marketplace = json.loads(path.read_text(encoding="utf-8"))
        marketplace["description"] = description
        marketplace["plugins"][0]["description"] = description
        outputs[path] = _json_text(marketplace)

    distribution = json.loads(DISTRIBUTION_MANIFEST.read_text(encoding="utf-8"))
    distribution["site"]["tagline"] = description
    outputs[DISTRIBUTION_MANIFEST] = _json_text(distribution)
    outputs[SKILL_MD] = _render_skill_md(SKILL_MD.read_text(encoding="utf-8"), catalog)
    outputs[OPENAI_INTERFACE] = _render_openai_interface(catalog)
    return outputs


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail when generated discovery metadata drifts")
    parser.add_argument(
        "--check-cli",
        action="store_true",
        help="compare the catalog with the installed released dcc-mcp-cli",
    )
    args = parser.parse_args(argv)

    catalog = load_product_catalog()
    if args.check_cli:
        try:
            version_result = subprocess.run(
                ["dcc-mcp-cli", "--version"],
                capture_output=True,
                text=True,
                check=True,
            )
            cli_version = version_result.stdout.strip().split()[-1]
            catalog_result = subprocess.run(
                ["dcc-mcp-cli", "dcc-types", "--output", "json"],
                capture_output=True,
                text=True,
                check=True,
            )
            validate_released_cli_snapshot(catalog, cli_version, json.loads(catalog_result.stdout))
        except (IndexError, json.JSONDecodeError, OSError, subprocess.CalledProcessError, ValueError) as error:
            print(f"released CLI discovery differs: {error}")
            return 1
        print(f"Released CLI {cli_version} matches {len(catalog['products'])} product identities")
    drift: list[Path] = []
    for path, expected in rendered_outputs(catalog).items():
        current = path.read_text(encoding="utf-8")
        if current == expected:
            continue
        if args.check:
            drift.append(path)
        else:
            path.write_text(expected, encoding="utf-8")
            print(path.relative_to(ROOT).as_posix())

    if drift:
        print("product discovery metadata is stale:")
        for path in drift:
            print(f"  - {path.relative_to(ROOT).as_posix()}")
        print("regenerate with: python scripts/sync_product_discovery.py")
        return 1
    if args.check:
        print(f"Product discovery metadata matches {len(catalog['products'])} released products")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

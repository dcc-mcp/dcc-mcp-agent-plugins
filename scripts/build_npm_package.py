"""Stage the canonical Skill suite as a publishable npm package.

The package carries no code. It vendors the same `skills/` directory the
Agent Skills CLI installs, so hosts that resolve Skills from `node_modules`
get byte-identical instructions to every other channel.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys

from distribution import ROOT, build_catalog, load_manifest


DEFAULT_OUTPUT = ROOT / "dist" / "npm"
SKILLS_DIR = ROOT / "plugins" / "dcc-mcp" / "skills"


def _package_json(catalog: dict, manifest: dict) -> dict:
    keywords = sorted({*catalog["keywords"], "agent-skills", "skills", "ai-agent", "dcc-mcp", "claude-code", "codex"})
    return {
        "name": manifest["npm"]["package"],
        "version": catalog["version"],
        "description": catalog["description"],
        "keywords": keywords,
        "license": catalog["license"],
        "author": f"{catalog['publisher']['name']} ({catalog['publisher']['url']})",
        "homepage": catalog["homepage"],
        "repository": {
            "type": "git",
            "url": f"git+{catalog['repository']}.git",
            "directory": "plugins/dcc-mcp",
        },
        "bugs": {"url": f"{catalog['repository']}/issues"},
        "publishConfig": {"access": manifest["npm"]["access"], "registry": manifest["npm"]["registry"]},
        "files": ["skills", "catalog.json", "README.md", "LICENSE"],
    }


def _readme(catalog: dict, manifest: dict) -> str:
    rows = "\n".join(
        f"| `{skill['slug']}` | {skill['description']} |" for skill in catalog["skills"]
    )
    return f"""# {manifest["npm"]["package"]}

{catalog["description"]}

This package vendors the canonical DCC-MCP Agent Skills. It ships instructions
only - no runtime code - and stays byte-identical to the Skills published to
every other channel.

## Install

```bash
{catalog["install"]["npm"]}
```

Skills land in `node_modules/{manifest["npm"]["package"]}/skills/<slug>/SKILL.md`.
Hosts that read Skills from `node_modules` can sync them with the Agent Skills
CLI:

```bash
npx --yes {manifest["skills_cli"]["package"]} experimental_sync
```

To install directly from the repository instead:

```bash
{catalog["install"]["skills_cli"]}
```

## Skills

| Skill | What it does |
| --- | --- |
{rows}

Machine-readable metadata: [`catalog.json`]({catalog["homepage"]}/catalog.json) ·
[`llms.txt`]({catalog["homepage"]}/llms.txt)

## License

{catalog["license"]}. Source: {catalog["repository"]}
"""


def build(output: Path, root: Path = ROOT) -> dict:
    catalog = build_catalog(root)
    manifest = load_manifest()

    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)

    for skill in catalog["skills"]:
        shutil.copytree(root / skill["source_path"], output / "skills" / skill["slug"])

    package = _package_json(catalog, manifest)
    (output / "package.json").write_text(json.dumps(package, indent=2) + "\n", encoding="utf-8")
    (output / "catalog.json").write_text(
        json.dumps(catalog, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (output / "README.md").write_text(_readme(catalog, manifest), encoding="utf-8")
    shutil.copyfile(root / "LICENSE", output / "LICENSE")
    return package


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage the npm package for the canonical Skill suite")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    try:
        package = build(args.output)
        print(f"Staged {package['name']}@{package['version']} at {args.output}")
        return 0
    except (KeyError, OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        print(error, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

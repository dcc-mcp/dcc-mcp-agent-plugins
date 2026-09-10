"""Render the canonical Agent quickstart into an adapter README."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REGISTRY = ROOT / ".github" / "adapter-readme-quickstarts.json"
DEFAULT_TEMPLATE = ROOT / "templates" / "adapter-readme-agent-quickstart.md"
START_MARKER = "<!-- dcc-mcp-agent-quickstart:start -->"
END_MARKER = "<!-- dcc-mcp-agent-quickstart:end -->"
INSTALL_GUIDE_URL = "https://github.com/dcc-mcp/dcc-mcp-agent-plugins#install"
TROUBLESHOOTING_URL = (
    "https://github.com/dcc-mcp/dcc-mcp-agent-plugins"
    "#adapter-connection-troubleshooting"
)


def load_entry(registry_path: Path, repository: str) -> dict[str, str]:
    registry = json.loads(registry_path.read_text(encoding="utf-8"))
    if registry.get("schema_version") != 1:
        raise ValueError("unsupported adapter quickstart registry schema")
    try:
        entry = registry["repositories"][repository]
    except KeyError as error:
        raise ValueError(f"repository is not registered: {repository}") from error
    required = ("dcc_name", "dcc_type", "smoke_prompt")
    for field in required:
        value = entry.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{repository}.{field} must be a non-empty string")
    return entry


def render(template: str, entry: dict[str, str]) -> str:
    values = {
        "DCC_NAME": entry["dcc_name"],
        "DCC_TYPE": entry["dcc_type"],
        "SMOKE_PROMPT": entry["smoke_prompt"],
        "INSTALL_GUIDE_URL": INSTALL_GUIDE_URL,
        "TROUBLESHOOTING_URL": TROUBLESHOOTING_URL,
    }
    rendered = template
    for name, value in values.items():
        rendered = rendered.replace("{{" + name + "}}", value)
    if "{{" in rendered or "}}" in rendered:
        raise ValueError("template contains an unresolved placeholder")
    if rendered.count(START_MARKER) != 1 or rendered.count(END_MARKER) != 1:
        raise ValueError("template must contain exactly one marker pair")
    return rendered.rstrip() + "\n"


def sync_readme(current: str, generated: str) -> str:
    starts = current.count(START_MARKER)
    ends = current.count(END_MARKER)
    if starts != ends or starts > 1:
        raise ValueError("README contains an invalid quickstart marker pair")
    if starts == 1:
        start = current.index(START_MARKER)
        end = current.index(END_MARKER, start) + len(END_MARKER)
        suffix = current[end:].lstrip("\r\n")
        return current[:start].rstrip() + "\n\n" + generated + ("\n" + suffix if suffix else "")

    lines = current.splitlines(keepends=True)
    insertion = next(
        (index for index, line in enumerate(lines) if line.startswith("## ")),
        len(lines),
    )
    prefix = "".join(lines[:insertion]).rstrip()
    suffix = "".join(lines[insertion:]).lstrip("\r\n")
    return prefix + "\n\n" + generated + ("\n" + suffix if suffix else "")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render or verify the canonical Agent quickstart in an adapter README."
    )
    parser.add_argument("--repository", required=True, help="Repository name in the registry")
    parser.add_argument("--readme", type=Path, required=True, help="Adapter README path")
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="Insert or update the generated block")
    mode.add_argument("--check", action="store_true", help="Fail if the generated block is absent or stale")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    entry = load_entry(args.registry.resolve(), args.repository)
    template = args.template.resolve().read_text(encoding="utf-8")
    generated = render(template, entry)
    readme = args.readme.resolve()
    current = readme.read_text(encoding="utf-8")
    expected = sync_readme(current, generated)
    if args.check:
        if START_MARKER not in current:
            print(f"missing generated Agent quickstart: {readme}", file=sys.stderr)
            return 1
        if current != expected:
            print(f"stale generated Agent quickstart: {readme}", file=sys.stderr)
            return 1
        print(f"Agent quickstart is current: {readme}")
        return 0
    readme.write_text(expected, encoding="utf-8", newline="\n")
    print(f"Updated Agent quickstart: {readme}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (KeyError, OSError, TypeError, ValueError) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error

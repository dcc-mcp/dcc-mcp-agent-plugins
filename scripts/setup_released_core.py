"""Install and attest the one released Core runtime declared by PRODUCTS.json."""

from __future__ import annotations

import argparse
import importlib.metadata
import subprocess
import sys
from pathlib import Path

try:
    from product_discovery import load_product_catalog, validate_released_core_runtime
except ModuleNotFoundError:  # Imported as scripts.setup_released_core by unit tests.
    from .product_discovery import load_product_catalog, validate_released_core_runtime


ROOT = Path(__file__).resolve().parent.parent
GATEWAY = ROOT / "plugins" / "dcc-mcp" / "skills" / "dcc-mcp" / "scripts" / "dcc_gateway.py"


def resolve_release_commit(repository: str, tag: str) -> str:
    """Resolve a lightweight or annotated tag to the commit it releases."""
    direct_ref = f"refs/tags/{tag}"
    peeled_ref = f"{direct_ref}^{{}}"
    result = subprocess.run(
        ["git", "ls-remote", repository, direct_ref, peeled_ref],
        capture_output=True,
        text=True,
        check=True,
    )
    refs: dict[str, str] = {}
    for row in result.stdout.splitlines():
        fields = row.split()
        if len(fields) != 2 or fields[1] in refs:
            raise ValueError("released Core tag returned an invalid ref set")
        refs[fields[1]] = fields[0]
    commit = refs.get(peeled_ref) or refs.get(direct_ref)
    if commit is None:
        raise ValueError("released Core tag did not resolve")
    return commit


def install_released_core(version: str, *, with_catalog_dependencies: bool) -> str:
    """Install the exact package version and return the installed distribution version."""
    requirements = [f"dcc-mcp-core=={version}"]
    if with_catalog_dependencies:
        requirements.append("PyYAML==6.0.2")
    subprocess.run([sys.executable, "-m", "pip", "install", *requirements], check=True)
    return importlib.metadata.version("dcc-mcp-core")


def ensure_released_cli(directory: Path, version: str) -> None:
    """Install the matching official CLI through its SHA-verified component manifest."""
    subprocess.run(
        [
            sys.executable,
            str(GATEWAY),
            "--cli",
            str(directory / "not-installed"),
            "--ensure-cli",
            "--install-dir",
            str(directory),
            "--version",
            version,
            "health",
        ],
        check=True,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--with-catalog-dependencies",
        action="store_true",
        help="also install the exact YAML dependency used by immutable catalog checks",
    )
    parser.add_argument(
        "--ensure-cli-dir",
        type=Path,
        help="also install the matching released CLI into this directory",
    )
    args = parser.parse_args(argv)

    catalog = load_product_catalog()
    released = catalog["sources"]["released_cli"]
    resolved_commit = resolve_release_commit(released["repository"], released["tag"])
    installed_version = install_released_core(
        released["version"],
        with_catalog_dependencies=args.with_catalog_dependencies,
    )
    validate_released_core_runtime(
        catalog,
        installed_version=installed_version,
        resolved_commit=resolved_commit,
    )
    if args.ensure_cli_dir is not None:
        ensure_released_cli(args.ensure_cli_dir, released["version"])
    print(f"Released Core {installed_version} matches {resolved_commit}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (
        OSError,
        ValueError,
        importlib.metadata.PackageNotFoundError,
        subprocess.CalledProcessError,
    ) as error:
        print(error, file=sys.stderr)
        raise SystemExit(1) from error

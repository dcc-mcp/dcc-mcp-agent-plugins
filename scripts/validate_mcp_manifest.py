"""Offline dry-run validator for an UNACTIVATED Phase-1 manifest proposal.

Phase 1 only. This module is deliberately STDLIB-ONLY and READ-ONLY:

* It validates ``mcp_registry/server.json`` against the pinned official
  ``server.json`` schema (vendored, offline) and against the publish contract.
* It performs NO network calls, NO registry writes, NO OAuth, NO publish, and
  writes NO files. Running it is a pure offline dry-run over this repo's own
  committed artifacts.
* This Phase-1 proposal is UNACTIVATED: NO live publisher or consumer is wired
  to it. ``dcc-mcp/dcc-mcp-core``'s live ``publish-mcp-registry.yml`` does NOT
  fetch this manifest or run this validator. A non-zero exit only means the
  committed proposal artifacts are inconsistent; it does NOT gate any live
  publish. Wiring a consumer is a separate, reviewed Phase-2 change (hallong
  activation + independent review + an end-to-end test).

Checks (each is a separate function so it can be unit-tested with negative
fixtures):

* official-schema conformance (offline Draft-07 subset)
* the contract stays explicitly UNACTIVATED (activation flags false, no false
  source_ref pin, draft status)
* sha256 integrity of the committed manifest/schema/baseline
* backward-compatibility of every immutable identity/wiring field
* ``repository`` continues to point at the real server source (Core), never the
  skills repo
* three version domains validated separately as STATIC authoring values (no
  conflation, no claim of live PyPI/Registry verification)
* exactly ONE active publisher DESIGN declaration (offline, not enforced on any
  live publish)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parent.parent
MCP = ROOT / "mcp_registry"

NAME_RE = re.compile(r"^[a-zA-Z0-9.-]+/[a-zA-Z0-9._-]+$")
# Version ranges are rejected by the official schema; reject them here too.
VERSION_RANGE_RE = re.compile(r"(\^|~=|>=|<=|[*xX]|\|\||\s-\s)")
SKILLS_REPO_FRAGMENTS = ("dcc-mcp-agent-plugins",)


# ---------------------------------------------------------------------------
# Minimal, offline JSON-Schema (Draft-07 subset) validator.
# Implements exactly the keywords used by the vendored official schema.
# ---------------------------------------------------------------------------

def _json_schema_validate(instance: Any, schema: dict, root: dict, path: str = "$") -> list[str]:
    errors: list[str] = []

    ref = schema.get("$ref")
    if ref:
        if not ref.startswith("#/"):
            errors.append(f"{path}: non-local $ref not supported offline: {ref}")
            return errors
        target: Any = root
        for part in ref[2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        errors.extend(_json_schema_validate(instance, target, root, path))
        return errors

    if "const" in schema and instance != schema["const"]:
        errors.append(f"{path}: must equal const {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: {instance!r} not in enum {schema['enum']!r}")

    t = schema.get("type")
    if t:
        types = t if isinstance(t, list) else [t]
        if not any(_type_ok(instance, tt) for tt in types):
            errors.append(f"{path}: expected type {types}, got {type(instance).__name__}")

    for key in ("allOf",):
        for sub in schema.get(key, []):
            errors.extend(_json_schema_validate(instance, sub, root, path))
    if "anyOf" in schema:
        if not any(not _json_schema_validate(instance, sub, root, path) for sub in schema["anyOf"]):
            errors.append(f"{path}: does not match any anyOf branch")
    if "oneOf" in schema:
        matches = sum(not _json_schema_validate(instance, sub, root, path) for sub in schema["oneOf"])
        if matches != 1:
            errors.append(f"{path}: matched {matches} oneOf branches (expected 1)")
    if "not" in schema and not _json_schema_validate(instance, schema["not"], root, path):
        errors.append(f"{path}: must NOT match the 'not' schema")

    if isinstance(instance, str):
        if "minLength" in schema and len(instance) < schema["minLength"]:
            errors.append(f"{path}: string shorter than minLength {schema['minLength']}")
        if "maxLength" in schema and len(instance) > schema["maxLength"]:
            errors.append(f"{path}: string longer than maxLength {schema['maxLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], instance):
            errors.append(f"{path}: string does not match pattern {schema['pattern']!r}")
        if schema.get("format") == "uri" and not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", instance):
            errors.append(f"{path}: string is not a URI")

    if isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(f"{path}: missing required property '{req}'")
        props = schema.get("properties", {})
        for k, v in instance.items():
            if k in props:
                errors.extend(_json_schema_validate(v, props[k], root, f"{path}.{k}"))
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: additional property '{k}' not allowed")
            elif isinstance(schema.get("additionalProperties"), dict):
                errors.extend(_json_schema_validate(v, schema["additionalProperties"], root, f"{path}.{k}"))

    if isinstance(instance, list):
        item_schema = schema.get("items")
        if isinstance(item_schema, dict):
            for i, v in enumerate(instance):
                errors.extend(_json_schema_validate(v, item_schema, root, f"{path}[{i}]"))

    return errors


def _type_ok(instance: Any, t: str) -> bool:
    return {
        "object": isinstance(instance, dict),
        "array": isinstance(instance, list),
        "string": isinstance(instance, str),
        "number": isinstance(instance, (int, float)) and not isinstance(instance, bool),
        "integer": isinstance(instance, int) and not isinstance(instance, bool),
        "boolean": isinstance(instance, bool),
        "null": instance is None,
    }.get(t, True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get(dotted: str, obj: Any) -> tuple[bool, Any]:
    """Resolve 'packages[0].transport.url' style paths. Returns (found, value)."""
    cur = obj
    for token in dotted.split("."):
        m = re.match(r"^([^\[]+)((\[\d+\])*)$", token)
        if not m:
            return False, None
        key, idx_part = m.group(1), m.group(2)
        if not isinstance(cur, dict) or key not in cur:
            return False, None
        cur = cur[key]
        for idx in re.findall(r"\[(\d+)\]", idx_part):
            i = int(idx)
            if not isinstance(cur, list) or i >= len(cur):
                return False, None
            cur = cur[i]
    return True, cur


def _sha256(data: bytes) -> str:
    # Line-ending-independent: the pinned digests are over the committed blobs
    # (LF), but a Windows checkout with core.autocrlf=true materializes CRLF.
    # Normalize so the integrity check is stable on every platform.
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Individual checks. Each returns a list of error strings (empty == pass).
# All arguments are plain data so negative tests can inject bad fixtures.
# ---------------------------------------------------------------------------

def check_official_schema(manifest: Any, schema: dict) -> list[str]:
    return _json_schema_validate(manifest, schema, schema)


def check_activation_state(contract: dict) -> list[str]:
    """Guard the honest framing of this Phase-1 change.

    This proposal is UNACTIVATED: no live consumer/publisher is wired and there
    is no enforceable publish gate. Reject re-introducing the false fixed-SHA
    provenance (a ``source_ref`` pin into a base commit where the manifest did
    not exist) or flipping the activation flags without the separate reviewed
    Phase-2 change plus an end-to-end test.
    """
    errors: list[str] = []
    activation = contract.get("activation", {})
    for flag in ("phase_1_is_activated", "live_consumer_or_publisher_wired", "enforceable_publish_gate"):
        if activation.get(flag) is not False:
            errors.append(f"activation.{flag} must be false for the unactivated Phase-1 proposal (got {activation.get(flag)!r})")
    if contract.get("status") != "draft-do-not-activate":
        errors.append(f"status must be 'draft-do-not-activate' (got {contract.get('status')!r})")
    if "source_ref" in contract.get("manifest", {}):
        errors.append(
            "manifest.source_ref reintroduces a false fixed-SHA provenance claim; "
            "integrity is anchored to the committed sha256, not a fetch pin"
        )
    return errors


def pypi_authoring_version(contract: dict) -> str:
    """Read the PyPI authoring-time version from the contract (single source of truth).

    The value is a STATIC authoring snapshot, NOT a live PyPI/Registry lookup.
    """
    return str(contract["version_domains"]["pypi_package"]["value_at_authoring"])


def check_integrity(manifest_bytes: bytes, schema_bytes: bytes, baseline_bytes: bytes, contract: dict) -> list[str]:
    errors: list[str] = []
    pairs = [
        ("manifest", manifest_bytes, contract["manifest"]["sha256"]),
        ("official schema", schema_bytes, contract["official_schema"]["vendored_sha256"]),
        ("baseline", baseline_bytes, contract["baseline"]["sha256"]),
    ]
    for label, data, expected in pairs:
        actual = _sha256(data)
        if actual != expected:
            errors.append(f"{label} sha256 mismatch: expected {expected}, got {actual}")
    return errors


def check_backward_compat(manifest: Any, contract: dict) -> list[str]:
    errors: list[str] = []
    for dotted, expected in contract["immutable_fields"].items():
        if dotted.startswith("$"):
            continue
        found, value = _get(dotted, manifest)
        if not found:
            errors.append(f"immutable field '{dotted}' is missing")
        elif value != expected:
            errors.append(f"immutable field '{dotted}' changed: expected {expected!r}, got {value!r}")
    return errors


def check_repository_source(manifest: Any) -> list[str]:
    url = manifest.get("repository", {}).get("url", "")
    if any(frag in url for frag in SKILLS_REPO_FRAGMENTS):
        return [f"repository.url points at a skills repo ({url!r}); it must stay on the real server source (Core)"]
    if "dcc-mcp-core" not in url:
        return [f"repository.url ({url!r}) does not point at dcc-mcp-core server source"]
    return []


def check_version_domains(manifest: Any, contract: dict, plugin_suite_version: str) -> list[str]:
    errors: list[str] = []
    domains = contract["version_domains"]

    found_v, version = _get("version", manifest)
    found_pv, pkg_version = _get("packages[0].version", manifest)
    if not found_v or not found_pv:
        return ["version / packages[0].version missing"]

    if VERSION_RANGE_RE.search(str(version)):
        errors.append(f"version {version!r} looks like a version range (forbidden by official schema)")
    if version != pkg_version:
        errors.append(f"version-domain mismatch: version={version!r} != packages[0].version={pkg_version!r}")

    # Static authoring self-consistency (offline only): the source manifest
    # version must match the value recorded in the contract. This checks the
    # proposal's own data has not drifted; it is NOT a live Registry/PyPI check.
    registry_authoring = domains.get("registry_metadata", {}).get("value_in_source_manifest")
    if registry_authoring is not None and str(version) != str(registry_authoring):
        errors.append(
            f"source manifest version {version!r} != contract "
            f"registry_metadata.value_in_source_manifest {registry_authoring!r} "
            f"(static authoring self-consistency)"
        )

    # A plugin-suite version must never leak into the MCP server metadata.
    if plugin_suite_version and (version == plugin_suite_version or pkg_version == plugin_suite_version):
        errors.append(
            f"version-domain conflation: plugin suite version {plugin_suite_version!r} "
            f"written into the MCP server metadata (registry/pypi domain)"
        )

    # Brand fields centralized here must be present (schema-checked too, but
    # assert the centralization intent explicitly).
    for field in contract.get("brand_fields_owned_here", []):
        if not _get(field, manifest)[0]:
            errors.append(f"brand field '{field}' missing from centralized manifest")
    return errors


def check_single_publisher(contract: dict, active_publishers: list[str] | None = None) -> list[str]:
    errors: list[str] = []
    publishers = active_publishers if active_publishers is not None else contract["publisher"]["active_publishers"]
    max_allowed = contract["publisher"]["max_active_publishers"]
    if len(publishers) != max_allowed:
        errors.append(
            f"expected exactly {max_allowed} active publisher(s), found {len(publishers)}: {publishers}. "
            "Two publishers double-write the same registry name; cross-repo concurrency groups do not prevent this."
        )
    sole = contract["publisher"]["phase_1_sole_publisher"]
    if publishers and publishers[0] != sole:
        errors.append(f"Phase-1 sole publisher must be {sole!r}, got {publishers[0]!r}")
    return errors


def run_all_checks(
    contract: dict,
    manifest: Any,
    schema: dict,
    manifest_bytes: bytes,
    schema_bytes: bytes,
    baseline_bytes: bytes,
    plugin_suite_version: str,
    active_publishers: list[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    errors += check_official_schema(manifest, schema)
    errors += check_activation_state(contract)
    errors += check_integrity(manifest_bytes, schema_bytes, baseline_bytes, contract)
    errors += check_backward_compat(manifest, contract)
    errors += check_repository_source(manifest)
    errors += check_version_domains(manifest, contract, plugin_suite_version)
    errors += check_single_publisher(contract, active_publishers)
    return errors


# ---------------------------------------------------------------------------
# CLI: pure dry-run. Reads local files, validates, prints, exits. No writes.
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--publish", action="store_true",
                        help=argparse.SUPPRESS)  # explicit no-op guard for callers
    args = parser.parse_args(argv)

    if args.publish:
        # Fail closed. This module never publishes; Phase-2 cutover is a
        # separately reviewed action, not a flag on this validator.
        print("ERROR: this validator is read-only; publishing is a separate Phase-2 action.", file=sys.stderr)
        return 2

    contract = load_json(MCP / "publish-contract.json")
    manifest_bytes = (MCP / "server.json").read_bytes()
    manifest = json.loads(manifest_bytes)
    schema_bytes = (ROOT / contract["official_schema"]["vendored_path"]).read_bytes()
    schema = json.loads(schema_bytes)
    baseline_bytes = (ROOT / contract["baseline"]["path"]).read_bytes()
    plugin_suite_version = str(load_json(ROOT / "plugins" / "dcc-mcp" / "plugin.json")["version"])

    errors = run_all_checks(
        contract, manifest, schema, manifest_bytes, schema_bytes,
        baseline_bytes, plugin_suite_version,
    )

    print("MCP manifest dry-run (offline, read-only; no publish/registry/OAuth/network writes)")
    print(f"  manifest: {contract['manifest']['path']} (integrity anchored to committed sha256; no source_ref pin)")
    print(f"  official schema: {contract['official_schema']['url']}")
    print(
        "  version domains (STATIC authoring values, NOT live-verified): "
        f"registry/package={manifest['version']}, pypi={pypi_authoring_version(contract)}, "
        f"plugin_suite={plugin_suite_version}"
    )
    print("  activation: UNACTIVATED draft proposal; no live consumer/publisher and no enforceable publish gate wired.")
    if errors:
        print(f"FAIL-STOP: {len(errors)} error(s):")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("PASS: offline static checks (schema / activation-state / integrity / backward-compat / version-domain / single-publisher) passed.")
    print("NOTE: this does NOT activate, publish, or enforce anything; a live publisher/consumer is a separate Phase-2 change.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

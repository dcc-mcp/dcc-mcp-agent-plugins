"""Canonical released-product discovery and routing contracts."""

from __future__ import annotations

import hashlib
import json
import re
import shlex
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRODUCT_CATALOG = (
    ROOT
    / "plugins"
    / "dcc-mcp"
    / "skills"
    / "dcc-mcp"
    / "references"
    / "PRODUCTS.json"
)
PRODUCT_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
CORE_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
RELEASED_CORE_SETUP_COMMAND = "python scripts/setup_released_core.py"
RELEASED_CORE_CATALOG_SETUP_COMMAND = (
    f"{RELEASED_CORE_SETUP_COMMAND} --with-catalog-dependencies"
)
RELEASED_CORE_WORKFLOW_COMMANDS = {
    ".github/workflows/ci.yml": {
        "product-discovery": (
            f"{RELEASED_CORE_CATALOG_SETUP_COMMAND} "
            "--ensure-cli-dir .released-cli"
        ),
        "validate": RELEASED_CORE_CATALOG_SETUP_COMMAND,
    },
    ".github/workflows/core-sync.yml": {"sync-core": RELEASED_CORE_CATALOG_SETUP_COMMAND},
    ".github/workflows/clawhub.yml": {"sync-skills": RELEASED_CORE_CATALOG_SETUP_COMMAND},
    ".github/workflows/release.yml": {
        "github-release": (
            f"{RELEASED_CORE_CATALOG_SETUP_COMMAND} "
            "--ensure-cli-dir .released-cli"
        ),
        "publish-npm": RELEASED_CORE_CATALOG_SETUP_COMMAND,
        "publish-pages": RELEASED_CORE_CATALOG_SETUP_COMMAND,
    },
}
RELEASED_CORE_WORKFLOW_JOBS = {
    relative: tuple(commands) for relative, commands in RELEASED_CORE_WORKFLOW_COMMANDS.items()
}
RELEASED_CORE_WORKFLOW_ENVIRONMENT = {
    ".github/workflows/ci.yml": None,
    ".github/workflows/core-sync.yml": {"SYNC_BRANCH": "automation/core-skill-sync"},
    ".github/workflows/clawhub.yml": {
        "CLAWHUB_CLI_PACKAGE": "clawhub@0.23.1",
        "CLAWHUB_CONFIG_PATH": ".clawhub/config.json",
        "CLAWHUB_DISABLE_TELEMETRY": "1",
    },
    ".github/workflows/release.yml": None,
}
RELEASED_CORE_WORKFLOW_REQUIRED_TRIGGERS = {
    ".github/workflows/ci.yml": {
        "push": {"branches": ["main"]},
        "pull_request": {"branches": ["main"]},
        "workflow_dispatch": None,
    },
    ".github/workflows/core-sync.yml": {
        "push": {"branches": ["main"]},
        "pull_request": {"branches": ["main"]},
        "schedule": [{"cron": "17 6 * * 1"}],
        "workflow_dispatch": {
            "inputs": {
                "bump": {
                    "description": "Version part to bump when Skill content changed",
                    "required": False,
                    "type": "choice",
                    "default": "patch",
                    "options": ["patch", "minor", "major"],
                }
            }
        },
    },
    ".github/workflows/clawhub.yml": {
        "workflow_call": {
            "inputs": {
                "checkout-ref": {"required": False, "type": "string", "default": ""},
                "publish": {"required": False, "type": "boolean", "default": False},
            },
            "secrets": {"CLAWHUB_TOKEN": {"required": False}},
        },
        "pull_request": {
            "branches": ["main"],
            "paths": [
                "plugins/dcc-mcp/skills/**",
                "scripts/package_openclaw_skill.py",
                "scripts/clawhub_sync.py",
                "scripts/setup_released_core.py",
                ".github/clawhub-skills.json",
                ".github/workflows/clawhub.yml",
            ],
        },
        "workflow_dispatch": {
            "inputs": {
                "publish": {
                    "description": "Publish instead of dry-running",
                    "required": False,
                    "type": "boolean",
                    "default": False,
                }
            }
        },
    },
    ".github/workflows/release.yml": {"push": {"tags": ["v*"]}},
}
# These are SHA-256 digests of parsed YAML job mappings, not raw files. Formatting
# and comments remain free, while every job, step, action, command, and execution
# control is enumerated; an added job or changed executable surface fails closed.
RELEASED_CORE_WORKFLOW_JOB_DIGESTS = {
    ".github/workflows/ci.yml": {
        "product-discovery": "f548c76c55d0a0901fcc29489d635ba1c0fc0d3c07ecc283ed3d102ceb918d49",
        "validate": "3d9ffa7bcb000cacb170786d81467beb18d63de758ce093bfc3a165a91381a89",
    },
    ".github/workflows/core-sync.yml": {
        "verify-pin": "4c071dc815592aef174dd1c6d89089cefb75e7a0cc2170354fd101868d3d5170",
        "sync-core": "c6144286012f7676fd324a09427caf5759ee0eb6b8c5ae4567841de24b9d8477",
    },
    ".github/workflows/clawhub.yml": {
        "sync-skills": "bc3fbd6dd149b5fcb324109bd045f99518f45d6757854c11ad739566035cf3a1",
    },
    ".github/workflows/release.yml": {
        "github-release": "99356779fa49b277609f1a6575c274dff907e1edf914203a23c07ac209cfe006",
        "publish-clawhub": "c911a32259c3658a50b2f6c47ba2a80240a9e168c4bcfda483cb212640340330",
        "publish-smithery": "2749e01e660ea0ed74c37d4e4f25c23f6848925055806bf91ca4634e67e75530",
        "publish-npm": "944cbdfc9bdfdcbf38a745c83f6a3c16ef20fbde965b3a9fd939f4a0070814e6",
        "publish-pages": "0e2635dfcc1358f8f5f02623a837d7e4434f18b5a023fe6f580c1463ae3644bd",
        "verify-public-install": "58c37a5068557a0a5d9f94545301d0a8ebff25fad8e1ce2719f1ae1a34c77656",
    },
}
RELEASED_CORE_JOB_EXECUTION_CONTROLS = {
    ".github/workflows/ci.yml": {
        "product-discovery": {
            "strategy": {
                "fail-fast": False,
                "matrix": {
                    "include": [
                        {"os": "ubuntu-latest", "cli": ".released-cli/dcc-mcp-cli"},
                        {"os": "macos-latest", "cli": ".released-cli/dcc-mcp-cli"},
                        {"os": "windows-latest", "cli": ".released-cli/dcc-mcp-cli.exe"},
                    ]
                },
            },
            "runs-on": "${{ matrix.os }}",
            "timeout-minutes": 15,
        },
        "validate": {"runs-on": "ubuntu-latest", "timeout-minutes": 15},
    },
    ".github/workflows/core-sync.yml": {
        "sync-core": {
            "if": "github.event_name == 'schedule' || github.event_name == 'workflow_dispatch'",
            "runs-on": "ubuntu-latest",
            "timeout-minutes": 15,
        }
    },
    ".github/workflows/clawhub.yml": {
        "sync-skills": {"runs-on": "ubuntu-latest", "timeout-minutes": 20}
    },
    ".github/workflows/release.yml": {
        "github-release": {"runs-on": "ubuntu-latest", "timeout-minutes": 15},
        "publish-npm": {
            "needs": "github-release",
            "runs-on": "ubuntu-latest",
            "timeout-minutes": 10,
        },
        "publish-pages": {
            "needs": "github-release",
            "runs-on": "ubuntu-latest",
            "timeout-minutes": 10,
            "environment": {
                "name": "github-pages",
                "url": "${{ steps.deploy.outputs.page_url }}",
            },
        },
    },
}
WORKFLOW_EXECUTION_CONTROL_KEYS = {
    "concurrency",
    "container",
    "continue-on-error",
    "defaults",
    "env",
    "environment",
    "if",
    "needs",
    "runs-on",
    "services",
    "strategy",
    "timeout-minutes",
    "uses",
}
WORKFLOW_PACKAGE_MANAGERS = {
    "conda",
    "pip",
    "pip3",
    "pipx",
    "pdm",
    "poetry",
    "rye",
    "uv",
    "vx",
}
WORKFLOW_INDIRECT_COMMANDS = {
    ".",
    "alias",
    "bash",
    "builtin",
    "call",
    "cmd",
    "command",
    "env",
    "eval",
    "exec",
    "iex",
    "invoke-expression",
    "nohup",
    "powershell",
    "pwsh",
    "set-alias",
    "sh",
    "source",
    "start",
    "start-process",
    "sudo",
    "time",
    "trap",
    "xargs",
}
WORKFLOW_SHELL_CONTROL_TOKENS = {"!", "do", "elif", "else", "if", "then", "until", "while"}
WORKFLOW_COMMAND_BOUNDARY_CHARS = frozenset("&|;(){}")
GENERIC_HIJACK_TERMS = {
    "ae",
    "ai",
    "app",
    "control",
    "design",
    "editor",
    "max",
    "model",
    "office",
    "paint",
    "ps",
    "render",
    "software",
    "usd",
}


def normalize_term(value: str) -> str:
    """Normalize a discovery term without turning substrings into aliases."""
    text = unicodedata.normalize("NFKC", value).casefold()
    text = re.sub(r"[_/\\-]+", " ", text)
    return " ".join(text.split())


def load_product_catalog(path: Path = PRODUCT_CATALOG) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_product_catalog(data)
    return data


def _alias_terms(product: dict, field: str) -> list[str]:
    values = product.get(field)
    if not isinstance(values, list):
        raise ValueError(f"{field} must be an array: {product.get('id')}")
    if any(not isinstance(value, str) or not normalize_term(value) for value in values):
        raise ValueError(f"{field} must contain only non-empty strings: {product.get('id')}")
    return values


def _adapter_identity(value: str) -> str:
    return value.casefold()


def _repository_identity(value: str) -> str:
    return value.rstrip("/").casefold()


def product_terms(product: dict, *, include_contextual: bool = True) -> list[str]:
    values = [product["id"], product["display_name"], *_alias_terms(product, "aliases")]
    if include_contextual:
        values.extend(_alias_terms(product, "contextual_aliases"))
    seen: set[str] = set()
    terms: list[str] = []
    for value in values:
        normalized = normalize_term(value)
        if normalized not in seen:
            seen.add(normalized)
            terms.append(value)
    return terms


def _contains_phrase(normalized_query: str, normalized_term: str) -> bool:
    if not normalized_term:
        return False
    if any(ord(character) > 127 for character in normalized_term):
        return normalized_term in normalized_query
    pattern = r"(?<![a-z0-9])" + re.escape(normalized_term).replace(r"\ ", r"\s+")
    pattern += r"(?![a-z0-9])"
    return re.search(pattern, normalized_query) is not None


def _contextual_match(normalized_query: str, normalized_term: str) -> bool:
    if normalized_query == normalized_term:
        return True
    escaped = re.escape(normalized_term).replace(r"\ ", r"\s+")
    english_prefix = (
        r"(?:in|inside|from|using|use|open|launch|operate|control)\s+(?:the\s+)?"
    )
    english_suffix = (
        r"(?:editor|project|scene|app|software|window|workflow|file|document|composition)"
    )
    if re.search(rf"(?<![a-z0-9]){english_prefix}{escaped}(?![a-z0-9])", normalized_query):
        return True
    if re.search(rf"(?<![a-z0-9]){escaped}\s+{english_suffix}(?![a-z0-9])", normalized_query):
        return True
    chinese_prefixes = "|".join(re.escape(value) for value in ("在", "用", "使用", "打开", "启动", "操作", "控制"))
    chinese_suffixes = "|".join(
        re.escape(value)
        for value in ("中", "里", "项目", "场景", "编辑器", "软件", "窗口", "建模", "合成")
    )
    return re.search(rf"(?:{chinese_prefixes})\s*{escaped}", normalized_query) is not None or re.search(
        rf"{escaped}\s*(?:{chinese_suffixes})", normalized_query
    ) is not None


def resolve_product_intent(query: str, catalog: dict | None = None) -> dict:
    """Resolve bounded product names without selecting through broad generic words."""
    data = catalog or load_product_catalog()
    normalized_query = normalize_term(query)
    matches: list[str] = []
    for product in data["products"]:
        contextual_terms = _alias_terms(product, "contextual_aliases")
        contextual_normalized = {normalize_term(term) for term in contextual_terms}
        identity_terms = [
            product["id"],
            product["display_name"],
            *_alias_terms(product, "aliases"),
        ]
        strong_terms = [
            term for term in identity_terms if normalize_term(term) not in contextual_normalized
        ]
        strong_match = any(
            _contains_phrase(normalized_query, normalize_term(term)) for term in strong_terms
        )
        contextual_match = any(
            _contextual_match(normalized_query, normalize_term(term)) for term in contextual_terms
        )
        if strong_match or contextual_match:
            matches.append(product["id"])

    if not matches:
        status = "none"
    elif len(matches) == 1:
        status = "match"
    else:
        status = "ambiguous"
    return {"status": status, "product_ids": matches}


def validate_product_catalog(data: dict) -> None:
    if data.get("schema_version") != 1:
        raise ValueError("product catalog schema_version must be 1")
    sources = data.get("sources")
    if not isinstance(sources, dict):
        raise ValueError("product catalog is missing sources")
    released_cli = sources.get("released_cli", {})
    core_catalog = sources.get("core_catalog", {})
    if released_cli.get("repository") != "https://github.com/dcc-mcp/dcc-mcp-core":
        raise ValueError("released CLI must use the official dcc-mcp-core repository")
    if released_cli.get("tag") != f"v{released_cli.get('version')}":
        raise ValueError("released CLI tag must match its version")
    if CORE_COMMIT_RE.fullmatch(str(released_cli.get("commit", ""))) is None:
        raise ValueError("released CLI must be pinned to a full release commit")
    if core_catalog.get("repository") != "https://github.com/dcc-mcp/dcc-mcp-core":
        raise ValueError("core catalog must use the official dcc-mcp-core repository")
    if CORE_COMMIT_RE.fullmatch(str(core_catalog.get("commit", ""))) is None:
        raise ValueError("core catalog must be pinned to a full immutable commit")
    if core_catalog.get("path") != "dcc-mcp-catalog.yml":
        raise ValueError("core catalog path must be dcc-mcp-catalog.yml")
    if core_catalog.get("commit") != released_cli.get("commit"):
        raise ValueError("core catalog must be pinned to the released CLI commit")
    products = data.get("products")
    if not isinstance(products, list) or not products:
        raise ValueError("product catalog must contain products")
    if released_cli.get("reported_total") != len(products):
        raise ValueError("released CLI product total differs from the catalog")
    cli_types = released_cli.get("dcc_types")
    if not isinstance(cli_types, list) or not cli_types:
        raise ValueError("released CLI source snapshot is missing dcc_types")

    ids: set[str] = set()
    adapters: set[str] = set()
    repositories: set[str] = set()
    owner_by_term: dict[str, str] = {}
    for product in products:
        product_id = product.get("id")
        if not isinstance(product_id, str) or PRODUCT_ID_RE.fullmatch(product_id) is None:
            raise ValueError(f"invalid canonical product id: {product_id!r}")
        if product_id in ids:
            raise ValueError(f"duplicate canonical product id: {product_id}")
        ids.add(product_id)

        adapter = product.get("adapter")
        repository = product.get("repository")
        if not isinstance(adapter, str) or not adapter:
            raise ValueError(f"duplicate or invalid adapter: {adapter!r}")
        if not isinstance(repository, str) or not repository:
            raise ValueError(f"duplicate or invalid repository: {repository!r}")
        adapter_identity = _adapter_identity(adapter)
        repository_identity = _repository_identity(repository)
        if adapter_identity in adapters:
            raise ValueError(f"duplicate or invalid adapter: {adapter!r}")
        if repository_identity in repositories:
            raise ValueError(f"duplicate or invalid repository: {repository!r}")
        if not repository_identity.startswith("https://github.com/dcc-mcp/"):
            raise ValueError(f"product repository is not organization-owned: {repository}")
        if repository_identity.split("/")[-1] != adapter_identity:
            raise ValueError(f"adapter and repository identity differ: {adapter}, {repository}")
        adapters.add(adapter_identity)
        repositories.add(repository_identity)

        if not product.get("display_name") or not product.get("family"):
            raise ValueError(f"product identity is incomplete: {product_id}")
        if not isinstance(product.get("catalog_install_available"), bool):
            raise ValueError(f"catalog_install_available must be boolean: {product_id}")
        examples = product.get("intent_examples", {})
        if not examples.get("en") or not examples.get("zh"):
            raise ValueError(f"bilingual intent examples are required: {product_id}")

        contextual_aliases = _alias_terms(product, "contextual_aliases")
        contextual = {normalize_term(term) for term in contextual_aliases}
        for term in product_terms(product):
            normalized = normalize_term(term)
            if normalized in GENERIC_HIJACK_TERMS:
                raise ValueError(f"generic discovery term is forbidden: {term!r}")
            previous = owner_by_term.get(normalized)
            if previous is not None and previous != product_id:
                raise ValueError(
                    f"discovery term {term!r} is shared by {previous!r} and {product_id!r}"
                )
            owner_by_term[normalized] = product_id
        for term in contextual:
            if term not in owner_by_term:
                raise ValueError(f"contextual alias is not discoverable: {product_id}, {term}")

    routing = data.get("ui_routing", {})
    if routing.get("canonical_provider") != "dcc-cua":
        raise ValueError("DCC-CUA must be the canonical application UI provider")
    if {normalize_term(term) for term in routing.get("search_terms", [])} != {
        "dcc cua",
        "ui control",
    }:
        raise ValueError("UI routing must expose both DCC-CUA and ui-control")
    if routing.get("typed_tools_first") is not True:
        raise ValueError("typed DCC-MCP tools must be preferred before application UI")
    if routing.get("default_for_dcc_mcp_application_ui") is not True:
        raise ValueError("DCC-CUA must be the default DCC-MCP application UI route")
    if routing.get("scope") != [
        "DCC application UI",
        "browser UI",
        "non-DCC application UI",
    ]:
        raise ValueError("DCC-CUA scope must cover DCC, browser, and non-DCC application UI")
    if routing.get("conditional_skill_route") != "dcc-cua":
        raise ValueError("conditional application UI routing must load dcc-cua")
    if routing.get("hard_skill_dependency") is not False:
        raise ValueError("conditional UI routing must not load DCC-CUA for every typed task")
    if routing.get("forbidden_fallbacks") != [
        "Codex/OpenAI Computer Use",
        "computer-use Skill",
        "@oai/sky",
        "Browser plugin",
        "Chrome plugin",
    ]:
        raise ValueError("generic UI providers must remain forbidden fallbacks")
    if routing.get("required_attestation") != ["provider", "runtime", "pid", "hwnd"]:
        raise ValueError("UI routing requires exact provider/runtime/PID/HWND attestation")
    if routing.get("action_contract") != [
        "fresh observation before every state-dependent action",
        "latest snapshot or semantic reference only",
        "post-action state readback",
        "stop on interruption or permission failure",
    ]:
        raise ValueError("DCC-CUA observation and verification contract is incomplete")
    if routing.get("human_handoff") != [
        "CAPTCHA",
        "authentication challenge",
        "security challenge",
    ]:
        raise ValueError("DCC-CUA security challenges must require human handoff")

    if cli_types != [product["id"] for product in products]:
        raise ValueError("enriched product identities differ from the released CLI snapshot")

    for product in products:
        for language in ("en", "zh"):
            result = resolve_product_intent(product["intent_examples"][language], data)
            if result != {"status": "match", "product_ids": [product["id"]]}:
                raise ValueError(
                    f"{language} intent does not resolve uniquely for {product['id']}: {result}"
                )


def validate_released_cli_snapshot(catalog: dict, cli_version: str, payload: dict) -> None:
    """Check a live released CLI result against the enriched discovery identities."""
    expected_source = catalog["sources"]["released_cli"]
    if cli_version != expected_source["version"]:
        raise ValueError(
            f"released CLI version differs: expected {expected_source['version']}, got {cli_version}"
        )
    rows = payload.get("dcc_types")
    if not isinstance(rows, list) or payload.get("total") != len(rows):
        raise ValueError("released CLI returned an invalid dcc_types payload")
    if [row.get("dcc_type") for row in rows] != expected_source["dcc_types"]:
        raise ValueError("released CLI product identities differ from PRODUCTS.json")

    products = {product["id"]: product for product in catalog["products"]}
    for row in rows:
        product = products[row["dcc_type"]]
        adapters = row.get("adapters")
        if not isinstance(adapters, list) or not adapters:
            raise ValueError(f"released CLI product has no adapter: {row['dcc_type']}")
        matches = [
            adapter
            for adapter in adapters
            if adapter.get("name", "").casefold() == product["adapter"].casefold()
        ]
        if len(matches) != 1:
            raise ValueError(f"released CLI adapter identity differs: {row['dcc_type']}")
        adapter = matches[0]
        if adapter.get("url", "").rstrip("/").casefold() != product["repository"].rstrip("/").casefold():
            raise ValueError(f"released CLI repository differs: {row['dcc_type']}")
        if adapter.get("catalog_install_available") is not product["catalog_install_available"]:
            raise ValueError(f"released CLI install availability differs: {row['dcc_type']}")


def validate_released_source_snapshot(catalog: dict, snapshot: dict) -> None:
    """Bind the claimed CLI version and catalog to an observed release ref."""
    if not isinstance(snapshot, dict):
        raise ValueError("released source snapshot must be an object")
    expected = catalog["sources"]["released_cli"]
    for field in ("repository", "tag", "commit"):
        if snapshot.get(field) != expected[field]:
            raise ValueError(f"released CLI {field} differs from the authoritative release")


def validate_released_core_runtime(
    catalog: dict, *, installed_version: str, resolved_commit: str
) -> None:
    """Require the installed Core and resolved release ref to match one catalog contract."""
    released = catalog["sources"]["released_cli"]
    core_catalog = catalog["sources"]["core_catalog"]
    if core_catalog["repository"] != released["repository"]:
        raise ValueError("released Core repository differs from the immutable catalog source")
    if core_catalog["commit"] != released["commit"]:
        raise ValueError("released Core commit differs from the immutable catalog source")
    if installed_version != released["version"]:
        raise ValueError(
            f"installed Core version differs: expected {released['version']}, got {installed_version}"
        )
    if resolved_commit != released["commit"]:
        raise ValueError(
            f"released Core commit differs: expected {released['commit']}, got {resolved_commit}"
        )


def _load_workflow_yaml(workflow: str, relative: str) -> dict:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - validators install catalog deps first
        raise ValueError("PyYAML is required to validate released Core workflows") from exc

    class UniqueKeyLoader(yaml.SafeLoader):
        pass

    UniqueKeyLoader.yaml_implicit_resolvers = {
        key: [
            (tag, expression)
            for tag, expression in resolvers
            if tag != "tag:yaml.org,2002:bool"
        ]
        for key, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
    }
    UniqueKeyLoader.add_implicit_resolver(
        "tag:yaml.org,2002:bool",
        re.compile(r"^(?:false|False|FALSE|true|True|TRUE)$"),
        list("fFtT"),
    )

    def construct_unique_mapping(loader, node, deep=False):
        loader.flatten_mapping(node)
        mapping = {}
        for key_node, value_node in node.value:
            key = loader.construct_object(key_node, deep=deep)
            if key in mapping:
                raise ValueError(f"workflow contains duplicate YAML key {key!r}: {relative}")
            mapping[key] = loader.construct_object(value_node, deep=deep)
        return mapping

    UniqueKeyLoader.add_constructor(
        yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
        construct_unique_mapping,
    )
    try:
        loaded = yaml.load(workflow, Loader=UniqueKeyLoader)
    except (yaml.YAMLError, ValueError) as exc:
        raise ValueError(f"invalid workflow YAML: {relative}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ValueError(f"workflow root must be a mapping: {relative}")
    return loaded


def _workflow_structure_digest(value: object) -> str:
    """Hash parsed execution structure so every job and step is fail-closed."""
    payload = json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _workflow_shell_text(command: str) -> str:
    command = re.sub(r"(?:\\|`|\^)\r?\n[ \t]*", "", command)
    executable_lines: list[str] = []
    heredoc_delimiter: str | None = None
    heredoc_pattern = re.compile(r"<<-?\s*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\1")
    for line in command.splitlines():
        if heredoc_delimiter is not None:
            if line.strip() == heredoc_delimiter:
                heredoc_delimiter = None
            continue
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        executable_lines.append(line)
        match = heredoc_pattern.search(line)
        if match is not None:
            heredoc_delimiter = match.group(2)
    if heredoc_delimiter is not None:
        raise ValueError("workflow command contains an unterminated heredoc")
    return "\n".join(executable_lines)


def _workflow_shell_segments(command: str) -> list[list[str]]:
    executable = _workflow_shell_text(command).replace("\n", " ; ")
    if not executable:
        return []
    lexer = shlex.shlex(executable, posix=True, punctuation_chars="&|;(){}")
    lexer.commenters = "#"
    lexer.whitespace_split = True
    try:
        tokens = list(lexer)
    except ValueError as exc:
        raise ValueError(f"workflow command is not lexically closed: {exc}") from exc

    segments: list[list[str]] = []
    segment: list[str] = []
    for token in tokens:
        if token and set(token) <= WORKFLOW_COMMAND_BOUNDARY_CHARS:
            if segment:
                segments.append(segment)
                segment = []
            continue
        segment.append(token)
    if segment:
        segments.append(segment)
    return segments


def _workflow_command_head(segment: list[str]) -> str | None:
    tokens = list(segment)
    while tokens and tokens[0].casefold() in WORKFLOW_SHELL_CONTROL_TOKENS:
        tokens.pop(0)
    if not tokens or tokens[0].casefold() in {"case", "for"}:
        return None
    while tokens and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", tokens[0], re.DOTALL):
        tokens.pop(0)
    return tokens[0] if tokens else None


def _workflow_trigger_is_reachable(trigger: str, config: object) -> bool:
    if trigger == "schedule":
        return isinstance(config, list) and bool(config) and all(
            isinstance(entry, dict)
            and isinstance(entry.get("cron"), str)
            and bool(entry["cron"].strip())
            for entry in config
        )
    if config is None:
        return True
    if not isinstance(config, dict):
        return False
    for key in (
        "branches",
        "branches-ignore",
        "paths",
        "paths-ignore",
        "tags",
        "tags-ignore",
    ):
        if key not in config:
            continue
        values = config[key]
        if not isinstance(values, list) or not values:
            return False
        if any(not isinstance(value, str) or not value.strip() for value in values):
            return False
    return True


def _validate_workflow_execution_surface(
    value: str,
    relative: str,
    job_name: str,
    *,
    reject_indirect_head: bool,
    surface_kind: str,
) -> None:
    if surface_kind == "uses":
        normalized_action = value.casefold().replace("_", "-")
        install_action = re.search(
            r"(?:^|[/@-])(?:pip(?:[0-9.]*)?|pipx|uv|vx)(?:[/@-]|$)",
            normalized_action,
        )
        if "dcc-mcp-core" in normalized_action or install_action is not None:
            raise ValueError(f"{relative} job {job_name} contains a competing install action")
        return

    executable = _workflow_shell_text(value)
    function_pattern = re.compile(
        r"(?im)^\s*(?:function\s+)?[A-Za-z_][A-Za-z0-9_]*\s*(?:\(\s*\))?\s*\{"
    )
    if function_pattern.search(executable):
        raise ValueError(f"{relative} job {job_name} contains shell function indirection")

    for segment in _workflow_shell_segments(value):
        normalized = [token.casefold().replace("_", "-") for token in segment]
        if any(token == "scripts/setup-released-core.py" for token in normalized):
            raise ValueError(f"{relative} job {job_name} contains a non-authoritative setup route")

        head = _workflow_command_head(segment)
        if head is None:
            continue
        normalized_head = Path(head).name.casefold().removesuffix(".exe")
        if reject_indirect_head and (
            "$" in head or "`" in head or re.search(r"%[^%]+%", head)
        ):
            raise ValueError(f"{relative} job {job_name} contains an indirect command head")
        if normalized_head in WORKFLOW_INDIRECT_COMMANDS:
            raise ValueError(f"{relative} job {job_name} contains shell command indirection")

        package_manager = normalized_head in WORKFLOW_PACKAGE_MANAGERS or re.fullmatch(
            r"pip[0-9]+(?:\.[0-9]+)*",
            normalized_head,
        ) is not None
        python_pip = (
            re.fullmatch(r"(?:python(?:\d+(?:\.\d+)?)?|py)", normalized_head) is not None
            and any(
                normalized[index : index + 2] in (["-m", "pip"], ["-m", "ensurepip"])
                for index in range(max(0, len(normalized) - 1))
            )
        )
        core_package = any(token.startswith("dcc-mcp-core") for token in normalized)
        dependency_action = any(token in {"add", "install", "sync"} for token in normalized)
        if package_manager or python_pip or (core_package and dependency_action):
            raise ValueError(f"{relative} job {job_name} contains a competing Core install route")


def _validate_released_core_job(
    workflow: dict,
    relative: str,
    job_name: str,
    expected_command: str,
) -> None:
    jobs = workflow.get("jobs")
    if not isinstance(jobs, dict):
        raise ValueError(f"released Core workflow has no jobs mapping: {relative}")
    job = jobs.get(job_name)
    if not isinstance(job, dict):
        raise ValueError(f"released Core workflow is missing required job: {job_name}")
    expected_controls = RELEASED_CORE_JOB_EXECUTION_CONTROLS[relative][job_name]
    actual_controls = {
        key: value for key, value in job.items() if key in WORKFLOW_EXECUTION_CONTROL_KEYS
    }
    if actual_controls != expected_controls:
        raise ValueError(
            f"{relative} job {job_name} execution controls differ from the frozen contract"
        )
    steps = job.get("steps")
    if not isinstance(steps, list):
        raise ValueError(f"{relative} job {job_name} has no executable steps")

    run_steps: list[dict] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"{relative} job {job_name} step {index} must be a mapping")
        if "run" in step:
            if not isinstance(step["run"], str):
                raise ValueError(f"{relative} job {job_name} step {index} run must be text")
            run_steps.append(step)

    if not run_steps or run_steps[0]["run"].strip() != expected_command:
        raise ValueError(
            f"{relative} job {job_name} must execute the released Core setup first"
        )

    authoritative = [step for step in run_steps if step["run"].strip() == expected_command]
    if len(authoritative) != 1:
        raise ValueError(
            f"{relative} job {job_name} must contain exactly one released Core setup step"
        )
    setup_step = authoritative[0]
    if setup_step != {"run": expected_command}:
        raise ValueError(
            f"{relative} job {job_name} weakens the released Core setup execution controls"
        )

    for step in steps:
        if step is setup_step:
            continue
        execution_surfaces = [
            (step.get("run"), True, "run"),
            (step.get("uses"), False, "uses"),
        ]
        environment = step.get("env", {})
        if not isinstance(environment, dict):
            raise ValueError(f"{relative} job {job_name} step env must be a mapping")
        execution_surfaces.extend((value, False, "env") for value in environment.values())
        for value, reject_indirect_head, surface_kind in execution_surfaces:
            if value is None:
                continue
            if not isinstance(value, str):
                raise ValueError(
                    f"{relative} job {job_name} execution surface must be text"
                )
            _validate_workflow_execution_surface(
                value,
                relative,
                job_name,
                reject_indirect_head=reject_indirect_head,
                surface_kind=surface_kind,
            )


def validate_released_core_workflows(catalog: dict, workflows: dict[str, str]) -> None:
    """Require one structurally executable catalog-derived Core setup per job."""
    released = catalog["sources"]["released_cli"]
    version_pin = re.compile(r"(?im)^\s*DCC_MCP_CORE_VERSION\s*:\s*['\"]?([^'\"\s]+)")
    commit_pin = re.compile(r"(?im)^\s*DCC_MCP_CORE_COMMIT\s*:\s*['\"]?([0-9a-f]+)")

    if set(workflows) != set(RELEASED_CORE_WORKFLOW_JOBS):
        raise ValueError("released Core workflow set differs from the required contract")
    for relative, commands in RELEASED_CORE_WORKFLOW_COMMANDS.items():
        workflow_text = workflows[relative]
        for match in version_pin.finditer(workflow_text):
            if match.group(1) != released["version"]:
                raise ValueError(f"workflow has a conflicting released Core version: {relative}")
            raise ValueError(f"workflow duplicates the catalog-derived Core version: {relative}")
        for match in commit_pin.finditer(workflow_text):
            if match.group(1) != released["commit"]:
                raise ValueError(f"workflow has a conflicting released Core commit: {relative}")
            raise ValueError(f"workflow duplicates the catalog-derived Core commit: {relative}")
        workflow = _load_workflow_yaml(workflow_text, relative)
        if workflow.get("defaults") is not None:
            raise ValueError(f"workflow changes the released Core default execution context: {relative}")
        if workflow.get("env") != RELEASED_CORE_WORKFLOW_ENVIRONMENT[relative]:
            raise ValueError(f"workflow environment differs from the frozen contract: {relative}")
        triggers = workflow.get("on")
        if triggers != RELEASED_CORE_WORKFLOW_REQUIRED_TRIGGERS[relative]:
            raise ValueError(f"workflow triggers differ from the exact contract: {relative}")
        if any(
            not _workflow_trigger_is_reachable(trigger, config)
            for trigger, config in triggers.items()
        ):
            raise ValueError(f"workflow contains an unreachable trigger: {relative}")

        jobs = workflow.get("jobs")
        expected_job_digests = RELEASED_CORE_WORKFLOW_JOB_DIGESTS[relative]
        if not isinstance(jobs, dict) or set(jobs) != set(expected_job_digests):
            raise ValueError(f"workflow jobs differ from the exact contract: {relative}")
        for job_name, expected_digest in expected_job_digests.items():
            if _workflow_structure_digest(jobs[job_name]) != expected_digest:
                raise ValueError(
                    f"{relative} job {job_name} execution topology differs from the exact contract"
                )
        for job_name, expected_command in commands.items():
            _validate_released_core_job(workflow, relative, job_name, expected_command)


def validate_core_catalog_snapshot(catalog: dict, payload: dict) -> None:
    """Check products against the adapter entries in an immutable Core catalog."""
    if not isinstance(payload, dict):
        raise ValueError("immutable Core catalog must be an object")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("immutable Core catalog has no entries array")

    authoritative: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("immutable Core catalog entry must be an object")
        tags = entry.get("tags", [])
        url = entry.get("url", "")
        if "adapter" not in tags or not isinstance(url, str):
            continue
        repository_identity = _repository_identity(url)
        if not repository_identity.startswith("https://github.com/dcc-mcp/"):
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("immutable Core adapter entry has no name")
        identity = _adapter_identity(name)
        if identity in authoritative:
            raise ValueError(f"immutable Core catalog repeats adapter: {name}")
        authoritative[identity] = entry

    products = {
        _adapter_identity(product["adapter"]): product for product in catalog["products"]
    }
    if set(authoritative) != set(products):
        raise ValueError("immutable Core adapter identities differ from PRODUCTS.json")

    for identity, product in products.items():
        entry = authoritative[identity]
        repository = entry.get("url")
        if _repository_identity(repository) != _repository_identity(product["repository"]):
            raise ValueError(f"immutable Core repository differs: {product['id']}")
        dcc_types = entry.get("dcc")
        if not isinstance(dcc_types, list) or any(
            not isinstance(value, str) or not value for value in dcc_types
        ):
            raise ValueError(f"immutable Core dcc identity is invalid: {product['id']}")
        if product["id"].casefold() not in {value.casefold() for value in dcc_types}:
            raise ValueError(f"immutable Core product identity differs: {product['id']}")
        if bool(entry.get("install")) is not product["catalog_install_available"]:
            raise ValueError(f"immutable Core install availability differs: {product['id']}")


def plugin_description(catalog: dict) -> str:
    count = len(catalog["products"])
    return (
        f"Discover and control {count} released creative applications with typed DCC-MCP "
        "tools; route scoped application UI through project-owned DCC-CUA/ui-control."
    )


def plugin_keywords(catalog: dict) -> list[str]:
    values = [
        "dcc",
        "mcp",
        "DCC-CUA",
        "ui-control",
        *(term for product in catalog["products"] for term in product_terms(product)),
    ]
    seen: set[str] = set()
    keywords: list[str] = []
    for value in values:
        normalized = normalize_term(value)
        if normalized not in seen:
            seen.add(normalized)
            keywords.append(value)
    return keywords


def skill_description(catalog: dict) -> str:
    return (
        f"Default DCC-MCP router for {len(catalog['products'])} released creative products. "
        "Use typed DCC-MCP tools first. For application UI, including browsers and non-DCC "
        "apps, DCC-CUA and ui-control name the same project-owned route and explicit DCC-CUA "
        "requests never fall back to generic Computer Use providers."
    )


def skill_search_hint(catalog: dict) -> str:
    products = " ".join(term for product in catalog["products"] for term in product_terms(product))
    return (
        "DCC-MCP typed tool discovery create edit inspect simulate animate render composite "
        "export automate 操作 控制 创建 编辑 检查 动画 渲染 合成 导出; released products: "
        f"{products}; application UI route: DCC-CUA dcc cua ui-control browser UI exact PID "
        "HWND fresh observation latest snapshot post-action readback no generic Computer Use"
    )


def skill_tags(catalog: dict) -> list[str]:
    return [
        "dcc",
        "dcc-mcp",
        "typed-tools",
        "dcc-cua",
        "ui-control",
        *(product["id"] for product in catalog["products"]),
    ]


def ui_route_prompt(catalog: dict) -> str:
    return (
        "Use $dcc-mcp for released-product discovery and typed DCC-MCP tools first. For any "
        "DCC-MCP application UI behavior, including browser and non-DCC application UI, use "
        "project-owned DCC-CUA through ui-control; explicit DCC-CUA requests are a hard "
        "provider boundary. Before the first UI observation or input report "
        "provider=dcc-cua, runtime, exact PID, and exact HWND. Use a fresh observation and "
        "latest snapshot or semantic reference for each action, verify with post-action "
        "readback, stop on interruption or permission failure, and hand CAPTCHA, "
        "authentication, or security challenges to the human. Never substitute generic "
        "Codex/OpenAI Computer Use, computer-use, @oai/sky, Browser, or Chrome plugins."
    )

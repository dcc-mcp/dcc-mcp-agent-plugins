"""Canonical released-product discovery and routing contracts."""

from __future__ import annotations

import json
import re
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
        r"(?:in|inside|with|using|use|open|launch|operate|control)\s+(?:the\s+)?"
    )
    english_suffix = (
        r"(?:editor|project|scene|app|software|window|workflow|file|document|composition)"
    )
    if re.search(rf"(?<![a-z0-9]){english_prefix}{escaped}(?![a-z0-9])", normalized_query):
        return True
    if re.search(rf"(?<![a-z0-9]){escaped}\s+{english_suffix}(?![a-z0-9])", normalized_query):
        return True
    chinese_prefixes = ("在", "用", "使用", "打开", "启动", "操作", "控制")
    chinese_suffixes = ("中", "里", "项目", "场景", "编辑器", "软件", "窗口", "建模", "合成")
    return any(prefix + normalized_term in normalized_query for prefix in chinese_prefixes) or any(
        normalized_term + suffix in normalized_query for suffix in chinese_suffixes
    )


def resolve_product_intent(query: str, catalog: dict | None = None) -> dict:
    """Resolve bounded product names without selecting through broad generic words."""
    data = catalog or load_product_catalog()
    normalized_query = normalize_term(query)
    matches: list[str] = []
    for product in data["products"]:
        contextual_terms = _alias_terms(product, "contextual_aliases")
        contextual_normalized = {normalize_term(term) for term in contextual_terms}
        strong_terms = [product["display_name"], *_alias_terms(product, "aliases")]
        if normalize_term(product["id"]) not in contextual_normalized:
            strong_terms.insert(0, product["id"])
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
    if core_catalog.get("repository") != "https://github.com/dcc-mcp/dcc-mcp-core":
        raise ValueError("core catalog must use the official dcc-mcp-core repository")
    if CORE_COMMIT_RE.fullmatch(str(core_catalog.get("commit", ""))) is None:
        raise ValueError("core catalog must be pinned to a full immutable commit")
    if core_catalog.get("path") != "dcc-mcp-catalog.yml":
        raise ValueError("core catalog path must be dcc-mcp-catalog.yml")
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

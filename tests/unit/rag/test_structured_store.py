from app.rag.structured_store import StructuredKnowledgeStore

_FACTS = {
    "version": 1,
    "facts": [
        {"category": "policy", "key": "refund_policy_version", "value": "v3 (2026-01-01 시행)"},
        {"category": "contact", "key": "customer_center", "value": "1588-0000"},
    ],
}


def test_returns_exact_value_for_known_category_and_key() -> None:
    store = StructuredKnowledgeStore(_FACTS)

    value = store.get("contact", "customer_center")

    assert value == "1588-0000"


def test_returns_none_for_unknown_key() -> None:
    store = StructuredKnowledgeStore(_FACTS)

    value = store.get("policy", "does_not_exist")

    assert value is None


def test_loads_from_json_file(tmp_path) -> None:
    import json

    facts_path = tmp_path / "service_facts.json"
    facts_path.write_text(json.dumps(_FACTS, ensure_ascii=False), encoding="utf-8")

    store = StructuredKnowledgeStore.from_file(facts_path)

    assert store.get("policy", "refund_policy_version") == "v3 (2026-01-01 시행)"


def test_empty_store_returns_none_for_any_key() -> None:
    store = StructuredKnowledgeStore({"version": 1, "facts": []})

    assert store.get("policy", "refund_policy_version") is None

import hashlib

import pytest
from conceptualize_runtime.adapters import ConversationAdapter, RepositoryAdapter
from conceptualize_runtime.context import ContextUnit, ContextUnitRuntime
from conceptualize_runtime.economics import ModelPricing, estimate_cost, load_pricing


def test_conversation_adapter_preserves_message_order_metadata_and_parent_links():
    adapter = ConversationAdapter()
    units = adapter.ingest(
        {
            "conversations": [
                {
                    "id": "decision-1",
                    "title": "Storage choice",
                    "messages": [
                        {"id": "m1", "role": "user", "content": "Use MySQL initially."},
                        {
                            "id": "m2",
                            "role": "assistant",
                            "content": "We will use PostgreSQL for JSON support.",
                            "parent_id": "m1",
                        },
                    ],
                }
            ]
        }
    )

    messages = [unit for unit in units if unit.source_type == "message"]
    conversation = next(unit for unit in units if unit.source_type == "conversation")
    assert [unit.metadata["order"] for unit in messages] == [0, 1]
    assert conversation.metadata["title"] == "Storage choice"
    assert messages[1].parent_id == messages[0].id
    assert {r["kind"] for r in messages[1].relationships} == {"member_of", "follows", "reply_to"}
    exported = adapter.export(units)
    assert [m["id"] for m in exported["conversations"][0]["messages"]] == ["m1", "m2"]


def test_context_search_prefers_exact_phrase_and_preserves_source_provenance():
    units = ConversationAdapter().ingest(
        {
            "conversations": [
                {
                    "id": "decisions",
                    "messages": [
                        {"id": "m1", "role": "user", "content": "We chose PostgreSQL for JSON support."},
                        {"id": "m2", "role": "user", "content": "Next week discuss the sidebar layout."},
                    ],
                }
            ]
        }
    )
    result = ContextUnitRuntime(units).search("PostgreSQL JSON support")

    assert result[0]["unit"].id.endswith("/message:m1")
    assert result[0]["score"] > 0
    assert result[0]["reasons"]


def test_context_search_does_not_rank_common_stopwords_as_context_signals():
    units = ConversationAdapter().ingest(
        {
            "conversations": [
                {"id": "a", "messages": [{"id": "m1", "role": "user", "content": "The plan and the budget."}]},
                {"id": "b", "messages": [{"id": "m2", "role": "user", "content": "PostgreSQL stores conversation context."}]},
            ]
        }
    )
    matches = ContextUnitRuntime(units).search("Which is the best context and?")

    assert all(row["unit"].id != "conversation:a/message:m1" for row in matches)


def test_generic_pack_returns_delta_and_references_unchanged_units():
    units = ConversationAdapter().ingest(
        {
            "conversations": [
                {
                    "id": "decisions",
                    "messages": [
                        {"id": "m1", "role": "assistant", "content": "Use PostgreSQL because JSONB supports metadata."}
                    ],
                }
            ]
        }
    )
    runtime = ContextUnitRuntime(units)
    first = runtime.pack("PostgreSQL JSONB metadata", 200)
    second = runtime.pack("PostgreSQL JSONB metadata", 200, history=first["deliveries"])

    assert "PostgreSQL" in first["context"]
    assert second["context"] == ""
    assert second["metrics"]["duplicate_tokens_avoided"] > 0
    assert second["previous_context"][0]["unchanged"] is True


def test_generic_disclosure_levels_reveal_progressively_and_explain_scores():
    units = ConversationAdapter().ingest(
        {
            "conversations": [
                {
                    "id": "c",
                    "messages": [
                        {
                            "id": "m",
                            "role": "assistant",
                            "content": "Chosen database: PostgreSQL. Implementation note: keep the original migration stable.",
                        }
                    ],
                }
            ]
        }
    )
    runtime = ContextUnitRuntime(units)
    mapped = runtime.pack("PostgreSQL", 200, source_types={"message"}, level="map")
    structured = runtime.pack("PostgreSQL", 200, source_types={"message"}, level="structure")
    source = runtime.pack("PostgreSQL", 200, source_types={"message"}, level="source")

    assert "Chosen database" not in mapped["context"]
    assert "Chosen database" in structured["context"]
    assert "Implementation note" not in structured["context"]
    assert "Implementation note" in source["context"]
    item = structured["selection"][0]
    assert item["score"] == sum(reason["weight"] for reason in item["reasons"])
    assert any(reason["signal"] == "exact_phrase" for reason in item["reasons"])
    source_after_structure = runtime.pack(
        "PostgreSQL",
        200,
        source_types={"message"},
        level="source",
        history=structured["deliveries"],
    )
    assert "Implementation note" in source_after_structure["context"]
    assert source_after_structure["invalidated_units"] == []


def test_generic_score_weights_can_be_overridden_and_unknown_weights_fail():
    units = ConversationAdapter().ingest(
        {"conversations": [{"id": "c", "messages": [{"id": "m", "role": "user", "content": "alpha beta"}]}]}
    )
    result = ContextUnitRuntime(units).pack(
        "alpha beta", 200, source_types={"message"}, score_weights={"exact_phrase": 50}
    )
    assert any(reason["signal"] == "exact_phrase" and reason["weight"] == 50 for reason in result["selection"][0]["reasons"])
    assert result["score_weights"]["exact_phrase"] == 50
    with pytest.raises(ValueError, match="score weights"):
        ContextUnitRuntime(units).pack("alpha", 200, score_weights={"mystery": 10})


def test_repository_adapter_maps_existing_file_records_to_generic_units():
    units = RepositoryAdapter().adapt(
        {
            "src/main.py": {
                "content": "print('hello')",
                "hash": hashlib.sha256(b"print('hello')").hexdigest(),
                "language": "python",
            }
        }
    )

    assert len(units) == 1
    assert units[0].source_type == "repository_file"
    assert units[0].source_id == "src/main.py"
    assert units[0].content == "print('hello')"


def test_repository_adapter_structure_discloses_signatures_before_source_bodies():
    source = "def calculate_total(items):\n    hidden_implementation = sum(items)\n    return hidden_implementation\n"
    units = RepositoryAdapter().adapt(
        {
            "src/totals.py": {
                "content": source,
                "hash": hashlib.sha256(source.encode()).hexdigest(),
                "language": "python",
                "symbols": [
                    {"name": "calculate_total", "signature": "def calculate_total(items)", "start_line": 1}
                ],
            }
        }
    )
    runtime = ContextUnitRuntime(units)
    structure = runtime.pack(
        "calculate_total",
        300,
        source_types={"repository_file"},
        level="structure",
    )

    assert "def calculate_total(items)" in structure["context"]
    assert "hidden_implementation" not in structure["context"]


def test_context_unit_hash_changes_with_content_and_pricing_is_explicit(tmp_path):
    original = ContextUnit(id="x", source_type="arbitrary_text", source_id="x", content="one")
    changed = ContextUnit(id="x", source_type="arbitrary_text", source_id="x", content="two")
    assert original.content_hash != changed.content_hash

    pricing = ModelPricing(
        model="test-model",
        version="fixture-2026-01",
        input_per_million=1.0,
        cached_input_per_million=0.2,
        output_per_million=4.0,
    )
    estimate = estimate_cost(pricing, input_tokens=100, cached_input_tokens=25, output_tokens=10)
    assert estimate["model"] == "test-model"
    assert estimate["pricing_version"] == "fixture-2026-01"
    assert estimate["estimated_cost"] == pytest.approx((75 + 5 + 40) / 1_000_000)
    unavailable = estimate_cost(pricing, input_tokens=None, cached_input_tokens=None, output_tokens=10)
    assert unavailable["estimated_cost"] is None
    with pytest.raises(ValueError):
        estimate_cost(pricing, input_tokens=1, cached_input_tokens=2, output_tokens=0)
    config = tmp_path / "pricing.json"
    config.write_text(
        '{"models":[{"model":"test-model","version":"fixture-2026-01",'
        '"input_per_million":1,"cached_input_per_million":0.2,"output_per_million":4}]}',
        encoding="utf-8",
    )
    assert load_pricing(config)["test-model"] == pricing

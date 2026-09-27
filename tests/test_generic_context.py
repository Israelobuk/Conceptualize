import hashlib

import pytest
from conceptualize_runtime.adapters import ConversationAdapter, RepositoryAdapter
from conceptualize_runtime.context import ContextUnit, ContextUnitRuntime
from conceptualize_runtime.economics import ModelPricing, estimate_cost, load_pricing
from conceptualize_runtime.runtime import ContextRuntime


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


def test_conversation_pack_does_not_expand_every_sibling_message():
    units = ConversationAdapter().ingest(
        {
            "conversations": [
                {
                    "id": "long-history",
                    "messages": [
                        {"id": "decision", "role": "user", "content": "Use IndexedDB for offline inspection records and attachments."},
                        {"id": "noise-1", "role": "user", "content": "The icon should be green."},
                        {"id": "noise-2", "role": "user", "content": "We may pilot in the North region."},
                        {"id": "noise-3", "role": "assistant", "content": "The release date is not final."},
                        {"id": "noise-4", "role": "user", "content": "Marketing will own the announcement."},
                    ],
                }
            ]
        }
    )

    result = ContextUnitRuntime(units).pack(
        "IndexedDB offline inspection records", 1000, source_types={"message"}
    )

    assert "Use IndexedDB" in result["context"]
    assert "green" not in result["context"]
    assert "North region" not in result["context"]
    assert result["metrics"]["selected_units"] == 1


def test_conversation_pack_omits_low_relevance_lexical_noise_but_keeps_decisions():
    units = ConversationAdapter().ingest({"conversations": [{"id": "planning", "messages": [
        {"id": "decision", "role": "user", "content": "Architecture decision: keep offline drafts until authenticated upload succeeds."},
        {"id": "noise", "role": "user", "content": "Implementation meeting moved to Thursday; lunch is at noon."},
    ]}]})
    result = ContextUnitRuntime(units).pack(
        "current implementation architecture plan", 500, source_types={"message"}
    )

    assert "offline drafts" in result["context"]
    assert "lunch is at noon" not in result["context"]
    noise = next(row for row in result["selection"] if row["source_id"] == "noise")
    assert noise["status"] == "omitted"
    assert noise["omission_reason"] == "below deterministic conversation relevance floor"
    assert result["metrics"]["low_relevance_tokens_suppressed"] > 0


def test_repeated_and_quoted_conversation_messages_are_suppressed_with_provenance():
    statement = "Use SQLite for the offline cache and keep local drafts until the server confirms upload."
    units = ConversationAdapter().ingest(
        {"conversations": [{"id": "repeat", "messages": [
            {"id": "original", "role": "user", "content": statement},
            {"id": "quote", "role": "assistant", "content": f'We agreed: "{statement}"'},
            {"id": "ack", "role": "assistant", "content": "Understood."},
        ]}]}
    )
    result = ContextUnitRuntime(units).pack(
        "SQLite offline cache local drafts server upload", 500,
        source_types={"message"}, targets=["conversation:repeat/message:ack"]
    )

    assert result["context"].count("Use SQLite") == 1
    assert result["metrics"]["duplicate_tokens_suppressed"] > 0
    assert result["metrics"]["low_information_tokens_suppressed"] > 0
    suppressed = [row for row in result["selection"] if row["status"] == "omitted"]
    assert any(row.get("duplicate_of") for row in suppressed)
    assert any("acknowledgement" in row.get("omission_reason", "") for row in suppressed)


def test_explicit_supersession_prefers_current_decision_and_keeps_trace_provenance():
    units = ConversationAdapter().ingest(
        {"conversations": [{"id": "decisions", "messages": [
            {"id": "old", "role": "user", "content": "Use PostgreSQL for the local component."},
            {"id": "new", "role": "user", "content": "We are switching the local component to SQLite.",
             "metadata": {"supersedes": "old"}},
        ]}]}
    )
    result = ContextUnitRuntime(units).pack(
        "current local component database decision", 500, source_types={"message"}
    )

    assert "switching" in result["context"]
    old = next(row for row in result["selection"] if row["source_id"] == "old")
    assert old["status"] == "omitted"
    assert old["omission_reason"] == "superseded by explicit newer context"
    assert result["metrics"]["superseded_units_suppressed"] == 1
    relationship = next(
        edge for unit in units for edge in unit.relationships if edge["kind"] == "supersedes"
    )
    assert relationship["origin"] == "explicit_metadata"
    assert relationship["heuristic"] is False


def test_session_delta_suppresses_near_duplicate_on_follow_up_but_allows_topic_shift():
    units = ConversationAdapter().ingest(
        {"conversations": [{"id": "c", "messages": [
            {"id": "a", "role": "user", "content": "Use SQLite for offline drafts and keep them until upload succeeds."},
            {"id": "b", "role": "assistant", "content": "Use SQLite for offline drafts and keep each draft until upload succeeds."},
            {"id": "c", "role": "user", "content": "Use blue as the primary accent for the dashboard."},
        ]}]}
    )
    runtime = ContextUnitRuntime(units)
    first = runtime.pack("SQLite offline drafts upload", 500, source_types={"message"})
    followup = runtime.pack(
        "SQLite offline drafts upload retries", 500, source_types={"message"}, history=first["deliveries"]
    )
    topic_shift = runtime.pack("blue dashboard accent", 500, source_types={"message"}, history=first["deliveries"])

    assert followup["context"] == ""
    assert followup["metrics"]["duplicate_tokens_suppressed"] > 0
    assert "blue" in topic_shift["context"]


def test_conversation_map_returns_compact_navigation_instead_of_message_ids():
    units = ConversationAdapter().ingest(
        {
            "conversations": [
                {
                    "id": "history",
                    "title": "Offline sync decisions",
                    "messages": [
                        {"id": f"m{i}", "role": "user", "content": f"Historical decision {i}."}
                        for i in range(40)
                    ],
                }
            ]
        }
    )
    result = ContextRuntime({}).execute_context_units(
        "map", {"source_types": ["conversation"]}, units
    )

    assert result["context"] == "[conversation:history] Offline sync decisions (40 messages)"
    assert len(result["included_context"]) == 1
    assert result["metrics"]["returned_tokens"] < 20


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

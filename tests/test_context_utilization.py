from __future__ import annotations

from conceptualize_runtime.adapters import ConversationAdapter
from conceptualize_runtime.context import ContextUnitRuntime


def _conversation(messages):
    return ConversationAdapter().ingest(
        {"conversations": [{"id": "utilization", "messages": messages}]}
    )


def test_critical_replaceability_decision_is_first_and_keeps_full_semantic_fidelity():
    decision = (
        "Local persistence and synchronization are independently replaceable layers."
    )
    units = _conversation([
        {"id": "support", "role": "assistant", "content": "The release currently uses a browser PWA."},
        {"id": "boundary", "role": "user", "content": decision},
    ])

    result = ContextUnitRuntime(units).pack(
        "current architecture implementation plan", 300,
        source_types={"message"},
        targets=["conversation:utilization/message:support", "conversation:utilization/message:boundary"],
    )

    context = result["context"]
    assert context.index("CRITICAL CURRENT CONSTRAINTS") < context.index("RELEVANT CONTEXT")
    directive = "Treat current decisions and critical constraints below as binding"
    assert context.index(directive) < context.index(decision)
    assert "do not omit or contradict relevant items" in context
    assert decision in context
    assert "persistence" in context.casefold()
    assert "synchronization" in context.casefold()
    assert "independently replaceable" in context.casefold()
    assert "[message:" not in context
    boundary = next(item for item in result["working_context"] if item["source_id"] == "boundary")
    assert boundary["priority"] == "critical"
    assert boundary["category"] == "CRITICAL CURRENT CONSTRAINTS"
    assert boundary["unit_id"] == "conversation:utilization/message:boundary"


def test_repeated_critical_confirmations_raise_priority_without_repeating_exact_content():
    decision = "Local persistence and synchronization are independently replaceable layers."
    units = _conversation([
        {"id": "a", "role": "user", "content": decision},
        {"id": "b", "role": "assistant", "content": decision},
        {"id": "support", "role": "user", "content": "The PWA supports offline field work."},
    ])

    result = ContextUnitRuntime(units).pack(
        "current architecture and implementation", 400,
        source_types={"message"},
        targets=[f"conversation:utilization/message:{item}" for item in ("a", "b", "support")],
    )

    assert result["context"].count(decision) == 1
    boundary = next(item for item in result["working_context"] if item["priority"] == "critical")
    assert boundary["corroboration_count"] == 2
    duplicate = next(item for item in result["selection"] if item["source_id"] == "b")
    assert duplicate["status"] == "omitted"
    assert duplicate["omission_reason"] == "near-duplicate content already selected"


def test_explicitly_superseded_context_uses_a_separate_noncurrent_section():
    units = _conversation([
        {"id": "old", "role": "user", "content": "Use localStorage for drafts.",
         "metadata": {"state": "superseded"}},
        {"id": "new", "role": "user", "content": "Use IndexedDB for current drafts.",
         "metadata": {"context_category": "decision"}},
    ])

    result = ContextUnitRuntime(units).pack(
        "current draft storage decision", 300, source_types={"message"},
        targets=["conversation:utilization/message:old", "conversation:utilization/message:new"],
    )

    assert "SUPERSEDED / DO NOT USE" in result["context"]
    assert result["context"].index("CURRENT DECISIONS") < result["context"].index("SUPERSEDED / DO NOT USE")
    assert "Use localStorage for drafts." in result["context"]
    old = next(item for item in result["working_context"] if item["source_id"] == "old")
    assert old["priority"] == "informational"
    assert old["category"] == "SUPERSEDED / DO NOT USE"


def test_context_delta_references_previously_supplied_critical_context_compactly():
    decision = "Local persistence and synchronization are independently replaceable layers."
    units = _conversation([
        {"id": "boundary", "role": "user", "content": decision},
        {"id": "detail", "role": "assistant", "content": "The PWA keeps using the HTTPS API."},
    ])
    runtime = ContextUnitRuntime(units)
    first = runtime.pack("current architecture implementation", 300,
                         source_types={"message"}, targets=["conversation:utilization/message:boundary"])

    followup = runtime.pack("current architecture implementation", 300,
                            source_types={"message"}, history=first["deliveries"],
                            targets=["conversation:utilization/message:boundary"])

    assert decision not in followup["context"]
    assert "CONTEXT DELTA" in followup["context"]
    assert "previously supplied critical context remains applicable" in followup["context"].casefold()
    assert followup["metrics"]["unchanged_context_tokens"] > 0
    assert followup["previous_context"][0]["priority"] == "critical"


def test_required_constraint_uses_deterministic_priority_and_keeps_trace_reason():
    units = _conversation([
        {"id": "constraint", "role": "user", "content": "Each local attachment must remain until authenticated upload acknowledgement."},
    ])

    result = ContextUnitRuntime(units).pack(
        "attachment upload persistence constraint", 300, source_types={"message"}
    )

    item = result["working_context"][0]
    assert item["priority"] in {"required", "critical"}
    assert item["priority_reasons"]
    assert "Each local attachment must remain" in result["context"]

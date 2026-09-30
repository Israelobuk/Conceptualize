"""Direct-routing config and catalog-request classification checks."""

import json
from pathlib import Path

from evaluations.scripts.run_provider_discovery_routing import (
    BASE_FLAGS,
    DIRECT_INSTRUCTION,
    catalog_requests,
)


def test_direct_routing_changes_only_host_instruction():
    assert "developer_instructions" not in " ".join(BASE_FLAGS)
    assert "mcp__conceptualize__conceptualize_context" in DIRECT_INSTRUCTION
    assert "@Conceptualize" in DIRECT_INSTRUCTION


def test_inline_tool_lookup_is_not_a_separate_discovery_request():
    run = {"requests": [
        {"request_index": 1, "input_tokens": 19601, "model_actions": [
            {"input": "text(ALL_TOOLS.filter(x => x.name.includes('conceptualize')))"}]},
        {"request_index": 2, "input_tokens": 29000, "model_actions": [
            {"input": "const t=ALL_TOOLS.find(x=>x.name==='mcp__conceptualize__conceptualize_context'); "
                      "await tools.mcp__conceptualize__conceptualize_context({task:'x'});"}]},
    ]}
    assert [row["request_index"] for row in catalog_requests(run)] == [1]


def test_saved_frozen_workflow_has_one_call_and_no_precall_catalog_turn():
    result = Path(__file__).resolve().parents[1] / (
        "evaluations/results/provider-input-overhead-discovery-optimization.json")
    data = json.loads(result.read_text(encoding="utf-8"))
    assert data["validity"] == {
        "after_zero_separate_catalog_requests": True,
        "after_two_provider_requests": True,
        "all_retrieval_and_context_8_of_8": True,
    }
    for run in data["after"]["runs"]:
        assert len(run["conceptualize_calls"]) == 1
        assert run["request_count"] == 2
        assert run["catalog_request_count"] == 0
        assert sum(request["input_tokens"] for request in run["requests"]) == run["input_tokens"]

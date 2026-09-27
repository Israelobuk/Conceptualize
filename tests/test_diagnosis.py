from conceptualize_evaluation.diagnose import discovery_comparison, observed_waits, outcome
from conceptualize_runtime.patterns import detect


def test_pair_discovery_comparison_keeps_unknown_times_unknown():
    rows = [{"mode": "control", "outcome": "success", "time_to_first_relevant_file_ms": None},
            {"mode": "conceptualize", "outcome": "success", "time_to_first_relevant_file_ms": 5000}]
    assert discovery_comparison(rows)["category"] == "inconclusive"
    rows[0]["time_to_first_relevant_file_ms"] = 10000
    result = discovery_comparison(rows)
    assert result["category"] == "context discovered earlier"
    assert result["enabled_minus_control_ms"] == -5000


def test_wait_spans_require_both_timestamps_and_do_not_invent_idle():
    events = [
        {"type": "item.started", "item": {"id": "a", "type": "mcp_tool_call"}},
        {"type": "item.completed", "item": {"id": "a", "type": "mcp_tool_call"}},
    ]
    assert observed_waits(events, {}) == []
    assert observed_waits(events, {0: 20, 1: 30}) == [{
        "kind": "mcp_tool_call", "item_id": "a", "start_step": 0,
        "end_step": 1, "arrival_span_ms": 10}]


def test_usage_interrupted_shipping_is_not_a_task_failure():
    assert (
        outcome(
            {
                "task_completion": False,
                "agent_exit_code": 1,
                "failure_signals": {"account_usage_limit": True},
            }
        )
        == "blocked_incomplete"
    )


def test_patterns_explain_repeats_without_quality_scores():
    calls = [
        {"operation": "dependencies", "inputs": {"target": "a.py"}, "metrics": {}},
        {
            "operation": "dependencies",
            "inputs": {"target": "a.py"},
            "metrics": {"full_selected_tokens": 100, "previously_supplied_tokens": 90},
        },
    ]
    patterns = detect(calls)
    assert {p["pattern"] for p in patterns} == {"repeated_dependencies", "mostly_known_context"}
    assert all("evidence" in p and "score" not in p for p in patterns)

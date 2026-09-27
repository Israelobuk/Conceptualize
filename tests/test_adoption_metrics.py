from conceptualize_evaluation.adoption import adoption_metrics


def test_invocation_is_not_utility_and_unobserved_discovery_stays_unknown():
    events = [{"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "conceptualize", "tool": "conceptualize_inspect", "status": "completed"}}]
    result = adoption_metrics(events, {"first_observed_read": {}}, [], ["relay/accounting.py"], True)
    assert result["tool_available"] is True
    assert result["tool_invoked"] is True
    assert result["first_operation"] == "inspect"
    assert result["useful_relationship_surfaced"] is None
    assert result["relationship_used_in_final_change"] is None
    assert result["when_invoked"] == "unknown"


def test_only_delivered_relationships_count_and_timing_uses_observed_reads():
    events = [{"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "conceptualize", "tool": "conceptualize_inspect", "status": "completed", "result": {"structured_content": {"environment": {"consumers": ["relay/accounting.py"]}}}}}]
    result = adoption_metrics(events, {"first_observed_read": {"relay/accounting.py": 4}}, [], ["relay/accounting.py"], True)
    assert result["useful_relationship_surfaced"] is True
    assert result["when_invoked"] == "before observed relevant manual read"
    assert result["relationship_used_in_final_change"] is None

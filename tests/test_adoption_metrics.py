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


def test_per_relationship_discovery_does_not_infer_missing_reads():
    events = [{"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "conceptualize", "tool": "conceptualize_inspect", "status": "completed", "result": {"structured_content": {"environment": {"consumers": ["shop/warehouse.py", "shop/orders.py"]}}}}}]
    result = adoption_metrics(events, {"first_observed_read": {"shop/warehouse.py": 3}}, [], ["shop/warehouse.py", "shop/orders.py"], True)
    assert result["relationship_discovery"]["shop/warehouse.py"]["when"] == "before observed read"
    assert result["relationship_discovery"]["shop/orders.py"]["when"] == "unknown"


def test_source_bearing_search_prevents_false_early_discovery_claim():
    events = [
        {"type": "item.completed", "item": {"type": "command_execution", "command": "rg Receipt shop", "exit_code": 0, "aggregated_output": "shop/warehouse.py:from .contracts import Receipt"}},
        {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "conceptualize", "tool": "conceptualize_inspect", "status": "completed", "result": {"structured_content": {"environment": {"consumers": ["shop/warehouse.py"]}}}}},
    ]
    result = adoption_metrics(events, {"first_observed_read": {"shop/warehouse.py": 3}}, [], ["shop/warehouse.py"], True)
    assert result["relationship_discovery"]["shop/warehouse.py"]["relative_to_source_discovery"] == "after observed source evidence"
    assert result["when_invoked_vs_observed_discovery"] == "after observed relevant source evidence"


def test_explicit_target_endpoint_alone_does_not_prove_useful_relationship():
    events = [{"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "conceptualize", "tool": "conceptualize_dependencies", "status": "completed", "result": {"structured_content": {"relationships": [{"source": "noise.py", "target": "relay/contracts.py", "kind": "imports"}]}}}}]
    result = adoption_metrics(events, {"first_observed_read": {}}, [], ["relay/contracts.py", "relay/accounting.py"], True)
    assert result["useful_relationship_surfaced"] is False

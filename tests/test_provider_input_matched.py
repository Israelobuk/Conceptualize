"""Focused checks for matched-host provider-input accounting."""

from evaluations.scripts.run_provider_input_matched import (
    _emitted_calls,
    _usage_delta,
    canonical_hash,
    mcp_config,
)


def test_mcp_registration_is_only_condition_difference():
    assert mcp_config("a2") == {"server_count": 0, "servers": []}
    b1 = mcp_config("b1")
    assert b1["server_count"] == 1
    assert [server["name"] for server in b1["servers"]] == ["inert"]
    assert b1 == mcp_config("b2")


def test_canonical_hash_is_order_independent():
    assert canonical_hash({"a": 1, "b": 2}) == canonical_hash({"b": 2, "a": 1})


def test_trace_parsing_preserves_tool_order_arguments_and_response():
    events = [
        {"type": "item.completed", "item": {"type": "agent_message", "text": "hello"}},
        {"type": "item.completed", "item": {"type": "mcp_tool_call", "server": "inert",
         "tool": "noop", "arguments": {"task": "x"}, "status": "completed",
         "result": {"content": [{"type": "text", "text": "ok"}]}}},
        {"type": "item.completed", "item": {"type": "command_execution", "name": "shell",
         "arguments": {"command": "echo hi"}, "status": "completed"}},
    ]
    calls = _emitted_calls(events)
    assert [(call["classification"], call["tool"]) for call in calls] == [
        ("mcp", "noop"), ("built_in_or_hosted", "shell")]
    assert calls[0]["arguments"] == {"task": "x"}
    assert calls[0]["response_text"] == "ok"


def test_provider_usage_delta_includes_cached_and_uncached():
    a2 = {"aggregate_usage": {"input_tokens": 100, "cached_input_tokens": 20,
                              "output_tokens": 10}, "aggregate_uncached_input_tokens": 80,
          "request_count": 1, "elapsed_ms": 200}
    b1 = {"aggregate_usage": {"input_tokens": 110, "cached_input_tokens": 0,
                              "output_tokens": 12}, "aggregate_uncached_input_tokens": 110,
          "request_count": 1, "elapsed_ms": 230}
    assert _usage_delta(b1, a2) == {
        "input_tokens": 10, "cached_input_tokens": -20,
        "uncached_input_tokens": 30, "output_tokens": 2,
        "request_count": 0, "total_elapsed_ms": 30,
    }

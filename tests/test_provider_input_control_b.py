"""Focused checks for the evaluation-only inert MCP fixture."""

import asyncio

from evaluations.scripts.run_provider_input_control_b import (
    _call_metrics,
    _tool_names,
    inspect_server,
)


def test_inert_fixture_exposes_only_read_only_noop() -> None:
    surface = asyncio.run(inspect_server())
    assert surface["tool_count"] == 1
    assert surface["tool_schema"]["name"] == "noop"
    assert surface["tool_schema"]["inputSchema"]["required"] == ["task"]
    assert surface["tool_schema"]["annotations"]["readOnlyHint"] is True
    assert surface["server_instruction_tokens_local"] < 20


def test_tool_call_metrics_measure_only_the_inert_response() -> None:
    assert _tool_names({"tools": [{"name": "mcp__inert__noop"}],
                        "additional_tools": []}) == ["mcp__inert__noop"]
    calls = _call_metrics([{
        "server": "inert", "tool": "noop", "status": "completed", "error": None,
        "arguments": {"task": "frozen task"},
        "result": {"content": [{"type": "text", "text": "ok"}]},
    }])
    assert calls[0]["response_text"] == "ok"
    assert calls[0]["response_bytes"] == 2
    assert calls[0]["response_tokens_local"] > 0

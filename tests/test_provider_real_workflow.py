"""Focused matching and request-boundary tests for the real V0.9 trace."""

from conceptualize_evaluation import v09_capability_benchmark as benchmark

from evaluations.scripts.analyze_provider_real_workflow import metric_delta
from evaluations.scripts.run_provider_real_workflow import (
    BASE_FLAGS,
    command,
    mcp_calls,
    prompts,
    request_timeline,
)


def test_three_conditions_share_base_flags_and_only_mcp_activation_changes():
    fixture, _, _ = benchmark.verify_freeze()
    _, history = benchmark.conversation(fixture)
    sample = prompts(fixture, history, "full_history")
    assert sample["f-minus-1"] == sample["f0"]
    assert sample["f1"].replace("@Conceptualize\n", "", 1) == sample["f0"]
    assert history in sample["f1"]
    assert "--model" in BASE_FLAGS
    a = command("f-minus-1", 1234, benchmark.FIXTURE)
    b = command("f0", 1234, benchmark.FIXTURE)
    c = command("f1", 1234, benchmark.FIXTURE)
    assert a[:len(BASE_FLAGS) + 2] == b[:len(BASE_FLAGS) + 2] == c[:len(BASE_FLAGS) + 2]
    assert "mcp_servers.conceptualize.enabled=true" not in a
    assert "mcp_servers.conceptualize.enabled=true" in b
    assert b == c


def test_proven_prompt_does_not_embed_fixture_history():
    fixture, _, _ = benchmark.verify_freeze()
    _, history = benchmark.conversation(fixture)
    sample = prompts(fixture, history, "proven")
    assert history not in sample["f1"]
    assert sample["f1"] == benchmark.generation_prompt(fixture, "conceptualize", history)


def test_timeline_attaches_tool_output_to_continuation():
    rollout = [
        {"type": "response_item", "ordinal": 1, "payload": {"type": "custom_tool_call",
          "name": "exec", "input": "call", "call_id": "a"}},
        {"type": "token_usage_record", "ordinal": 2},
        {"type": "response_item", "ordinal": 3, "payload": {"type": "custom_tool_call_output",
          "call_id": "a", "output": "ok"}},
        {"type": "response_item", "ordinal": 4, "payload": {"type": "message",
          "role": "assistant", "content": "DONE"}},
        {"type": "token_usage_record", "ordinal": 5},
    ]
    timeline = request_timeline(rollout, [{"request_index": 1}, {"request_index": 2}])
    assert timeline[0]["phase"] == "initial"
    assert timeline[0]["model_actions"][0]["name"] == "exec"
    assert timeline[1]["phase"] == "continuation_after_tool"
    assert len(timeline[1]["preceded_by_tool_outputs"]) == 1


def test_mcp_trace_keeps_builtin_resource_calls_separate():
    events = [{"type": "item.completed", "item": {"type": "mcp_tool_call",
               "server": "codex", "tool": "list_mcp_resources", "arguments": {},
               "result": {"content": []}, "status": "completed"}},
              {"type": "item.completed", "item": {"type": "mcp_tool_call",
               "server": "conceptualize", "tool": "conceptualize_context",
               "arguments": {"task": "x"},
               "result": {"structuredContent": {"context": "hello"}},
               "status": "completed"}}]
    calls = mcp_calls(events)
    assert [(call["server"], call["tool"]) for call in calls] == [
        ("codex", "list_mcp_resources"), ("conceptualize", "conceptualize_context")]


def test_attribution_delta_keeps_cached_and_uncached_separate():
    before = {"aggregate_usage": {"input_tokens": 100, "cached_input_tokens": 40,
                                  "output_tokens": 10}, "aggregate_uncached_input_tokens": 60,
              "request_count": 1, "elapsed_ms": 100}
    after = {"aggregate_usage": {"input_tokens": 150, "cached_input_tokens": 20,
                                 "output_tokens": 12}, "aggregate_uncached_input_tokens": 130,
             "request_count": 2, "elapsed_ms": 130}
    assert metric_delta(after, before) == {"input_tokens": 50, "cached_input_tokens": -20,
                                           "uncached_input_tokens": 70, "output_tokens": 2,
                                           "request_count": 1, "elapsed_ms": 30}

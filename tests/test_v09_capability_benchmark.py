from __future__ import annotations

import asyncio
import json
import os
import sys

import pytest
from conceptualize_evaluation import v09_capability_benchmark as benchmark
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


@pytest.fixture
def truth():
    return benchmark._truth()


def test_v09_truth_has_frozen_semantic_propositions_and_strict_pass_rule(truth):
    assert len(truth["facts"]) == 8
    assert all(fact["critical"] for fact in truth["facts"])
    assert truth["pass_rule"]["maximum_stale_as_current"] == 0
    assert truth["pass_rule"]["maximum_contradictions"] == 0


def test_generation_conditions_preserve_identical_user_task_and_separate_activation():
    fixture = {"question": "Do the current work.", "history": []}
    control = benchmark.generation_prompt(fixture, "control", "older messages")
    activated = benchmark.generation_prompt(fixture, "conceptualize", "older messages")
    assert control.split("USER TASK:\n", 1)[1] == fixture["question"]
    assert activated.split("@Conceptualize\n", 1)[1] == fixture["question"]
    assert "older messages" in control and "older messages" not in activated
    assert "conceptualize_context" not in activated


def test_evaluator_prompt_is_blind_and_contains_frozen_task_truth_and_output_schema(truth, monkeypatch, tmp_path):
    prompt_path = tmp_path / "prompt.txt"
    prompt_path.write_text(benchmark.EVALUATOR_TEMPLATE, encoding="utf-8")
    monkeypatch.setattr(benchmark, "PROMPT_TEMPLATE", prompt_path)
    rendered = benchmark.evaluator_prompt("frozen task", truth, "answer_001", "the answer")
    assert "control" not in rendered.casefold()
    assert "conceptualize" not in rendered.casefold()
    assert "frozen task" in rendered and "answer_001" in rendered
    assert "ARCH_01" in rendered and "stale_as_current" in rendered
    assert "the answer" in rendered


def _grade(truth, statuses):
    props = [{"id": fact["id"], "status": statuses.get(fact["id"], "present"),
              "evidence": "evidence", "reason": "reason"} for fact in truth["facts"]]
    present = sum(item["status"] == "present" for item in props)
    critical = sum(item["status"] == "present" for item in props if item["id"] in
                   {fact["id"] for fact in truth["facts"] if fact["critical"]})
    total = round(100 * present / len(props), 2)
    crit = round(100 * critical / sum(fact["critical"] for fact in truth["facts"]), 2)
    stale = sum(item["status"] == "stale_as_current" for item in props)
    contra = sum(item["status"] == "contradicted" for item in props)
    passed = (critical == 8 and total >= 85 and stale == 0 and contra == 0)
    return {"answer_id": "answer_001", "propositions": props,
            "critical_proposition_coverage_percent": crit,
            "total_proposition_coverage_percent": total,
            "stale_current_errors": stale, "contradiction_count": contra, "pass": passed}


def test_aggregate_accepts_complete_paraphrase_independent_evaluator_statuses(truth):
    grade = _grade(truth, {})
    benchmark.validate_grade(grade, truth, "answer_001")
    assert grade["pass"] is True


@pytest.mark.parametrize("status", ["absent", "contradicted", "stale_as_current"])
def test_aggregate_rejects_missing_or_incorrect_critical_state(truth, status):
    grade = _grade(truth, {"CON_01": status})
    benchmark.validate_grade(grade, truth, "answer_001")
    assert grade["pass"] is False


def test_aggregate_validation_rejects_judge_schema_or_math_errors(truth):
    grade = _grade(truth, {})
    grade["pass"] = False
    with pytest.raises(ValueError, match="aggregate fields disagree"):
        benchmark.validate_grade(grade, truth, "answer_001")


def test_evaluator_output_must_match_frozen_proposition_order(truth):
    grade = _grade(truth, {})
    grade["propositions"].reverse()
    with pytest.raises(ValueError, match="omitted, duplicated, or reordered"):
        benchmark.validate_grade(grade, truth, "answer_001")


def test_post_capability_workflow_records_items_after_context_arrives():
    events = [
        {"type": "item.completed", "item": {"type": "mcp_tool_call"}},
        {"type": "item.completed", "item": {"type": "reasoning"}},
        {"type": "item.completed", "item": {"type": "agent_message"}},
    ]
    assert benchmark._post_capability_items(events) == ["reasoning", "agent_message"]
    assert benchmark._post_capability_items([]) is None


def test_fixture_creation_refuses_to_overwrite_any_frozen_artifact(monkeypatch, tmp_path):
    monkeypatch.setattr(benchmark, "FIXTURE", tmp_path / "fixture.json")
    monkeypatch.setattr(benchmark, "TRUTH", tmp_path / "ground-truth.json")
    monkeypatch.setattr(benchmark, "PROMPT_TEMPLATE", tmp_path / "prompt.txt")
    monkeypatch.setattr(benchmark, "FREEZE", tmp_path / "freeze.json")
    benchmark.FREEZE.write_text("frozen", encoding="utf-8")
    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        benchmark.create_frozen_fixture()


def test_freeze_verification_rejects_changed_fixture(monkeypatch, tmp_path):
    fixture_path, truth_path, prompt_path, freeze_path = (tmp_path / name for name in
                                                           ("fixture.json", "truth.json", "prompt.txt", "freeze.json"))
    fixture_path.write_text(json.dumps({"question": "task"}), encoding="utf-8")
    truth_path.write_text(json.dumps({"pass_rule": {}}), encoding="utf-8")
    prompt_path.write_text("prompt", encoding="utf-8")
    freeze_path.write_text(json.dumps({"fixture_sha256": "wrong"}), encoding="utf-8")
    monkeypatch.setattr(benchmark, "FIXTURE", fixture_path)
    monkeypatch.setattr(benchmark, "TRUTH", truth_path)
    monkeypatch.setattr(benchmark, "PROMPT_TEMPLATE", prompt_path)
    monkeypatch.setattr(benchmark, "FREEZE", freeze_path)
    with pytest.raises(RuntimeError, match="artifact changed"):
        benchmark.verify_freeze()


def test_v09_fixture_mcp_stdio_exposes_one_task_only_capability_and_returns_context():
    async def smoke():
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", "conceptualize_evaluation.v09_mcp_fixture_server"],
            env={**os.environ, "PYTHONPATH": os.pathsep.join(str(benchmark.ROOT / path) for path in
                                                            ("apps/api", "apps/mcp", "packages"))},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = (await session.list_tools()).tools
                assert [tool.name for tool in tools] == ["conceptualize_context"]
                schema = tools[0].inputSchema
                assert schema["required"] == ["task"]
                assert set(schema["properties"]) == {"task"}
                fixture, _, _ = benchmark.verify_freeze()
                result = await session.call_tool("conceptualize_context", {"task": fixture["question"]})
                assert not result.isError
                assert result.structuredContent["new_context_tokens"] > 0
                assert "context" in result.structuredContent

    asyncio.run(smoke())

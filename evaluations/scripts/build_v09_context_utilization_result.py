"""Build an auditable report from the frozen V0.9 utilization rerun artifacts."""

from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any

from conceptualize_evaluation import v09_capability_benchmark as benchmark
from conceptualize_runtime.runtime import token_count

ROOT = Path(__file__).resolve().parents[2]
RUNS = ROOT / "evaluations/runs/v09/v09-utilization-fix/activated-priority-directive"
OUTPUT = ROOT / "evaluations/results/v09-context-utilization-fix.json"
AUDIT = ROOT / "evaluations/results/v09-context-utilization-fix-human-audit.md"
KINDS = ("retrieval", "working", "answer")


def _grade(run: int, kind: str, truth: dict[str, Any], fixture: dict[str, Any]) -> dict[str, Any]:
    path = RUNS / "semantic-judges" / kind / f"run-{run}" / "agent-events.jsonl"
    events = benchmark._extract_events(path.read_text(encoding="utf-8"))
    grade = benchmark._json_object(benchmark._final_text(events, "agent_message"))
    benchmark.validate_grade(grade, truth, f"{kind}_{run:03d}")
    return grade


def build() -> dict[str, Any]:
    fixture, truth, freeze = benchmark.verify_freeze()
    units, _ = benchmark.conversation(fixture)
    by_source = {unit.source_id: unit for unit in units}
    records = []

    for run_number in range(1, 4):
        run_dir = RUNS / f"rep-{run_number}"
        trace = json.loads((run_dir / "conceptualize-trace.json").read_text(encoding="utf-8"))
        events = benchmark._extract_events((run_dir / "agent-events.jsonl").read_text(encoding="utf-8"))
        grades = {kind: _grade(run_number, kind, truth, fixture) for kind in KINDS}
        metrics = benchmark.context_utilization_metrics(
            truth, grades["retrieval"], grades["working"], grades["answer"]
        )
        calls = [
            event["item"] for event in events
            if event.get("type") == "item.completed"
            and event.get("item", {}).get("type") == "mcp_tool_call"
        ]
        retrieval_sources = []
        seen_sources = set()
        for selected in trace["selection"]:
            source_id = selected.get("source_id")
            unit = by_source.get(source_id)
            if selected.get("status") in {"selected", "referenced"} and unit and source_id not in seen_sources:
                retrieval_sources.append({"source_id": source_id, "unit_id": selected["unit_id"]})
                seen_sources.add(source_id)

        command_metadata = (run_dir / "command-metadata.json").stat().st_mtime
        post_run_events = (run_dir / "agent-events.jsonl").stat().st_mtime
        elapsed_ms = round((post_run_events - command_metadata) * 1000, 2)
        records.append({
            "run": run_number,
            "answer": (run_dir / "answer.md").read_text(encoding="utf-8"),
            "capability_activated": True,
            "capability_calls": len(calls),
            "capability_task_arguments": [call.get("arguments", {}).get("task") for call in calls],
            "normal_workflow_after_capability": benchmark._post_capability_items(events),
            "provider_usage": benchmark._usage(events),
            "elapsed_ms_approx": elapsed_ms,
            "latency_source": "pre-run command metadata to post-run event-file timestamp",
            "working_context": trace["context"],
            "working_context_tokens": token_count(trace["context"]),
            "context_delta": trace["metrics"],
            "runtime_timings_ms": trace["timings_ms"],
            "runtime_elapsed_ms": trace["elapsed_ms"],
            "selected_provenance_count": trace["selected_provenance_count"],
            "retrieval_sources": retrieval_sources,
            "working_context_units": trace["working_context"],
            "retrieval_grade": grades["retrieval"],
            "working_context_grade": grades["working"],
            "answer_grade": grades["answer"],
            "utilization_metrics": metrics,
        })

    def mean(key: str) -> float:
        return round(statistics.mean(row[key] for row in records), 2)

    average_usage = {
        key: round(statistics.mean(row["provider_usage"][key] for row in records), 2)
        for key in ("input_tokens", "cached_input_tokens", "output_tokens")
    }
    averages = {
        **average_usage,
        "working_context_tokens": mean("working_context_tokens"),
        "elapsed_ms_approx": mean("elapsed_ms_approx"),
        "capability_calls": mean("capability_calls"),
        "retrieval_coverage_percent": round(statistics.mean(
            row["utilization_metrics"]["context_retrieval_coverage_percent"] for row in records
        ), 2),
        "working_context_coverage_percent": round(statistics.mean(
            row["utilization_metrics"]["working_context_coverage_percent"] for row in records
        ), 2),
        "final_answer_coverage_percent": round(statistics.mean(
            row["utilization_metrics"]["final_answer_coverage_percent"] for row in records
        ), 2),
        "context_utilization_rate_percent": round(statistics.mean(
            row["utilization_metrics"]["context_utilization_rate_percent"] for row in records
        ), 2),
        "critical_context_utilization_rate_percent": round(statistics.mean(
            row["utilization_metrics"]["critical_context_utilization_rate_percent"] for row in records
        ), 2),
    }
    result = {
        "diagnostic": "V0.9 frozen benchmark post-fix context-utilization rerun; no new benchmark version",
        "benchmark": "v0.9-capability-semantic-v1",
        "fixture_sha256": freeze["fixture_sha256"],
        "ground_truth_sha256": freeze["ground_truth_sha256"],
        "evaluator_prompt_sha256": freeze["evaluator_prompt_sha256"],
        "generation_model": benchmark.GENERATION_MODEL,
        "generation_reasoning": benchmark.GENERATION_REASONING,
        "evaluator_model": benchmark.EVALUATOR_MODEL,
        "evaluator_reasoning": benchmark.EVALUATOR_REASONING,
        "task": fixture["question"],
        "working_context_directive": (
            "Treat current decisions and critical constraints below as binding; "
            "do not omit or contradict relevant items."
        ),
        "repetitions": len(records),
        "pass_count": sum(row["answer_grade"]["pass"] for row in records),
        "averages": averages,
        "records": records,
        "notes": [
            "The frozen V0.9 fixture, ground truth, task, evaluator prompt, and grading rules were verified unchanged.",
            "Provider-reported model tokens are distinct from local Working Context token counts.",
            "Elapsed time is approximate because the final runner did not persist its in-process stopwatch value.",
            "Every required proposition is critical; any omitted proposition is a full-pass failure.",
        ],
    }
    OUTPUT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    audit = [
        "# V0.9 context-utilization fix — human audit", "",
        f"Frozen fixture: `{freeze['fixture_sha256']}`. Frozen evaluator prompt: `{freeze['evaluator_prompt_sha256']}`.",
        f"Full passes: **{result['pass_count']}/3**. Retrieval / Working Context / answer coverage: **{averages['retrieval_coverage_percent']}% / {averages['working_context_coverage_percent']}% / {averages['final_answer_coverage_percent']}%**.",
        f"Context Utilization Rate: **{averages['context_utilization_rate_percent']}%**. Critical Context Utilization Rate: **{averages['critical_context_utilization_rate_percent']}%**.",
        "",
    ]
    for row in records:
        audit += [
            f"## Run {row['run']}", "",
            f"Pass: **{row['answer_grade']['pass']}**; calls: {row['capability_calls']}; context: {row['working_context_tokens']} local tokens; provider input/cached/output: {row['provider_usage']['input_tokens']}/{row['provider_usage']['cached_input_tokens']}/{row['provider_usage']['output_tokens']}; latency: approximately {row['elapsed_ms_approx']} ms.",
            "", "| Proposition | Retrieval | Working Context | Final answer | Answer evidence |", "|---|---|---|---|---|",
        ]
        grades = [row[key] for key in (
            "retrieval_grade", "working_context_grade", "answer_grade"
        )]
        maps = [{item["id"]: item for item in grade["propositions"]} for grade in grades]
        for fact in truth["facts"]:
            item = maps[2][fact["id"]]
            evidence = item["evidence"].replace("|", "\\|").replace("\n", " ")
            audit.append(
                f"| {fact['id']} | {maps[0][fact['id']]['status']} | {maps[1][fact['id']]['status']} | {item['status']} | {evidence} |"
            )
        arch = next(item for item in row["utilization_metrics"]["propositions"] if item["id"] == "ARCH_02")
        classification = arch["failure_classification"] or "none; present through retrieval, compilation, and answer"
        audit += ["", f"ARCH_02 classification: `{classification}`.", ""]
    AUDIT.write_text("\n".join(audit), encoding="utf-8")
    return result


if __name__ == "__main__":
    print(json.dumps(build(), ensure_ascii=False, indent=2))

"""Deterministic context-selection checks; deliberately not represented as model runs."""

import argparse
import json
from pathlib import Path
from time import perf_counter

from conceptualize_runtime.adapters import ConversationAdapter
from conceptualize_runtime.context import ContextUnitRuntime
from conceptualize_runtime.runtime import token_count

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "evaluations" / "conversations-v05.json"
RESULT = ROOT / "evaluations" / "results" / "v05-conversations.json"


def run(fixture: dict) -> dict:
    units = ConversationAdapter().ingest({"conversations": fixture["conversations"]})
    runtime = ContextUnitRuntime(units)
    full_context = "\n\n".join(
        f"[{unit.metadata.get('role', 'conversation')}] {unit.content}"
        for unit in units
        if unit.source_type == "message"
    )
    control_tokens = token_count(full_context)
    tasks = []
    for task in fixture["tasks"]:
        started = perf_counter()
        packed = runtime.pack(
            task["query"],
            task["token_budget"],
            source_types={"message"},
        )
        conceptualize_ms = (perf_counter() - started) * 1000
        control_facts = [fact for fact in task["required_facts"] if fact.lower() in full_context.lower()]
        selected_facts = [
            fact for fact in task["required_facts"] if fact.lower() in packed["context"].lower()
        ]
        control = {
            "condition": "full_context_control",
            "success": len(control_facts) == len(task["required_facts"]),
            "required_facts": task["required_facts"],
            "facts_recovered": control_facts,
            "context_tokens": control_tokens,
            "model_input_tokens": None,
            "cached_input_tokens": None,
            "output_tokens": None,
            "elapsed_ms": None,
            "tool_operations": 0,
            "context": full_context,
        }
        conceptualize = {
            "condition": "conceptualize_runtime_selection",
            "success": len(selected_facts) == len(task["required_facts"]),
            "required_facts": task["required_facts"],
            "facts_recovered": selected_facts,
            "context_tokens": packed["metrics"]["new_context_tokens"],
            "candidate_tokens": packed["metrics"]["candidate_tokens"],
            "selected_tokens": packed["metrics"]["selected_tokens"],
            "model_input_tokens": None,
            "cached_input_tokens": None,
            "output_tokens": None,
            "elapsed_ms": round(conceptualize_ms, 3),
            "tool_operations": 1,
            "selection": packed["selection"],
            "included_units": packed["included_units"],
            "omitted_units": packed["omitted_units"],
            "context": packed["context"],
            "retrieval_notice": packed["retrieval_notice"],
        }
        tasks.append(
            {
                "task_id": task["id"],
                "query": task["query"],
                "token_budget": task["token_budget"],
                "control": control,
                "conceptualize": conceptualize,
                "context_token_difference": conceptualize["context_tokens"] - control_tokens,
                "same_deterministic_fact_coverage": control["success"]
                == conceptualize["success"],
            }
        )
    return {
        "benchmark": "v0.5 deterministic conversation context selection",
        "fixture_version": fixture["version"],
        "run_type": "runtime-only diagnostic; no host AI model was invoked",
        "tasks": tasks,
        "aggregate": {
            "tasks": len(tasks),
            "control_passes": sum(task["control"]["success"] for task in tasks),
            "conceptualize_fact_coverage_passes": sum(
                task["conceptualize"]["success"] for task in tasks
            ),
            "same_fact_coverage_tasks": sum(
                task["same_deterministic_fact_coverage"] for task in tasks
            ),
            "control_context_tokens_per_task": control_tokens,
            "conceptualize_context_tokens": sum(
                task["conceptualize"]["context_tokens"] for task in tasks
            ),
            "model_input_tokens": None,
            "cached_input_tokens": None,
            "output_tokens": None,
            "estimated_cost": None,
            "autonomous_adoption": "not measured; this diagnostic invokes the runtime directly",
            "forced_context_agent_quality": "not measured; no model was called",
        },
        "categories": {
            "effectiveness": {
                "control_fact_checks_passed": sum(task["control"]["success"] for task in tasks),
                "conceptualize_fact_checks_passed": sum(
                    task["conceptualize"]["success"] for task in tasks
                ),
                "checks": len(tasks),
                "model_answer_correctness": None,
            },
            "efficiency": {
                "full_context_tokens_per_task": control_tokens,
                "conceptualize_context_tokens_total": sum(
                    task["conceptualize"]["context_tokens"] for task in tasks
                ),
                "candidate_context_tokens_total": sum(
                    task["conceptualize"]["candidate_tokens"] for task in tasks
                ),
                "tool_operations": sum(task["conceptualize"]["tool_operations"] for task in tasks),
                "average_runtime_selection_ms": round(
                    sum(task["conceptualize"]["elapsed_ms"] for task in tasks) / max(1, len(tasks)),
                    3,
                ),
                "model_input_tokens": None,
                "cached_input_tokens": None,
                "output_tokens": None,
            },
            "economics": {
                "pricing_snapshot": None,
                "baseline_model_cost": None,
                "conceptualize_model_cost": None,
                "estimated_cost_difference": None,
            },
        },
        "limitations": [
            "String-based fact checks measure selected-context coverage, not model answer correctness.",
            "The control supplies the complete fixture history to every task and is intentionally broad.",
            "Context string tokens are not model-reported input tokens.",
            "No pricing estimate is emitted without actual input/cached/output token telemetry and an explicit pricing snapshot.",
        ],
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--output", type=Path, default=RESULT)
    args = parser.parse_args()
    report = run(json.loads(args.fixture.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report["aggregate"], indent=2))


if __name__ == "__main__":
    main()

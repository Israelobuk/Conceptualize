"""Grade F1 answer/context with the frozen V0.9 rubric, reusing exact prior evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

from conceptualize_evaluation import v09_capability_benchmark as benchmark

from evaluations.scripts.run_provider_input_control_a import CODEX_HOME, RESULTS, RUN_ROOT

SOURCE = RESULTS / "provider-input-overhead-real-workflow-proven-v3.json"
PRIOR = RESULTS / "v09-context-utilization-fix.json"
OUTPUT = RESULTS / "provider-input-overhead-real-workflow-effectiveness.json"
JUDGE_ROOT = RUN_ROOT / "real-workflow-proven-v3" / "semantic-judges"


def selected_sources(trace: dict) -> set[str]:
    return {item["source_id"] for item in trace["selection"]
            if item.get("status") in {"selected", "referenced"}}


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=SOURCE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--judge-root", type=Path, default=JUDGE_ROOT)
    args = parser.parse_args()
    fixture, truth, freeze = benchmark.verify_freeze()
    current = json.loads(args.source.read_text(encoding="utf-8"))
    prior = json.loads(PRIOR.read_text(encoding="utf-8"))
    units, _ = benchmark.conversation(fixture)
    by_source = {unit.source_id: unit for unit in units}
    configuration = current.get("base_configuration", current.get("configuration"))
    if configuration["fixture_sha256"] != freeze["fixture_sha256"]:
        raise RuntimeError("Fixture mismatch")
    records = []
    for run in [item for item in current["runs"] if item["kind"] == "f1"]:
        order = run["run_order"]
        trace = json.loads(Path(run["context_trace_path"]).read_text(encoding="utf-8"))
        sources = selected_sources(trace)
        retrieval_match = next((old for old in prior["records"]
                                if sources == {item["source_id"] for item in old["retrieval_sources"]}), None)
        if retrieval_match is None:
            ordered_ids = list(dict.fromkeys(item["source_id"] for item in trace["selection"]
                if item.get("status") in {"selected", "referenced"}
                and item.get("source_id") in by_source))
            artifact = "\n\n".join(
                f"[{by_source[source_id].metadata['role']} "
                f"{by_source[source_id].metadata['timestamp']}] {by_source[source_id].content}"
                for source_id in ordered_ids)
            retrieval_judged = benchmark._run_judge(
                artifact, f"retrieval_real_{order}", fixture=fixture, truth=truth,
                codex_home=CODEX_HOME, timeout=240,
                run_dir=args.judge_root / f"retrieval-run-{order}")
            retrieval_grade = retrieval_judged["grade"]
            retrieval_source = {"type": "new_frozen_semantic_judge",
                                "source_count": len(ordered_ids),
                                "provider_usage": retrieval_judged["provider_usage"]}
        else:
            retrieval_grade = retrieval_match["retrieval_grade"]
            retrieval_source = {"type": "exact_prior_selection",
                                "prior_run": retrieval_match["run"], "source_count": len(sources)}
        context_match = next((old for old in prior["records"]
                              if trace["context"] == old["working_context"]), None)
        if context_match:
            working_grade = context_match["working_context_grade"]
            working_source = {"type": "exact_prior_context", "prior_run": context_match["run"]}
        else:
            judged = benchmark._run_judge(
                trace["context"], f"working_real_{order}", fixture=fixture, truth=truth,
                codex_home=CODEX_HOME, timeout=240,
                run_dir=args.judge_root / f"working-run-{order}")
            working_grade = judged["grade"]
            working_source = {"type": "new_frozen_semantic_judge",
                              "provider_usage": judged["provider_usage"]}
        answer_judged = benchmark._run_judge(
            run["answer"], f"answer_real_{order}", fixture=fixture, truth=truth,
            codex_home=CODEX_HOME, timeout=240,
            run_dir=args.judge_root / f"answer-run-{order}")
        metrics = benchmark.context_utilization_metrics(
            truth, retrieval_grade, working_grade, answer_judged["grade"])
        records.append({
            "run_order": order, "retrieval_source": {"type": "exact_prior_selection",
                "prior_run": retrieval_match["run"], "source_count": len(sources)}
                if retrieval_match else retrieval_source,
            "working_source": working_source, "context_trace_sha256": sha256(trace["context"]),
            "saved_result_context_sha256": run["working_context_sha256"],
            "saved_result_context_hash_matches_trace": run["working_context_sha256"] == sha256(trace["context"]),
            "retrieval_coverage_percent": metrics["context_retrieval_coverage_percent"],
            "working_context_coverage_percent": metrics["working_context_coverage_percent"],
            "final_answer_coverage_percent": metrics["final_answer_coverage_percent"],
            "final_pass": answer_judged["grade"]["pass"],
            "answer_judge_usage": answer_judged["provider_usage"],
            "answer_grade": answer_judged["grade"],
            "working_grade": working_grade,
        })
        print(json.dumps({key: records[-1][key] for key in (
            "run_order", "retrieval_coverage_percent", "working_context_coverage_percent",
            "final_answer_coverage_percent", "final_pass")}), flush=True)
    output = {"commit_sha": configuration["commit_sha"],
              "fixture_sha256": freeze["fixture_sha256"],
              "ground_truth_sha256": freeze["ground_truth_sha256"],
              "evaluator_prompt_sha256": freeze["evaluator_prompt_sha256"],
              "records": records}
    with args.output.open("x", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)
    print(str(args.output), flush=True)


if __name__ == "__main__":
    main()

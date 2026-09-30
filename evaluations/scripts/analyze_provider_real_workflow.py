"""Build conservative request-level attribution from saved real-workflow traces."""

from __future__ import annotations

import hashlib
import json
import statistics
from pathlib import Path
from typing import Any

from conceptualize_runtime.runtime import token_count

from evaluations.scripts.run_provider_input_control_a import RESULTS

SOURCE = RESULTS / "provider-input-overhead-real-workflow-proven-v3.json"
EFFECTIVENESS = RESULTS / "provider-input-overhead-real-workflow-effectiveness.json"
SCALING = RESULTS / "provider-input-overhead-response-size-scaling.json"
OUTPUT = RESULTS / "provider-input-overhead-real-workflow-analysis.json"


def metric_delta(after: dict[str, Any], before: dict[str, Any]) -> dict[str, float | int]:
    return {"input_tokens": after["aggregate_usage"]["input_tokens"] - before["aggregate_usage"]["input_tokens"],
            "cached_input_tokens": after["aggregate_usage"]["cached_input_tokens"] - before["aggregate_usage"]["cached_input_tokens"],
            "uncached_input_tokens": after["aggregate_uncached_input_tokens"] - before["aggregate_uncached_input_tokens"],
            "output_tokens": after["aggregate_usage"]["output_tokens"] - before["aggregate_usage"]["output_tokens"],
            "request_count": after["request_count"] - before["request_count"],
            "elapsed_ms": round(after["elapsed_ms"] - before["elapsed_ms"], 2)}


def visible_context_audit(run: dict[str, Any]) -> dict[str, Any]:
    rollout = [json.loads(line) for line in Path(run["trace_path"], "rollout.jsonl").read_text(
        encoding="utf-8").splitlines()]
    outputs = [event["payload"]["output"] for event in rollout
               if event.get("type") == "response_item"
               and event.get("payload", {}).get("type") == "custom_tool_call_output"]
    response = None
    for output in outputs:
        if not isinstance(output, list):
            continue
        for part in output:
            if not isinstance(part, dict):
                continue
            try:
                decoded = json.loads(part.get("text", ""))
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(decoded, dict) and "context" in decoded:
                response = decoded
    trace = json.loads(Path(run["context_trace_path"]).read_text(encoding="utf-8"))
    if response is None:
        return {"model_visible_context_captured": False}
    context = response["context"]
    trace_context = trace["context"]
    def sha(text: str) -> str:
        return hashlib.sha256(text.encode("utf-8")).hexdigest()
    return {"model_visible_context_captured": True,
            "response_trace_id": response.get("trace_id"), "server_trace_id": trace.get("trace_id"),
            "response_context_tokens_local": token_count(context),
            "server_trace_context_tokens_local": token_count(trace_context),
            "response_context_sha256": sha(context), "server_trace_context_sha256": sha(trace_context),
            "same_context_bytes": context == trace_context,
            "context_character_delta": len(trace_context) - len(context),
            "saved_result_hash_matches_response": run["working_context_sha256"] == sha(context),
            "saved_result_hash_matches_trace": run["working_context_sha256"] == sha(trace_context),
            "model_tool_output_context_header_occurrences": sum(
                str(output).count("CONCEPTUALIZE WORKING CONTEXT") for output in outputs)}


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    effectiveness = json.loads(EFFECTIVENESS.read_text(encoding="utf-8"))
    scaling = json.loads(SCALING.read_text(encoding="utf-8"))
    slope = scaling["analysis"]["request_2_fit"]["slope"]
    by_repetition = {(run["repetition"], run["kind"]): run for run in source["runs"]}
    presence_pairs = []
    activation_pairs = []
    for repetition in (1, 2, 3):
        fminus = by_repetition[(repetition, "f-minus-1")]
        f0 = by_repetition[(repetition, "f0")]
        f1 = by_repetition[(repetition, "f1")]
        if f0["status"] == "VALID":
            presence_pairs.append({"repetition": repetition, **metric_delta(f0, fminus)})
            activation_pairs.append({"repetition": repetition, **metric_delta(f1, f0)})
    f1_records = []
    for run in [item for item in source["runs"] if item["kind"] == "f1"]:
        request_rows = []
        for request in run["requests"]:
            request_rows.append({"request_index": request["request_index"],
                                 "input_tokens": request["input_tokens"],
                                 "cached_input_tokens": request["cached_input_tokens"],
                                 "uncached_input_tokens": request["uncached_input_tokens"],
                                 "output_tokens": request["output_tokens"],
                                 "sampling_elapsed_ms": request["elapsed_ms"],
                                 "phase": request["phase"],
                                 "preceding_tool_output_tokens_local": sum(
                                     part["output_tokens_local"] for part in request["preceded_by_tool_outputs"]),
                                 "model_actions": request["model_actions"]})
        first = request_rows[0]["input_tokens"]
        f1_records.append({"repetition": run["repetition"], "run_order": run["run_order"],
                           "total_input_tokens": run["aggregate_usage"]["input_tokens"],
                           "request_count": run["request_count"],
                           "requests": request_rows,
                           "observed_conceptualize_calls": len(run["model_emitted_conceptualize_calls"]),
                           "mcp_tool_call_spans": run["host_internal_activity"]["span_counts"].get(
                               "mcp.tools.call", 0),
                           "working_context_tokens_local": run["working_context_tokens_local"],
                           "estimated_payload_input_tokens": round(
                               slope * run["working_context_tokens_local"], 2),
                           "initial_request_size_times_request_count": first * run["request_count"],
                           "estimated_repeated_initial_prefix_beyond_first": first * (run["request_count"] - 1),
                           "context_visibility": visible_context_audit(run)})
    analysis = {"commit_sha": source["base_configuration"]["commit_sha"],
                "fixture_sha256": source["base_configuration"]["fixture_sha256"],
                "base_configuration_sha256": source["base_configuration_sha256"],
                "prompt_mode": source["prompt_mode"],
                "conditions": source["summary"],
                "presence_pairs_valid_f0_only": presence_pairs,
                "activation_pairs_valid_f0_only": activation_pairs,
                "mean_presence_delta_input": statistics.mean(p["input_tokens"] for p in presence_pairs),
                "mean_activation_delta_input": statistics.mean(p["input_tokens"] for p in activation_pairs),
                "payload_scaling_slope": slope, "f1_waterfalls": f1_records,
                "effectiveness": [{key: item[key] for key in (
                    "run_order", "retrieval_coverage_percent", "working_context_coverage_percent",
                    "final_answer_coverage_percent", "final_pass")}
                    for item in effectiveness["records"]],
                "attribution_limit": "Provider request bodies are unavailable; prefix replay and payload contribution are estimates, not byte-level partitions."}
    with OUTPUT.open("x", encoding="utf-8") as file:
        json.dump(analysis, file, ensure_ascii=False, indent=2)
    print(json.dumps({"output": str(OUTPUT), "mean_presence_delta_input": analysis["mean_presence_delta_input"],
                      "mean_activation_delta_input": analysis["mean_activation_delta_input"],
                      "f1_requests": [item["request_count"] for item in f1_records]}), flush=True)


if __name__ == "__main__":
    main()

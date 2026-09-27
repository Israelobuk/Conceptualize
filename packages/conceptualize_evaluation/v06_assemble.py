"""Assemble reproducible V0.6 developer reports from raw local benchmark records."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / "evaluations" / "results"


def read(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def run(a_b_root: Path, c_root: Path, result_dir: Path = RESULTS, unused_c_root: Path | None = None) -> dict:
    a_b_root, c_root, result_dir = a_b_root.resolve(), c_root.resolve(), result_dir.resolve()
    a_path = a_b_root / "gpt-6-sol" / "mode_a_full_context" / "rep-1" / "result.json"
    b_path = a_b_root / "gpt-6-sol" / "mode_b_precompiled" / "rep-1" / "result.json"
    c_path = c_root / "gpt-6-sol" / "mode_c_autonomous_mcp" / "rep-1" / "result.json"
    modes = {"A": read(a_path), "B": read(b_path), "C": read(c_path)}
    rows = []
    for name, result in modes.items():
        usage = result.get("model_reported_usage", {})
        rows.append({
            "mode": name, "condition": result["condition"], "model": result["model"],
            "repetition": result["repetition"], "success": result["success"],
            "elapsed_ms_agent": result.get("elapsed_ms"),
            "condition_elapsed_ms_including_precompile": result.get("condition_elapsed_ms"),
            "precompile_elapsed_ms": result.get("precompile_elapsed_ms"),
            "input_tokens": usage.get("input_tokens"),
            "cached_input_tokens": usage.get("cached_input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "grade_pass": result.get("grade", {}).get("deterministic_pass"),
            "grade_coverage_percent": result.get("grade", {}).get("coverage_percent"),
            "context_tokens_precompiled": result.get("precompiled_context_tokens"),
            "context_tokens_returned": result.get("context_string_tokens_delivered_by_conceptualize"),
            "conceptualize_invoked": result.get("conceptualize_invoked"),
            "conceptualize_calls": result.get("conceptualize_call_count"),
            "host_non_mcp_tool_calls": result.get("host_non_mcp_tool_call_count"),
            "mcp_request_argument_bytes": result.get("mcp_tool_argument_payload_bytes"),
            "mcp_result_payload_bytes": result.get("mcp_tool_result_payload_bytes"),
            "mcp_result_payload_tokens": result.get("mcp_tool_result_payload_tokens"),
            "duplicate_context_avoided_tokens": result.get("duplicate_context_avoided_tokens"),
            "trace_runtime_ms": result.get("mcp_tool_elapsed_ms"),
            "trace_timings": result.get("conceptualize_traces"),
            "estimated_model_cost": result.get("estimated_model_cost"),
        })
    by_mode = {row["mode"]: row for row in rows}
    a, b, c = by_mode["A"], by_mode["B"], by_mode["C"]
    model_report = {
        "benchmark": "Conceptualize V0.6 three-mode model-context economics",
        "model": a["model"], "repetitions_per_mode": 1,
        "fixture": "evaluations/v05-conversation-problem.json",
        "fixture_version": modes["A"]["benchmark"],
        "modes": rows,
        "comparisons": {
            "B_minus_A_input_tokens": (b["input_tokens"] - a["input_tokens"])
            if b["input_tokens"] is not None and a["input_tokens"] is not None else None,
            "C_minus_A_input_tokens": (c["input_tokens"] - a["input_tokens"])
            if c["input_tokens"] is not None and a["input_tokens"] is not None else None,
            "C_minus_B_input_tokens": (c["input_tokens"] - b["input_tokens"])
            if c["input_tokens"] is not None and b["input_tokens"] is not None else None,
            "C_input_increment_when_no_tool_invoked": bool(not c["conceptualize_invoked"] and c["input_tokens"] and a["input_tokens"] and c["input_tokens"] > a["input_tokens"]),
            "all_answers_passed_rubric": all(row["grade_pass"] is True for row in rows),
        },
        "diagnostic": "A/B/C isolate full history, precompiled context without MCP, and optional autonomous MCP. One repetition is exploratory. Provider-reported input is authoritative for this run, while local tokenization estimates the context strings and MCP JSON separately.",
        "known_limitations": [
            "The Codex CLI reports turn-aggregate usage but does not expose internal prompt-component token attribution.",
            "The same deterministic grading rubric uses exact phrase checks and is not a semantic judge.",
            "No pricing snapshot was supplied; model cost is unavailable.",
        ],
        "raw_runs": [str(a_path.relative_to(ROOT)), str(b_path.relative_to(ROOT)), str(c_path.relative_to(ROOT))],
    }
    write(result_dir / "v06-three-mode.json", model_report)

    trace = c.get("trace_timings") or []
    unused_probe = None
    if unused_c_root:
        unused_path = unused_c_root.resolve() / "gpt-6-sol" / "mode_c_autonomous_mcp" / "rep-1" / "result.json"
        unused_probe = read(unused_path)
    surface_tokens = read(result_dir / "v06-mcp-surface-default.json")["profile"]["combined_token_estimate"]
    mcp_report = {
        "benchmark": "V0.6 autonomous MCP integration overhead",
        "mode_c_invoked": c["conceptualize_invoked"], "tool_calls": c.get("conceptualize_calls"),
        "host_non_mcp_tool_calls": c.get("host_non_mcp_tool_calls"),
        "input_tokens": c.get("input_tokens"),
        "input_tokens_mode_a": a.get("input_tokens"),
        "model_input_increment": model_report["comparisons"]["C_minus_A_input_tokens"],
        "mcp_argument_payload_bytes": c.get("mcp_request_argument_bytes"),
        "mcp_result_payload_bytes": c.get("mcp_result_payload_bytes"),
        "mcp_result_payload_tokens": c.get("mcp_result_payload_tokens"),
        "context_tokens_returned": c.get("context_tokens_returned"),
        "trace": trace,
        "unused_probe": ({
            "model_input_tokens": unused_probe.get("model_reported_usage", {}).get("input_tokens"),
            "mode_a_input_tokens": a.get("input_tokens"),
            "increment_over_mode_a": unused_probe.get("model_reported_usage", {}).get("input_tokens", 0) - a.get("input_tokens", 0),
            "conceptualize_invoked": unused_probe.get("conceptualize_invoked"),
            "conceptualize_calls": unused_probe.get("conceptualize_call_count"),
            "mcp_context_tokens": unused_probe.get("context_string_tokens_delivered_by_conceptualize"),
            "increment_beyond_surface_estimate": unused_probe.get("model_reported_usage", {}).get("input_tokens", 0) - a.get("input_tokens", 0) - surface_tokens,
            "raw_run": str(unused_path.relative_to(ROOT)),
        } if unused_probe else None),
        "host_accounting_unattributed_tokens": model_report["comparisons"]["C_minus_A_input_tokens"],
        "default_serialized_mcp_surface_token_estimate": surface_tokens,
        "invoked_run_increment_beyond_surface_estimate": model_report["comparisons"]["C_minus_A_input_tokens"] - surface_tokens,
        "interpretation": "The measured compact MCP schema/surface is far smaller than the provider-reported mode-C increment. The no-adoption probe still had a large increment despite zero Conceptualize calls and zero context returned, so the response payload cannot explain it. The observed cause is MCP-enabled Codex host execution/configuration; Codex turn telemetry does not expose component-level attribution, so it cannot identify which internal Codex prompt field or integration stage accounts for the remaining tokens.",
    }
    write(result_dir / "v06-mcp-integration.json", mcp_report)

    engine = read(result_dir / "v06-context-engine.json")
    session = next(task for task in engine["tasks"] if task["id"] == "session-continuation")
    write(result_dir / "v06-session-delta.json", {
        "benchmark": "V0.6 session context delta evaluation",
        "fixture_version": engine["fixture_version"], "task": session,
        "result": {"first_call_new_context_tokens": session.get("first_call_new_context_tokens"),
                   "first_call_candidate_tokens": session.get("first_call_candidate_tokens"),
                   "followup_context_tokens": session.get("followup_context_tokens"),
                   "followup_delta_smaller": session.get("delta_is_smaller"),
                   "second_call_previous_context_references": session.get("previous_context")},
        "run_type": "deterministic runtime fixture; no model invoked",
    })
    continuity = next(task for task in engine["tasks"] if task["id"] == "conversation-continuity")
    write(result_dir / "v06-redundancy.json", {
        "benchmark": "V0.6 deterministic conversation redundancy evaluation",
        "fixture_version": engine["fixture_version"], "task": continuity,
        "run_type": "deterministic content suppression; raw messages remain stored",
    })

    default = read(result_dir / "v06-mcp-surface-default.json")
    advanced = read(result_dir / "v06-mcp-surface-advanced.json")
    base_tokens = default["profile"]["combined_token_estimate"]
    advanced_tokens = advanced["profile"]["combined_token_estimate"]
    surface_report = {
        "benchmark": "V0.6 MCP serialized tool surface profile",
        "default": default, "advanced": advanced,
        "token_estimate_reduction_percent": round(100 * (advanced_tokens - base_tokens) / advanced_tokens, 2) if advanced_tokens else None,
        "limitation": "MCP server initialization/listing/resource serialization is measured locally with cl100k_base. Codex host prompt packing and provider token attribution are separate and not observable from these payload sizes.",
    }
    write(result_dir / "v06-mcp-surface.json", surface_report)
    return model_report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--a-b-root", type=Path, default=ROOT / "evaluations" / "runs" / "v06-final2")
    parser.add_argument("--c-root", type=Path, default=ROOT / "evaluations" / "runs" / "v06-final-c2")
    parser.add_argument("--unused-c-root", type=Path, default=ROOT / "evaluations" / "runs" / "v06-final-c")
    parser.add_argument("--result-dir", type=Path, default=RESULTS)
    args = parser.parse_args()
    result = run(args.a_b_root, args.c_root, args.result_dir, args.unused_c_root)
    print(json.dumps(result["comparisons"], indent=2))


if __name__ == "__main__":
    main()

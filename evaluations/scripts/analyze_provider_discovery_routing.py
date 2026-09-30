"""Audit and report the same-version Codex direct-activation comparison."""

from __future__ import annotations

import json
import statistics
from pathlib import Path

from evaluations.scripts.run_provider_discovery_routing import RUN_ROOT, catalog_requests
from evaluations.scripts.run_provider_input_control_a import RESULTS

BEFORE_GRADE = RESULTS / "provider-input-overhead-discovery-before-effectiveness.json"
AFTER_GRADE = RESULTS / "provider-input-overhead-discovery-after-effectiveness.json"
OUTPUT = RESULTS / "provider-input-overhead-discovery-optimization.json"
REPORT = RESULTS / "provider-input-overhead-discovery-optimization-report.md"


def read_phase(phase: str, grade_path: Path) -> dict:
    source = json.loads((RUN_ROOT / f"{phase}.json").read_text(encoding="utf-8"))
    grades = json.loads(grade_path.read_text(encoding="utf-8"))
    by_run = {record["run_order"]: record for record in grades["records"]}
    rows = []
    for run in source["runs"]:
        assert run["status"] == "VALID" and run["telemetry_reconciles"]
        assert len(run["model_emitted_conceptualize_calls"]) == 1
        assert not run["model_emitted_other_mcp_calls"]
        catalog = catalog_requests(run)
        grade = by_run[run["run_order"]]
        rows.append({"repetition": run["repetition"], "request_count": run["request_count"],
                     "requests": run["requests"], "catalog_request_count": len(catalog),
                     "catalog_discovery_input": sum(row["input_tokens"] for row in catalog),
                     "catalog_requests": catalog,
                     "input_tokens": run["aggregate_usage"]["input_tokens"],
                     "cached_input_tokens": run["aggregate_usage"]["cached_input_tokens"],
                     "uncached_input_tokens": run["aggregate_uncached_input_tokens"],
                     "output_tokens": run["aggregate_usage"]["output_tokens"],
                     "elapsed_ms": run["elapsed_ms"],
                     "working_context_tokens_local": run["working_context_tokens_local"],
                     "retrieval_coverage_percent": grade["retrieval_coverage_percent"],
                     "working_context_coverage_percent": grade["working_context_coverage_percent"],
                     "final_answer_coverage_percent": grade["final_answer_coverage_percent"],
                     "final_pass": grade["final_pass"],
                     "host_internal_activity": run["host_internal_activity"],
                     "conceptualize_calls": run["model_emitted_conceptualize_calls"]})
    return {"configuration": source["configuration"],
            "configuration_sha256": source["configuration_sha256"], "runs": rows}


def compare_configuration(before: dict, after: dict) -> None:
    left, right = dict(before["configuration"]), dict(after["configuration"])
    before_flags = left.pop("base_flags")
    after_flags = right.pop("base_flags")
    if left != right or after_flags[:len(before_flags)] != before_flags:
        raise RuntimeError("Before/after configuration mismatch outside routing instruction")
    if len(after_flags) != len(before_flags) + 2 or after_flags[-2] != "-c":
        raise RuntimeError("Unexpected host flag difference")
    if not after_flags[-1].startswith("developer_instructions="):
        raise RuntimeError("Expected only a developer instruction override")


def main() -> None:
    before = read_phase("before", BEFORE_GRADE)
    after = read_phase("after", AFTER_GRADE)
    compare_configuration(before, after)
    pairs = []
    for old, new in zip(before["runs"], after["runs"], strict=True):
        if old["repetition"] != new["repetition"]:
            raise RuntimeError("Pair mismatch")
        saved = old["input_tokens"] - new["input_tokens"]
        pairs.append({"repetition": old["repetition"], "provider_input_saved": saved,
                      "input_reduction_percent": round(saved / old["input_tokens"] * 100, 2),
                      "requests_removed": old["request_count"] - new["request_count"],
                      "catalog_requests_removed": old["catalog_request_count"]
                      - new["catalog_request_count"],
                      "catalog_discovery_input_removed": old["catalog_discovery_input"]
                      - new["catalog_discovery_input"],
                      "latency_saved_ms": round(old["elapsed_ms"] - new["elapsed_ms"], 2),
                      "cached_input_saved": old["cached_input_tokens"]
                      - new["cached_input_tokens"],
                      "uncached_input_saved": old["uncached_input_tokens"]
                      - new["uncached_input_tokens"]})
    means = {key: round(statistics.mean(pair[key] for pair in pairs), 2)
             for key in ("provider_input_saved", "input_reduction_percent", "requests_removed",
                         "catalog_requests_removed", "catalog_discovery_input_removed",
                         "latency_saved_ms", "cached_input_saved", "uncached_input_saved")}
    output = {"before": before, "after": after, "paired_deltas": pairs, "mean_delta": means,
              "configuration_equivalence": "only developer_instructions override differs",
              "validity": {"after_zero_separate_catalog_requests": all(
                  run["catalog_request_count"] == 0 for run in after["runs"]),
                  "after_two_provider_requests": all(
                      run["request_count"] == 2 for run in after["runs"]),
                  "all_retrieval_and_context_8_of_8": all(
                      run["retrieval_coverage_percent"] == 100
                      and run["working_context_coverage_percent"] == 100
                      for phase in (before, after) for run in phase["runs"])}}
    with OUTPUT.open("x", encoding="utf-8") as file:
        json.dump(output, file, ensure_ascii=False, indent=2)
    lines = ["# Conceptualize capability discovery optimization", "",
             f"Commit `{before['configuration']['commit_sha']}`; "
             f"CLI `{before['configuration']['codex_cli_version']}` in both phases; "
             f"frozen fixture `{before['configuration']['fixture_sha256']}`.", "",
             "Only the Codex `developer_instructions` host override differed. The frozen "
             "@Conceptualize user prompt, model, reasoning, working directory, environment, "
             "permissions, and one-tool fixture MCP server matched. The direct instruction "
             "names `mcp__conceptualize__conceptualize_context` and prohibits catalog search.", "",
             "| Phase | Run | Requests | Separate catalog requests | Catalog input | "
             "Total input | Cached | Uncached | Output | Context local | Final pass | Elapsed ms |",
             "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- | ---: |"]
    for phase_name, phase in (("Before", before), ("After", after)):
        for row in phase["runs"]:
            lines.append(f"| {phase_name} | {row['repetition']} | {row['request_count']} | "
                f"{row['catalog_request_count']} | {row['catalog_discovery_input']:,} | "
                f"{row['input_tokens']:,} | {row['cached_input_tokens']:,} | "
                f"{row['uncached_input_tokens']:,} | {row['output_tokens']:,} | "
                f"{row['working_context_tokens_local']:,} | {row['final_pass']} | "
                f"{row['elapsed_ms']:,.0f} |")
    lines += ["", "| Pair | Input saved | Reduction | Requests removed | "
              "Catalog input removed | Latency saved |",
              "| ---: | ---: | ---: | ---: | ---: | ---: |"]
    for pair in pairs:
        lines.append(f"| {pair['repetition']} | {pair['provider_input_saved']:,} | "
                     f"{pair['input_reduction_percent']}% | {pair['requests_removed']} | "
                     f"{pair['catalog_discovery_input_removed']:,} | "
                     f"{pair['latency_saved_ms']:,.0f} ms |")
    lines += [f"| Mean | {means['provider_input_saved']:,.0f} | "
              f"{means['input_reduction_percent']}% | {means['requests_removed']} | "
              f"{means['catalog_discovery_input_removed']:,.0f} | "
              f"{means['latency_saved_ms']:,.0f} ms |", "",
              "All six runs had one Conceptualize call, no task retry, and 8/8 retrieval and "
              "Working Context coverage. Final answers passed 1/3 before and 2/3 after. "
              "The after runs used exactly two provider requests each: tool call, then final answer. "
              "Two after-run code snippets performed an inline `ALL_TOOLS.find` in the same "
              "request that called Conceptualize; neither created a separate provider turn or "
              "printed the catalog. Host-internal MCP startup/tool listing remained.", "",
              "The original 0.159.0 diagnostic (81,872, 141,153, 85,718 input) showed "
              "the same discovery pattern. This report's savings use only the new matched "
              "0.159.0 before/after runs. PowerShell's `codex` command displayed 0.157.1, "
              "but the Python subprocess executable used for every measured run reported 0.159.0.", "",
              "The default MCP surface remains one tool and exposes no resources or prompts. "
              "The expensive discovery was model-emitted `exec` over `ALL_TOOLS`, not a "
              "Conceptualize MCP resource or prompt enumeration. The likely trigger was that "
              "`@Conceptualize` alone did not bind to a specific callable in this Codex host. "
              "The trace cannot reveal the model's internal reason for sometimes inspecting "
              "the catalog twice more.", "",
              "The opt-in Codex setup snippet adds a short developer instruction for direct "
              "routing. It is a host adapter; no retrieval, Working Context, benchmark, "
              "or generic MCP behavior changed. Merge the instruction with any existing "
              "developer instructions when installing the snippet, since Codex config has "
              "one top-level `developer_instructions` value.", "",
              "Remaining after-run input was 43,221–47,089 tokens across two requests. "
              "The ~3.4k-token Working Context is a minority of this total; host prefix "
              "and tool-result serialization remain, but exact provider bodies were unavailable "
              "for byte-level attribution. Do not optimize these in this phase.", ""]
    for phase_name, phase in (("Before", before), ("After", after)):
        lines += [f"## {phase_name} request timelines", ""]
        for row in phase["runs"]:
            lines += [f"### Run {row['repetition']}", ""]
            for request in row["requests"]:
                actions = [str(item.get("input", "")).strip().replace("\n", " ")
                           for item in request["model_actions"]]
                label = "catalog inspection" if any(
                    item["request_index"] == request["request_index"]
                    for item in row["catalog_requests"]) else (
                    "Conceptualize call" if any("tools.mcp__conceptualize__conceptualize_context("
                                               in action for action in actions) else "final")
                lines.append(f"- Request {request['request_index']}: {request['input_tokens']:,} "
                             f"input ({request['cached_input_tokens']:,} cached), "
                             f"{request['output_tokens']:,} output; {label}. "
                             f"Action: `{actions[0][:250] if actions else 'final answer'}`")
            lines.append("")
    with REPORT.open("x", encoding="utf-8") as file:
        file.write("\n".join(lines))
    print(json.dumps({"report": str(REPORT), "mean_delta": means,
                      "validity": output["validity"]}), flush=True)


if __name__ == "__main__":
    main()

"""Regenerate V0.4 reports from preserved raw evaluation evidence."""
import argparse
import json
from pathlib import Path
from statistics import mean

from .adoption import adoption_metrics
from .runner import ROOT, write
from .surface import encoded


def load_cohort(path, expected):
    rows = json.loads((path / "results.json").read_text(encoding="utf-8")) if (path / "results.json").exists() else []
    for row in rows:
        directory = Path(row["manifest"]["repository"]).parent
        events = [json.loads(line) for line in (directory / "host/agent-events.jsonl").read_text(encoding="utf-8").splitlines()]
        traces = json.loads((directory / "traces.json").read_text(encoding="utf-8"))
        registration = json.loads((directory / "host/registration.json").read_text(encoding="utf-8"))
        task = row["manifest"]["task"]
        registry = json.loads((ROOT / "evaluations/adoption-tasks.json").read_text())
        relevant = next((t["relevant_files"] for t in registry if t["id"] == task), [])
        if task == "receipts":
            relevant = ["shop/warehouse.py", "shop/contracts.py", "shop/checkout.py", "shop/orders.py", "test_shop.py"]
        stderr = (directory / "host/agent-stderr.txt").read_text(encoding="utf-8")
        initialization_failed = "required MCP servers failed to initialize: conceptualize" in stderr
        row["adoption"] = adoption_metrics(events, row["exploration"], traces, relevant,
            False if row["manifest"]["mode"] == "control" or initialization_failed else (True if row["execution"]["exit_code"] == 0 else None))
        row["agent_version"] = registration["agent_version"]
        row["sandbox_failures_observed"] = "apply deny-read ACLs" in stderr or "sandbox violation" in stderr
        row["account_limit_observed"] = "hit your usage limit" in stderr or any("hit your usage limit" in str(e) for e in events)
        row["mcp_calls"] = sum(e.get("type") == "item.completed" and e.get("item", {}).get("type") == "mcp_tool_call" and e["item"].get("server") == "conceptualize" for e in events)
        row["mcp_result_bytes"] = sum(len(encoded(e["item"].get("result"))) for e in events if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "mcp_tool_call" and e["item"].get("server") == "conceptualize")
        row["full_trace_bytes"] = sum(len(encoded(t)) for t in traces)
        row["api_operation_latency_ms"] = [t["latency_ms"] for t in traces]
        row["runtime_stage_timings"] = [t["result"].get("timings_ms", {}) for t in traces]
        row["client_transport_and_host_wait_ms"] = None
        row["observed_unnecessary_files"] = sorted(set(row["exploration"]["observed_files_inspected"]) - set(relevant)) if relevant else None
        row["unnecessary_scope"] = "Task oracle file set; additional tests and legitimate alternative implementations may be useful. Not total unnecessary exploration."
    pairs = []
    for repetition, task in sorted({(r["repetition"], r["manifest"]["task"]) for r in rows}):
        pair = [r for r in rows if r["repetition"] == repetition and r["manifest"]["task"] == task]
        comparable = len(pair) == 2 and {r["manifest"]["mode"] for r in pair} == {"control", "conceptualize"}
        if comparable:
            comparable = all(len({str(r["manifest"][key]) for r in pair}) == 1 for key in ("baseline", "prompt_sha256")) and len({r["agent_version"] for r in pair}) == 1 and len({r["execution"]["model"] for r in pair}) == 1
        pairs.append({"repetition": repetition, "task": task, "comparable": comparable})
    return {"expected_trials": expected, "recorded_trials": len(rows), "complete": len(rows) == expected,
            "pairs": pairs, "trials": rows}


def generate(output):
    names = {"adoption": ("v04-adoption-isolated", 12), "receipts": ("v04-receipts-repeated", 6), "negative": ("v04-negative-controls", 6)}
    cohorts = {key: load_cohort(ROOT / "evaluations/runs" / folder, count) for key, (folder, count) in names.items()}
    result = {"schema_version": 1, "complete": all(c["complete"] for c in cohorts.values()), "cohorts": cohorts,
              "excluded_setup_attempts": "v04-adoption-suite used relative fixture paths and failed before agent execution; v04-reachability-after used unconfigured database setup. Raw evidence retained.",
              "claims": "Invocation is not utility; observations do not establish causal speed or token improvement. Relationship use in final change remains unknown."}
    write(output / "ADOPTION-SUITE.json", result)
    lines = ["# Autonomous adoption evidence", "", "Status: " + ("all planned cohorts recorded" if result["complete"] else "evaluation in progress; incomplete cohorts are not final benchmark evidence"), "",
             "Explicit pre/post-change reachability proves that Codex can see and invoke inspect, receive valid responses and persist traces. Historical zero-call runs do not prove intentional rejection; their exact model-visible prompt is unavailable. Reduced schema/descriptions and clearer decision boundaries are implemented. These changes cannot be individually attributed as causes without an ablation.", "",
             "| Cohort | Task | Mode | Success | Seconds | Observed files | Repeated reads | MCP calls | Context tokens | First operation | Discovery | Useful relationship |", "|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|"]
    for name, cohort in cohorts.items():
        for row in cohort["trials"]:
            ex = row["execution"]
            ob = row["exploration"]
            ad = row["adoption"]
            lines.append(f"| {name} | {row['manifest']['task']} #{row['repetition']+1} | {row['manifest']['mode']} | {row['tests_passed']} | {ex['elapsed_seconds']:.2f} | {len(ob['observed_files_inspected'])} | {ob['observed_repeated_reads']} | {row['mcp_calls']} | {row['context_tokens']} | {ad['first_operation'] or 'none'} | {ad['when_invoked_vs_observed_discovery']} | {ad['useful_relationship_surfaced']} |")
        lines += ["", f"{name}: {cohort['recorded_trials']}/{cohort['expected_trials']} trials recorded."]
        for mode in ("control", "conceptualize"):
            trials = [r for r in cohort["trials"] if r["manifest"]["mode"] == mode]
            if trials:
                lines += [f"{mode}: {sum(r['tests_passed'] for r in trials)}/{len(trials)} checks passed; mean elapsed {mean(r['execution']['elapsed_seconds'] for r in trials):.2f}s; MCP invoked in {sum(r['adoption']['tool_invoked'] for r in trials)} trials."]
    lines += ["", "## Selective adoption and interpretation", ""]
    for name, cohort in cohorts.items():
        for row in cohort["trials"]:
            if row["manifest"]["mode"] != "conceptualize":
                continue
            ad = row["adoption"]
            if name == "negative":
                interpretation = "Skipped MCP for a clearly local edit, consistent with the intended decision boundary." if not ad["tool_invoked"] else "MCP was invoked for a local edit; this is not counted as product utility."
            elif ad["useful_relationship_surfaced"]:
                interpretation = "Delivered required relationship paths, appropriate for cross-file understanding; causal use and speed benefit remain unproven."
            elif not ad["tool_invoked"]:
                interpretation = "No MCP call. A passing manual implementation does not show that skipping was wrong, or that the context runtime affected this trial."
            else:
                interpretation = "Invocation did not establish a required delivered relationship; useful source context may still exist, so utility is inconclusive."
            lines += [f"{name}/{row['manifest']['task']} #{row['repetition']+1}: {interpretation}"]
            if row["api_operation_latency_ms"]:
                lines += [f"Persisted API operation latencies: {row['api_operation_latency_ms']} ms. Host startup, model wait and client transport are not included or inferred from these values."]
            warehouse = ad["relationship_discovery"].get("shop/warehouse.py")
            if warehouse:
                lines += [f"Warehouse relationship discovery: {warehouse['relative_to_source_discovery']} (surfaced event {warehouse['surfaced_step']}, source evidence event {warehouse['observed_source_evidence_step']}, explicit read event {warehouse['observed_read_step']})."]
    lines += ["", "Files/read counts are supported command-derived lower bounds. Discovery also considers source-bearing rg/grep/Select-String output; plain directory/file listings do not establish a relationship. Useful relationships mean required oracle paths appeared in delivered relationship metadata, not merely in the full trace. Their causal use in changes remains unknown. Positive results do not imply faster execution; unnecessary-files proxies include legitimate tests and alternative implementations. Agent usage, cached tokens, wire bytes, full trace bytes, comparability checks and sandbox/account-limit observations are in ADOPTION-SUITE.json.", "", "Coding agent trials ran serially on a shared development host; local validation and normal background activity were not eliminated. Scheduling, approval/sandbox failures and provider effects remain timing confounders. The eight connected-but-unused trials are separate in BASELINE-OVERHEAD.md. Historical V0.2/V0.3 evidence is unchanged. No model runs inside Conceptualize."]
    (output / "ADOPTION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, default=ROOT)
    args = parser.parse_args()
    result = generate(args.output)
    print(json.dumps({"complete": result["complete"], "recorded": {k: v["recorded_trials"] for k, v in result["cohorts"].items()}}))


if __name__ == "__main__":
    main()

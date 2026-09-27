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
        if (directory / "posthoc-validation.json").exists():
            row["independent_fixture_regression"] = json.loads((directory / "posthoc-validation.json").read_text(encoding="utf-8"))
        row["sandbox_failures_observed"] = "apply deny-read ACLs" in stderr or "sandbox violation" in stderr
        row["account_limit_observed"] = "hit your usage limit" in stderr or any("hit your usage limit" in str(e) for e in events)
        row["mcp_calls"] = sum(e.get("type") == "item.completed" and e.get("item", {}).get("type") == "mcp_tool_call" and e["item"].get("server") == "conceptualize" for e in events)
        row["mcp_result_bytes"] = sum(len(encoded(e["item"].get("result"))) for e in events if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "mcp_tool_call" and e["item"].get("server") == "conceptualize")
        row["full_trace_bytes"] = sum(len(encoded(t)) for t in traces)
        row["api_operation_latency_ms"] = [t["latency_ms"] for t in traces]
        row["runtime_stage_timings"] = [
            {
                **t["result"].get("timings_ms", {}),
                **{f"overhead_{key}": value for key, value in t["result"].get("overhead", {}).items()},
            }
            for t in traces
        ]
        row["client_transport_and_host_wait_ms"] = None
        row["observed_files_outside_task_oracle"] = sorted(set(row["exploration"]["observed_files_inspected"]) - set(relevant)) if relevant else None
        row["observed_unnecessary_files"] = None
        row["unnecessary_scope"] = "Outside-oracle files are a descriptive list, not proven unnecessary reads; useful tests and alternative implementations may lie outside the oracle. Actual unnecessary reads remain unknown."
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
    lines += ["", "Files/read counts are supported command-derived lower bounds. Discovery also considers source-bearing rg/grep/Select-String output; plain directory/file listings do not establish a relationship. Useful relationships mean required oracle paths appeared in delivered relationship metadata, not merely in the full trace. Their causal use in changes remains unknown. Positive results do not imply faster execution; outside-oracle file lists may include useful tests and alternative implementations, so actual unnecessary reads remain null. Agent usage, cached tokens, wire bytes, full trace bytes, comparability checks and sandbox/account-limit observations are in ADOPTION-SUITE.json.", "", "Negative controls use independent AST/value/behavior checks; completed fixture regressions and changed-file scope are separately retained in each trial. Coding agent trials ran serially on a shared development host; local validation and normal background activity were not eliminated. Scheduling, approval/sandbox failures and provider effects remain timing confounders. The eight connected-but-unused trials are separate in BASELINE-OVERHEAD.md. Historical V0.2/V0.3 evidence is unchanged. No model runs inside Conceptualize."]
    (output / "ADOPTION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    results_dir = output / "evaluations" / "results" if output == ROOT else output / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    for cohort_name, filename in (("adoption", "v04-adoption.json"),
                                  ("negative", "v04-negative-controls.json"),
                                  ("receipts", "v04-receipts.json")):
        write(results_dir / filename, cohorts[cohort_name])

    baseline_path = ROOT / "evaluations/results/v04-unused-connection.json"
    baseline = json.loads(baseline_path.read_text(encoding="utf-8")) if baseline_path.exists() else None
    write(results_dir / "v04-baseline-overhead.json", baseline)

    before = json.loads((ROOT / "evaluations/results/v04-mcp-surface-before.json").read_text(encoding="utf-8"))
    after = json.loads((ROOT / "evaluations/results/v04-mcp-surface-after.json").read_text(encoding="utf-8"))
    def surface_metrics(payload):
        return payload.get("profile", payload.get("after", payload))
    surface = {"before": surface_metrics(before), "after": surface_metrics(after),
               "payload_observation": after.get("actual_inspect_result"),
               "host_prompt_token_effect": None,
               "scope": "Serialized MCP JSON and a captured host event; model-visible token packing and duplicate consumption are unavailable."}
    old_listing = surface["before"].get("tool_listing_bytes")
    new_listing = surface["after"].get("tool_listing_bytes")
    surface["tool_listing_bytes_reduction"] = old_listing - new_listing if old_listing is not None and new_listing is not None else None
    surface["tool_listing_reduction_percent"] = round((old_listing-new_listing)/old_listing*100, 2) if old_listing and new_listing is not None else None
    write(results_dir / "v04-mcp-surface.json", surface)

    # Stage timings are collected from persisted API results. Transport and indexing are not
    # inferred from these operation-local measurements.
    overhead_samples = {}
    for cohort in cohorts.values():
        for trial in cohort["trials"]:
            for trace in trial.get("runtime_stage_timings", []):
                for name, value in trace.items():
                    if isinstance(value, (int, float)):
                        overhead_samples.setdefault(name, []).append(value)
    runtime_overhead = {"stage_samples_ms": {name: values for name, values in sorted(overhead_samples.items())},
                        "stage_mean_ms": {name: round(mean(values), 3) for name, values in sorted(overhead_samples.items()) if values},
                        "scope": "Persisted operation stage timings from actual adoption/receipt traces. MCP transport and per-run Git indexing analysis are not separable in these samples."}
    write(results_dir / "v04-runtime-overhead.json", runtime_overhead)

    adoption_rows = cohorts["adoption"]["trials"]
    receipt_rows = cohorts["receipts"]["trials"]
    negative_rows = cohorts["negative"]["trials"]
    unused_trials = (baseline or {}).get("trials", [])
    pairwise_rows = []
    for cohort_name, cohort in cohorts.items():
        keys = sorted({(r["repetition"], r["manifest"]["task"]) for r in cohort["trials"]})
        for repetition, task in keys:
            pair = {r["manifest"]["mode"]: r for r in cohort["trials"]
                    if r["repetition"] == repetition and r["manifest"]["task"] == task}
            if not {"control", "conceptualize"} <= pair.keys():
                continue
            def mode_cell(row):
                files = len(row["exploration"].get("observed_files_inspected", []))
                relevant = len(row.get("adoption", {}).get("required_relationship_paths_surfaced", []))
                repeats = row["exploration"].get("observed_repeated_reads")
                return (f"{bool(row.get('tests_passed'))}; {row['execution']['elapsed_seconds']:.2f}s; "
                        f"{files} files*; {relevant} required relationships; {repeats} repeats; "
                        f"{row.get('context_tokens')} context tokens")
            pairwise_rows.append(
                f"| {cohort_name}: {task} #{repetition + 1} | {mode_cell(pair['control'])} | {mode_cell(pair['conceptualize'])} |"
            )
    def cohort_line(name, rows):
        done = sum(bool(r.get("tests_passed")) for r in rows)
        enabled = [r for r in rows if r.get("manifest", {}).get("mode") == "conceptualize"]
        calls = sum(bool(r.get("adoption", {}).get("tool_invoked")) for r in enabled)
        return f"{name}: {done}/{len(rows)} runs passed independent checks; Conceptualize invoked in {calls}/{len(enabled)} enabled runs."
    v04_lines = ["# V0.4 completion and evidence", "",
      "Conceptualize is model-independent repository context infrastructure. It runs no AI model. The report describes measured behavior and limits; invocation alone is not counted as utility.", "",
      "## 1. MCP reachability", "",
      "The preserved before/after Codex reachability checks and stdio surface capture report six tools. The post-change autonomous adoption cohort is recorded separately; SDK handshake alone is not host reachability.", "",
      "## 2. Autonomous adoption", "", cohort_line("Six cross-file tasks (paired modes)", adoption_rows),
      "Required relationships in result traces are measured against independent task oracles. Read timing and relationship delivery are evidence; appearance in the final patch is not proof of causal use.", "",
      "## 3. Negative controls", "", cohort_line("Three local tasks (paired modes)", negative_rows),
      "Local edits are expected to skip MCP when repository context is already sufficient. Actual choices are retained per trial.", "",
      "## 4. Receipt repeated runs", "", cohort_line("Three paired repetitions", receipt_rows),
      "All attempts remain preserved in ignored raw run folders. Sample size is small and does not establish statistical significance or a speed improvement.", "",
      "## Paired task observations", "",
      "Each pair uses the same prompt and repository baseline. `files*` is a command-derived lower bound; required-relationship count records oracle paths surfaced by delivered Conceptualize relationships. Timing versus independent discovery is separately recorded where supported and otherwise unknown. Unnecessary files and corrective iterations were not reliably measurable and remain unknown.", "",
      "| Cohort/task | Control: pass; time; files*; relationships; repeats; context tokens | Conceptualize: pass; time; files*; relationships; repeats; context tokens |",
      "|---|---|---|"] + pairwise_rows + ["",
      "## 5. MCP surface size", "",
      f"Six tools remain exposed. Serialized tool listing fell from {old_listing} to {new_listing} bytes ({surface['tool_listing_reduction_percent']}%); schema and description measurements are in `results/v04-mcp-surface.json`.", "",
      "## 6. Compact response impact", "",
      "The captured inspect response includes compact structured/text payload sizes alongside full API result and trace sizes. Host consumption of both text and structured copies is unknown, so bytes are not converted into claimed model-token savings.", "",
      "## 7. Connected-but-unused overhead", "",
      f"The preserved baseline has {len(unused_trials)} real trials, no MCP invocations, and a mean elapsed time of {((baseline or {}).get('summary', {}).get('connected', {}).get('mean_seconds'))} seconds connected versus {((baseline or {}).get('summary', {}).get('control', {}).get('mean_seconds'))} seconds control. The consistent input-token difference and timing do not isolate causation; host startup/initialization remain unavailable.", "",
      "## 8. Runtime overhead", "",
      "Persisted operation-stage samples and means are in `results/v04-runtime-overhead.json`, including graph traversal, Git/index lookup, scoring, context compilation, cache, and database trace timings where present. MCP transport is not separately measured; API timings do not include host waiting or model time.", "",
      "## 9. Limitations", "",
      "Runs are small, local, and exposed to host/provider scheduling and cache effects. Files inspected are command-derived lower bounds; actual unnecessary reads, complete files-inspected telemetry, and causal use in edits are not available. MCP JSON byte counts are not model tokens. Some startup and token telemetry is null by design where the host did not expose it.", "",
      "## 10. What is and is not demonstrated", "",
      "The evidence demonstrates that an external Codex agent can reach and autonomously invoke Conceptualize, that deterministic context relationships are delivered and traced, and that simple local tasks can serve as negative controls. It does not demonstrate that Conceptualize makes tasks faster, reduces model tokens, improves success probability, or caused any particular code change. The initial 93-second control versus 122-second enabled pair both passed; no speed benefit is claimed.", "",
      f"{cohort_line('Adoption', adoption_rows)} {cohort_line('Negative controls', negative_rows)} {cohort_line('Receipts', receipt_rows)}", ""]
    (output / "evaluations" / "V04.md" if output == ROOT else output / "V04.md").write_text("\n".join(v04_lines), encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, default=ROOT)
    args = parser.parse_args()
    result = generate(args.output)
    print(json.dumps({"complete": result["complete"], "recorded": {k: v["recorded_trials"] for k, v in result["cohorts"].items()}}))


if __name__ == "__main__":
    main()

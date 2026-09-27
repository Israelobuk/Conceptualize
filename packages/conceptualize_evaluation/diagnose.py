"""Audit every preserved pair; unknown times stay unknown."""

import argparse
import json
from pathlib import Path

from conceptualize_runtime.patterns import detect

from .runner import write


def observed_waits(events, arrivals):
    """Arrival-based spans; overlapping calls are retained, never summed as idle."""
    started = {}
    spans = []
    for step, event in enumerate(events):
        item = event.get("item", {})
        if item.get("type") not in {"command_execution", "mcp_tool_call"}:
            continue
        identity = item.get("id")
        if event.get("type") == "item.started" and step in arrivals:
            started[identity] = (step, arrivals[step])
        elif event.get("type") == "item.completed" and identity in started and step in arrivals:
            first_step, first_ms = started.pop(identity)
            spans.append({"kind": item["type"], "item_id": identity,
                          "start_step": first_step, "end_step": step,
                          "arrival_span_ms": max(0, arrivals[step] - first_ms)})
    return spans


def discovery_comparison(rows):
    modes = {r["mode"]: r for r in rows}
    result = {"category": "inconclusive", "enabled_minus_control_ms": None,
              "scope": "First supported relevant-file observation, buffered CLI arrival timestamps, modified-file proxy. Earlier observation is not a causal MCP benefit.",
              "similarity_window_ms": 1000}
    if set(modes) != {"control", "conceptualize"} or any(r["outcome"] != "success" for r in rows):
        return result
    values = [modes[m].get("time_to_first_relevant_file_ms") for m in ("control", "conceptualize")]
    if any(v is None for v in values):
        return result
    difference = values[1] - values[0]
    result["enabled_minus_control_ms"] = difference
    result["category"] = "context discovered similarly" if abs(difference) <= 1000 else (
        "context discovered earlier" if difference < 0 else "context discovered later")
    return result


def outcome(result):
    signals = result.get("failure_signals", {})
    if signals.get("account_usage_limit"):
        return "blocked_incomplete"
    if result.get("task_completion"):
        return "success"
    if result.get("agent_exit_code") != 0 or any(signals.values()):
        return "incomplete"
    return "completed_failure"


def diagnose_run(directory):
    result = json.loads((directory / "result.json").read_text(encoding="utf-8"))
    events = [
        json.loads(line)
        for line in (directory / "agent-events.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    observed = result.get("exploration", {})
    relevant = set(result.get("coverage", {}).get("relevant_files_proxy", []))
    reads = observed.get("first_observed_read", {})
    discovery = {p: step for p, step in reads.items() if p in relevant}
    source_discovery = {}
    calls = []
    for step, event in enumerate(events):
        item = event.get("item", {})
        if (
            event.get("type") != "item.completed"
            or item.get("type") != "mcp_tool_call"
            or item.get("server") != "conceptualize"
        ):
            continue
        raw = item.get("result") or {}
        payload = raw.get("structured_content") or raw.get("structuredContent") or {}
        for p in payload.get("included_files", []):
            if p in relevant:
                discovery[p] = min(step, discovery.get(p, step))
        for unit in payload.get("deliveries", []):
            if unit.get("level") in {"source", "pack"}:
                source_discovery.setdefault(unit["path"], step)
        calls.append(
            {
                "operation": payload.get(
                    "operation", item.get("tool", "").removeprefix("conceptualize_")
                ),
                "inputs": item.get("arguments", {}),
                "step": step,
                "metrics": payload.get("metrics", {}),
                "selected_files": payload.get("selected_files", []),
                "included_files": payload.get("included_files", []),
                "deliveries": payload.get("deliveries", []),
                "status": item.get("status"),
                "error": item.get("error"),
                "timings_ms": payload.get("timings_ms", {}),
                "overhead": payload.get("overhead", {}),
            }
        )
    patterns = detect(calls)
    for call in calls:
        if call["operation"] == "pack":
            already_read = [
                u["path"]
                for u in call["deliveries"]
                if u.get("level") in {"source", "pack"}
                and reads.get(u["path"], float("inf")) < call["step"]
            ]
            if already_read:
                patterns.append(
                    {
                        "pattern": "pack_after_host_reads",
                        "step": call["step"],
                        "evidence": {"files": already_read},
                        "interpretation": "Host reads are not MCP delivery history; runtime cannot deduplicate undisclosed host reads.",
                    }
                )
    category = "inconclusive"
    basis = []
    early_source = [
        p
        for p, step in source_discovery.items()
        if p in relevant and p in reads and step < reads[p]
    ]
    extra_source = sorted(set(source_discovery) - relevant)
    if outcome(result) == "success" and calls:
        if early_source:
            category = "context discovered earlier"
            basis = [
                "MCP source precedes a supported subsequent host read in this run",
                sorted(early_source),
            ]
        elif patterns:
            category = "repeated/redundant exploration"
            basis = ["Observed sequence flags, not proof the calls were unnecessary"]
        elif len(extra_source) >= 5:
            category = "excessive context"
            basis = ["At least five source files outside modified-file proxy", extra_source]
    timeline_path = directory / "event-timeline.jsonl"
    arrivals = (
        {
            x["event_step"]: x["arrival_elapsed_ms"]
            for x in [json.loads(line) for line in timeline_path.read_text().splitlines()]
        }
        if timeline_path.exists()
        else {}
    )
    first_test = min(
        (step for p, step in discovery.items() if Path(p).name.startswith("test_")), default=None
    )
    http_times = [c["timings_ms"].get("mcp_http_round_trip") for c in calls]
    return {
        "task": result["task"],
        "mode": result["mode"],
        "outcome": outcome(result),
        "diagnostic_category": category,
        "category_basis": basis,
        "time_to_first_relevant_file_ms": arrivals.get(min(discovery.values(), default=None)),
        "time_to_first_required_dependency_ms": None,
        "time_to_first_relevant_test_ms": arrivals.get(first_test),
        "first_relevant_event_step": min(discovery.values(), default=None),
        "first_relevant_test_event_step": first_test,
        "first_required_dependency_event_step": None,
        "discovery_events": discovery,
        "source_events": source_discovery,
        "total_files_inspected": None,
        "observed_files_inspected": observed.get("observed_files_inspected"),
        "irrelevant_files_inspected": None,
        "observed_non_relevance_proxy_files": result.get("coverage", {}).get(
            "observed_unnecessary_files_inspected"
        ),
        "repeated_reads": observed.get("observed_repeated_reads"),
        "searches": observed.get("searches"),
        "grep_operations": observed.get("grep_operations"),
        "mcp_calls": len(calls),
        "mcp_successful_calls": sum(c.get("status") == "completed" for c in calls),
        "mcp_failed_calls": sum(c.get("status") == "failed" for c in calls),
        "context_tokens": result.get("context_tokens_returned"),
        "duplicate_tokens_avoided": result.get("coverage", {}).get("duplicate_tokens_avoided"),
        "runtime_http_ms": sum(http_times) if all(isinstance(t, (int, float)) for t in http_times) else None,
        "agent_idle_or_tool_wait_ms": None,
        "observed_tool_wait_spans": observed_waits(events, arrivals),
        "wait_scope": "CLI event arrival spans include buffering; overlapping spans are not agent idle time.",
        "corrective_iterations": result.get("corrective_iterations"),
        "elapsed_seconds": result.get("execution_seconds"),
        "patterns": patterns,
        "calls": calls,
        "failure_signals": result.get("failure_signals"),
        "limits": "Old logs have event ordering, not per-event elapsed timestamps. No required-dependency oracle. File relevance is modified-source/test proxy. Category describes observable evidence only.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directories", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    diagnoses = []
    planned = set()
    for cohort in args.directories:
        config = cohort / "run-config.json"
        if config.exists():
            planned.update((cohort.name, task) for task in json.loads(config.read_text(encoding="utf-8")).get("tasks", []))
        for path in sorted(cohort.glob("*/result.json")):
            diagnoses.append(
                {"cohort": cohort.name, "run_path": str(path.parent), **diagnose_run(path.parent)}
            )
    pairs = []
    for cohort, task in sorted(planned | {(d["cohort"], d["task"]) for d in diagnoses}):
        runs = [d for d in diagnoses if d["cohort"] == cohort and d["task"] == task]
        pairs.append(
            {"cohort": cohort, "task": task, "runs": runs, "matched_available": len(runs) == 2,
             "discovery_comparison": discovery_comparison(runs),
             "missing_modes": sorted({"control", "conceptualize"} - {r["mode"] for r in runs})}
        )
    write(
        args.output.with_suffix(".json"),
        {
            "pairs": pairs,
            "rules": "Descriptive flags; no quality score. Blocking is not a completed task failure.",
        },
    )
    lines = [
        "# Per-pair protocol diagnosis",
        "",
        "Unknown elapsed discovery and waiting times remain null. Event steps cannot be translated to seconds. Classification is descriptive and uses a changed-file relevance proxy, not semantic judgment. Shipping usage interruption is blocked/incomplete; previous check results describe repository state, not a completed benchmark failure.",
        "",
        "| Cohort | Task | Mode | Outcome | Category | First relevant event | Reads (observed unique) | Searches | MCP | HTTP ms |",
        "|---|---|---|---|---|---:|---:|---:|---:|---:|",
    ]
    for d in diagnoses:
        http_label = f"{d['runtime_http_ms']:.1f}" if d["runtime_http_ms"] is not None else "—"
        lines.append(
            f"| {d['cohort']} | {d['task']} | {d['mode']} | {d['outcome']} | {d['diagnostic_category']} | {d['first_relevant_event_step']} | {len(d['observed_files_inspected'] or [])} | {d['searches']} | {d['mcp_calls']} | {http_label} |"
        )
    lines += ["", "## Pattern evidence"]
    lines += ["", "## Pairwise first-observation comparison", "",
              "Buffered arrival timestamps and modified-file proxy only; within 1,000 ms is labelled similar. Unknown times remain inconclusive. This is not a causal MCP effect."]
    for pair in pairs:
        comparison = pair["discovery_comparison"]
        lines += [f"- {pair['cohort']} / {pair['task']}: {comparison['category']}; enabled minus control ms: {comparison['enabled_minus_control_ms']}."]
    for pair in pairs:
        if pair["missing_modes"]:
            lines += ["", f"Unavailable result: {pair['cohort']} / {pair['task']} / {', '.join(pair['missing_modes'])}. Preserve runner logs; no outcome inferred."]
    for d in diagnoses:
        if d["patterns"]:
            lines += [
                "",
                f"### {d['cohort']} / {d['task']} / {d['mode']}",
                "",
                "```json",
                json.dumps(d["patterns"], indent=2),
                "```",
            ]
    args.output.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    main()

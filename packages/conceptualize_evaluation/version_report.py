"""Reproducible V0.2/V0.3 comparison from retained attempts, never synthetic measurements."""

import argparse
import json
from pathlib import Path
from statistics import mean

from .diagnose import diagnose_run, outcome
from .protocol_benchmark import stage_statistics
from .runner import ROOT, write


def cohort(directory):
    rows = []
    for task in json.loads((ROOT / "evaluations/tasks.json").read_text(encoding="utf-8")):
        for mode in ("control", "conceptualize"):
            folder = directory / f"{task['id']}-{mode}"
            path = folder / "result.json"
            if path.exists():
                result = json.loads(path.read_text(encoding="utf-8"))
                rows.append({"task": task["id"], "mode": mode, "outcome": outcome(result),
                             "result": result, "diagnosis": diagnose_run(folder)})
            else:
                rows.append({"task": task["id"], "mode": mode, "outcome": "unavailable",
                             "result": None, "diagnosis": None,
                             "runner_log": str(directory / f"{task['id']}-{mode}.log")})
    return rows


def generate(old, current, output):
    cohorts = {"v02": cohort(old), "v03": cohort(current)}
    comparisons = []
    for before, after in zip(cohorts["v02"], cohorts["v03"]):
        identity_keys = ("task", "mode", "baseline", "prompt_sha256", "model", "agent_version", "suite_sha256")
        comparable = bool(before["result"] and after["result"] and all(
            before["result"].get(k) == after["result"].get(k) for k in identity_keys))
        comparisons.append({"task": before["task"], "mode": before["mode"],
                            "same_task_identity": comparable,
                            "elapsed_difference_seconds": after["result"]["execution_seconds"] - before["result"]["execution_seconds"]
                            if comparable else None})
    statistics = {}
    for version, rows in cohorts.items():
        statistics[version] = {}
        for mode in ("control", "conceptualize"):
            available = [r for r in rows if r["mode"] == mode and r["result"]]
            calls = [call for r in available for call in r["diagnosis"]["calls"]
                     if call["status"] == "completed"]
            statistics[version][mode] = {
                "available_attempts": len(available),
                "successful_attempts": sum(r["outcome"] == "success" for r in available),
                "mean_elapsed_seconds_all_available": mean(r["result"]["execution_seconds"] for r in available) if available else None,
                "observed_unique_files_sum": sum(len(r["diagnosis"]["observed_files_inspected"] or []) for r in available),
                "mcp_attempts": sum(r["diagnosis"]["mcp_calls"] for r in available),
                "successful_mcp_calls": len(calls),
                "stage_statistics": stage_statistics(calls),
            }
    write(output.with_suffix(".json"), {"cohorts": cohorts, "comparisons": comparisons, "statistics": statistics})
    lines = ["# V0.2 versus V0.3", "",
             "All original ten tasks are retained. Separate executions are observational cohorts, not a controlled runtime-version causal experiment. Unknown values remain unavailable. Relevant files use the modified-source/test proxy; unchanged required dependencies are not fully measured.", "",
             "| Task | Mode | V0.2 outcome | V0.3 outcome | V0.2 / V0.3 seconds | Observed files | MCP attempts |", "|---|---|---|---|---:|---:|---:|"]
    for before, after in zip(cohorts["v02"], cohorts["v03"]):
        def value(row, field):
            if not row["result"]:
                return "—"
            if field == "files":
                return len(row["diagnosis"]["observed_files_inspected"] or [])
            return row["result"]["execution_seconds"] if field == "seconds" else row["diagnosis"]["mcp_calls"]
        lines.append(f"| {before['task']} | {before['mode']} | {before['outcome']} | {after['outcome']} | {value(before,'seconds')} / {value(after,'seconds')} | {value(before,'files')} / {value(after,'files')} | {value(before,'mcp')} / {value(after,'mcp')} |")
    lines += ["", "## Aggregate and stage percentiles", "", "```json", json.dumps(statistics, indent=2), "```", "",
              "CLI arrival spans are retained per operation; they include buffering and do not establish model idle time. P50/P95 use nearest rank, report sample counts and leave missing stages null. HTTP transport is a client residual. Stage timers overlap; do not sum them as a complete time decomposition.", "",
              "Version identity checks are in JSON. V0.2 recovery, rejected calls, blocked Shipping, and V0.3 harness-contaminated attempts remain in separate diagnosis reports and raw directories. No attempt is silently replaced."]
    output.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--v02", type=Path, required=True)
    parser.add_argument("--v03", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    generate(args.v02, args.v03, args.output)


if __name__ == "__main__":
    main()

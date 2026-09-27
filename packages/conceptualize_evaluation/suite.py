"""Run matched external-agent pairs and regenerate reports from preserved evidence."""

import argparse
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from statistics import mean, median

from .diagnose import outcome
from .runner import ROOT, compare, write


def report(directory):
    pairs = []
    missing = []
    tasks = json.loads((ROOT / "evaluations/tasks.json").read_text(encoding="utf-8"))
    config_path = directory / "run-config.json"
    config = json.loads(config_path.read_text(encoding="utf-8")) if config_path.exists() else {}
    if config.get("tasks"):
        tasks = [t for t in tasks if t["id"] in config["tasks"]]
    for task in tasks:
        paths = [
            directory / f"{task['id']}-{mode}" / "result.json"
            for mode in ("control", "conceptualize")
        ]
        if not all(p.exists() for p in paths):
            missing.append(task["id"])
            continue
        pairs.append(compare(*paths))
    rows = []
    for pair in pairs:
        for run in pair["runs"]:
            observed = run.get("exploration") or {}
            coverage = run.get("coverage") or {}
            rows.append(
                {
                    "task": pair["task"],
                    "mode": run["mode"],
                    "success": run["task_completion"],
                    "outcome": outcome(run),
                    "seconds": run["execution_seconds"],
                    "observed_files": len(observed.get("observed_files_inspected", [])),
                    "relevant_surfaced": coverage.get("relevant_files_surfaced"),
                    "relevant_discovered": sorted(
                        (
                            set(observed.get("observed_files_inspected", []))
                            | set(coverage.get("relevant_files_surfaced", []))
                        )
                        & set(coverage.get("relevant_files_proxy", []))
                    ),
                    "mcp_operations": run.get("conceptualize_operations", 0),
                    "provider_disruptions": run.get("provider_disruptions_observed", False),
                    "failure_signals": run.get("failure_signals", {}),
                    "unnecessary_observed": len(
                        coverage.get("observed_unnecessary_files_inspected", [])
                    )
                    if run["task_completion"]
                    else None,
                    "repeated_reads": observed.get("observed_repeated_reads"),
                    "context_tokens": run["context_tokens_returned"],
                    "corrective_iterations": run["corrective_iterations"],
                    "coverage": coverage,
                    "exploration": observed,
                }
            )
    aggregate = {}
    for mode in ("control", "conceptualize"):
        subset = [r for r in rows if r["mode"] == mode]
        aggregate[mode] = {
            "runs": len(subset),
            "successes": sum(r["success"] for r in subset),
            "mean_seconds": mean(r["seconds"] for r in subset) if subset else None,
            "median_seconds": median(r["seconds"] for r in subset) if subset else None,
            "provider_disrupted_runs": sum(r["provider_disruptions"] for r in subset),
            "observed_files_successful_runs": sum(
                r["observed_files"] for r in subset if r["success"]
            ),
            "observed_files_total": sum(r["observed_files"] for r in subset),
            "observed_repeated_reads_total": sum(r["repeated_reads"] or 0 for r in subset),
            "compiled_context_tokens_total": sum(r["context_tokens"] or 0 for r in subset),
        }
    clean_ids = [
        pair["task"]
        for pair in pairs
        if pair["comparable"]
        and all(
            run["task_completion"] and not run.get("provider_disruptions_observed", False)
            for run in pair["runs"]
        )
    ]
    clean = {}
    for mode in ("control", "conceptualize"):
        subset = [r for r in rows if r["mode"] == mode and r["task"] in clean_ids]
        clean[mode] = {
            "pairs": len(subset),
            "mean_seconds": mean(r["seconds"] for r in subset) if subset else None,
            "median_seconds": median(r["seconds"] for r in subset) if subset else None,
            "observed_files_total": sum(r["observed_files"] for r in subset),
        }
    result = {
        "config": config,
        "pairs": pairs,
        "rows": rows,
        "aggregate": aggregate,
        "missing_tasks": missing,
        "successful_pairs_without_logged_provider_disruption": {
            "task_ids": clean_ids,
            "statistics": clean,
        },
    }
    write(directory / "summary.json", result)
    lines = [
        "# Conceptualize paired benchmark",
        "",
        "Actual external-agent runs. Pairs validate identical task, prompt, baseline, model, CLI version and suite definition. One run per mode/task; synthetic fixture, not general product evidence.",
        "",
        "Observed reads are lower bounds from supported successful literal read commands. Relevance is a post-hoc modified-source-file proxy after independent checks pass. Unchanged but necessary files may be misclassified. Source recall is before an observed read, not proof no other read happened. Corrective iterations and complete filesystem access are unavailable (—). Context tokens measure compiled source/structure, not the entire MCP JSON response. Token savings are redundant transmission accounting, not utility.",
        "",
        "| Task | Mode | Passed | Seconds | Observed files | Relevant discovered* | Unnecessary observed* | Repeated reads | Context tokens | Corrections | MCP calls | Provider disruption |",
        "|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---|",
    ]
    for r in rows:
        values = [
            r["task"],
            r["mode"],
            r["outcome"],
            r["seconds"],
            r["observed_files"],
            ", ".join(r["relevant_discovered"]) or "—",
            r["unnecessary_observed"],
            r["repeated_reads"],
            r["context_tokens"],
            r["corrective_iterations"],
            r["mcp_operations"],
            r["provider_disruptions"],
        ]
        lines.append("| " + " | ".join("—" if v is None else str(v) for v in values) + " |")
    lines += [
        "",
        "*Relative to the modified-source proxy; not a definitive unnecessary-work count.",
        "",
        "## Aggregate",
        "",
        "```json",
        json.dumps(aggregate, indent=2),
        "```",
        "",
        "Full source recall, early discovery event steps, surfaced non-proxy files, duplicate retransmission and avoidance, searches, grep operations, listings and read evidence are in summary.json and each run/result.json. Raw agent events, traces, test outputs and diffs remain in each run directory.",
        "",
        "Missing tasks: " + (", ".join(missing) or "none"),
        "Non-comparable attempts: "
        + (", ".join(p["task"] for p in pairs if not p["comparable"]) or "none"),
        "Failure signals are retained in summary.json and per-run results, including required MCP startup and account usage-limit failures; failures are not silently discarded.",
        "",
        "Elapsed differences combine agent behavior and tool overhead. Stage timing in raw traces measures runtime overhead; timings overlap and must not be summed blindly. No conclusion of superiority follows automatically from these measurements.",
        "Provider-disrupted runs, including successful recovery, contaminate elapsed comparisons. Failed outcomes provide no relevance ground truth. Relevant discovered combines observed reads and MCP surfacing relative to the modified-source proxy; MCP-only source recall remains separate in JSON.",
        "",
        "## Successful matched pairs without logged provider disruption",
        "",
        "This separate stratum is not evidence that all network or model timing was controlled. Every excluded attempt remains in the full table above.",
        "",
        "Tasks: " + (", ".join(clean_ids) or "none"),
        "",
        "```json",
        json.dumps(clean, indent=2),
        "```",
        "",
        "## Context delivery evidence",
        "",
        "| Task | MCP relevant source files | Confirmed source-before-observed-read fraction* | Non-proxy files surfaced | Duplicate tokens avoided | Duplicate tokens resent |",
        "|---|---|---:|---:|---:|---:|",
    ]
    for row in rows:
        if row["mode"] != "conceptualize":
            continue
        c = row["coverage"]
        values = [
            row["task"],
            ", ".join(c.get("relevant_source_files_surfaced", [])) or "—",
            c.get("relevant_file_recall_before_observed_read"),
            len(c["unnecessary_files_surfaced"]) if "unnecessary_files_surfaced" in c else None,
            c.get("duplicate_tokens_avoided"),
            c.get("duplicate_context_tokens_retransmitted"),
        ]
        lines.append("| " + " | ".join("—" if v is None else str(v) for v in values) + " |")
    lines += [
        "",
        "*Only an observed subsequent read establishes ordering. Files surfaced without any observed read are listed separately in JSON; strict recall before any independent read remains unavailable. Structural map exposure is separate from source. Non-proxy counts can include unchanged necessary dependencies; do not interpret them as definitive waste.",
    ]
    (directory / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["run", "report"])
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--codex")
    parser.add_argument("--model")
    parser.add_argument("--api-url", default="http://127.0.0.1:8039")
    parser.add_argument("--workers", type=int, default=2, choices=[1, 2])
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument(
        "--tasks", help="Comma-separated task IDs; default is the complete ten-task suite"
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.action == "run":
        if not args.codex or not args.model:
            parser.error("run requires explicit --codex and --model")
        tasks = json.loads((ROOT / "evaluations/tasks.json").read_text(encoding="utf-8"))
        if args.tasks:
            requested = set(args.tasks.split(","))
            if requested - {t["id"] for t in tasks}:
                parser.error("Unknown requested task ID")
            tasks = [t for t in tasks if t["id"] in requested]
        config_path = args.output / "run-config.json"
        if config_path.exists():
            parser.error("Refusing to overwrite suite configuration/evidence")
        import hashlib

        runtime_hash = hashlib.sha256()
        for path in sorted(
            [
                *(ROOT / "packages/conceptualize_runtime").glob("*.py"),
                ROOT / "apps/mcp/conceptualize_mcp/server.py",
                ROOT / "apps/api/conceptualize/cache.py",
            ]
        ):
            runtime_hash.update(path.relative_to(ROOT).as_posix().encode())
            runtime_hash.update(path.read_bytes())
        write(
            config_path,
            {
                "tasks": [t["id"] for t in tasks],
                "model": args.model,
                "workers": args.workers,
                "timeout": args.timeout,
                "runtime_source_sha256": runtime_hash.hexdigest(),
                "cohort_note": "Independent paired runs; compare within this cohort, not as a controlled runtime-version experiment.",
            },
        )

        def pair(index, task):
            modes = ["control", "conceptualize"] if index % 2 == 0 else ["conceptualize", "control"]
            for mode in modes:
                target = args.output / f"{task['id']}-{mode}"
                if target.exists():
                    raise ValueError(f"Refusing to overwrite evidence: {target}")
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "conceptualize_evaluation.runner",
                        "run",
                        "--task",
                        task["id"],
                        "--mode",
                        mode,
                        "--output",
                        str(target),
                        "--codex",
                        args.codex,
                        "--model",
                        args.model,
                        "--api-url",
                        args.api_url,
                        "--timeout",
                        str(args.timeout),
                    ],
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                (args.output / f"{task['id']}-{mode}.log").write_text(
                    completed.stdout + completed.stderr, encoding="utf-8"
                )
                print(f"{task['id']} {mode}: runner exit {completed.returncode}", flush=True)
                if completed.returncode:
                    raise RuntimeError(f"Runner failed: {task['id']} {mode}; inspect preserved log")

        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futures = [pool.submit(pair, index, task) for index, task in enumerate(tasks)]
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception as exc:
                    print(str(exc), file=sys.stderr, flush=True)
    result = report(args.output)
    print(json.dumps(result["aggregate"], indent=2))


if __name__ == "__main__":
    main()

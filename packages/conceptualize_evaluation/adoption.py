"""Autonomous cross-file adoption, repeated receipts and local negative controls."""
import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .exploration import exploration
from .host import execute
from .runner import ROOT, assess, command, new_project, prepare, traces, write


def adoption_metrics(events, observations, trace_data, relevant, available):
    calls = [(step, e["item"]) for step, e in enumerate(events)
             if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "mcp_tool_call"
             and e["item"].get("server") == "conceptualize"]
    first = calls[0] if calls else None
    reads = [v for p, v in observations["first_observed_read"].items() if p in relevant]
    timing = "unknown"
    if first and reads:
        timing = "before observed relevant manual read" if first[0] < min(reads) else "after observed relevant manual read"
    surfaced = set()
    results_observed = False
    for _, item in calls:
        result = item.get("result") or {}
        payload = result.get("structured_content")
        if not payload:
            for content in result.get("content", []):
                if content.get("type") == "text":
                    try:
                        payload = json.loads(content["text"])
                    except (ValueError, KeyError):
                        continue
        if not isinstance(payload, dict):
            continue
        results_observed = True
        for edge in payload.get("relationships", []):
            surfaced.update([edge.get("source"), edge.get("target")])
        for key in ("consumers", "dependencies", "tests"):
            surfaced.update(payload.get("environment", {}).get(key, []))
    useful = bool(set(relevant) & surfaced) if results_observed else None
    return {"tool_available": available, "tool_invoked": bool(calls),
            "first_operation": first[1].get("tool", "").removeprefix("conceptualize_") if first else None,
            "when_invoked": timing, "useful_relationship_surfaced": useful,
            "relationship_used_in_final_change": None,
            "required_relationship_paths_surfaced": sorted(set(relevant) & surfaced),
            "limits": "Manual discovery is an explicit-command lower bound; causal use in final changes is not inferred from invocation or passing tests."}


def prepare_adoption(task, mode, destination):
    destination.mkdir(parents=True, exist_ok=False)
    repo = destination / "repository"
    shutil.copytree(ROOT / "evaluations/adoption-fixture", repo,
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    (repo / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n", encoding="utf-8")
    command(["git", "init", "-b", "main"], repo)
    command(["git", "config", "user.name", "Conceptualize evaluation"], repo)
    command(["git", "config", "user.email", "evaluation@localhost"], repo)
    command(["git", "config", "core.autocrlf", "false"], repo)
    command(["git", "add", "."], repo)
    command(["git", "commit", "-m", "Adoption fixture baseline"], repo,
            {**os.environ, "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00", "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00"})
    prompt = task["prompt"] + "\nImplement the change and run repository tests. Keep unrelated behavior unchanged. Python interpreter: " + sys.executable
    manifest = {"task": task["id"], "mode": mode, "repository": str(repo),
                "baseline": command(["git", "rev-parse", "HEAD"], repo),
                "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "prompt": prompt}
    write(destination / "manifest.json", manifest)
    return manifest


def trial(task, mode, destination, args, receipts=False):
    manifest = prepare("receipts", mode, destination) if receipts else prepare_adoption(task, mode, destination)
    repo = Path(manifest["repository"])
    prompt = (destination / "prompt.txt").read_text(encoding="utf-8") if receipts else manifest["prompt"]
    project, key = new_project(repo, "Adoption " + task["id"]) if mode == "conceptualize" else (None, None)
    result, events = execute(repo, destination / "host", prompt, args.codex, args.model, args.api_url, key)
    persisted = traces(args.api_url, key) if key else []
    write(destination / "traces.json", persisted)
    paths = command(["git", "ls-tree", "-r", "--name-only", "HEAD"], repo).splitlines()
    observed = exploration(events, paths)
    if receipts:
        for name in ("agent-events.jsonl", "agent-stderr.txt"):
            shutil.copyfile(destination / "host" / name, destination / name)
        checked = assess(destination, result["exit_code"], result["elapsed_seconds"], project, persisted, args.model)
        success = checked["task_completion"]
    elif task.get("check"):
        check = subprocess.run([sys.executable, "-m", "pytest", str(repo / "verification"),
                                str(ROOT / "evaluations/adoption-checks" / task["check"]),
                                "-q", "--import-mode=importlib"], cwd=repo,
                               env={**os.environ, "PYTHONPATH": str(repo), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"},
                               capture_output=True, text=True, encoding="utf-8", timeout=120)
        (destination / "tests.txt").write_text(check.stdout + check.stderr, encoding="utf-8")
        success = check.returncode == 0
    else:
        tree = ast.parse((repo / "relay/isolated.py").read_text())
        values = {node.targets[0].id: ast.literal_eval(node.value) for node in tree.body
                  if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name)}
        if task["id"] == "typo":
            success = values.get("GREETING") == "Hello" and values.get("TIMEOUT") == 5
        elif task["id"] == "constant":
            success = values.get("TIMEOUT") == 8 and values.get("GREETING") == "Helo"
        else:
            function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "square")
            success = any(isinstance(node, ast.Return) and isinstance(node.value, ast.Name) and node.value.id == "squared" for node in ast.walk(function))
        namespace = {}
        exec(compile(tree, "isolated.py", "exec"), namespace)
        success = success and all(namespace["square"](v) == v * v for v in (-3, 0, 4))
    row = {"manifest": manifest, "execution": result, "tests_passed": success,
           "exploration": observed, "adoption": adoption_metrics(events, observed, persisted,
                     task.get("relevant_files", []), False if mode == "control" or result.get("failure_signals", {}).get("required_mcp_startup_failed") else (True if result["exit_code"] == 0 else None)),
           "context_tokens": sum(t["returned_tokens"] for t in persisted), "trace_ids": [t["id"] for t in persisted]}
    write(destination / "adoption-result.json", row)
    return row


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--codex", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--kind", choices=["adoption", "receipts", "negative"], default="adoption")
    parser.add_argument("--repetitions", type=int, default=1)
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=False)
    tasks = json.loads((ROOT / "evaluations/adoption-tasks.json").read_text())
    if args.kind == "receipts":
        tasks = [{"id": "receipts", "relevant_files": ["shop/warehouse.py", "shop/contracts.py", "shop/orders.py"]}]
    elif args.kind == "negative":
        tasks = [
            {"id": "typo", "prompt": "Fix GREETING in relay/isolated.py from Helo to Hello. Change nothing else.", "expected": 'GREETING = "Hello"'},
            {"id": "constant", "prompt": "Change TIMEOUT in relay/isolated.py from 5 to 8. Change nothing else.", "expected": "TIMEOUT = 8"},
            {"id": "local-variable", "prompt": "Rename the local result variable in square in relay/isolated.py to squared. Preserve behavior.", "expected": "return squared"}]
    rows = []
    for repetition in range(args.repetitions):
        for index, task in enumerate(tasks):
            order = ["control", "conceptualize"] if (repetition + index) % 2 == 0 else ["conceptualize", "control"]
            for mode in order:
                row = trial(task, mode, args.output / f"{repetition}-{task['id']}-{mode}", args, args.kind == "receipts")
                row.update({"repetition": repetition, "order": order, "kind": args.kind})
                rows.append(row)
                write(args.output / "results.json", rows)
                print(json.dumps({"task": task["id"], "mode": mode, "passed": row["tests_passed"], "adoption": row["adoption"]}), flush=True)


if __name__ == "__main__":
    main()

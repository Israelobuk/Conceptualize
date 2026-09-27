"""Paired external-agent evaluation. Context runtime never calls a model."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def write(path, value):
    path.write_text(json.dumps(value, indent=2), encoding="utf-8")


def command(args, cwd, env=None):
    return subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout.strip()


def prepare(task_id: str, mode: str, destination: Path) -> dict:
    if mode not in {"control", "conceptualize"}:
        raise ValueError("Unknown evaluation mode")
    task = next(
        (
            t
            for t in json.loads((ROOT / "evaluations/tasks.json").read_text(encoding="utf-8"))
            if t["id"] == task_id
        ),
        None,
    )
    if task is None:
        raise ValueError("Unknown evaluation task")
    destination = destination.resolve()
    if destination.exists():
        raise ValueError("Run directory must not exist; preserve previous evidence")
    destination.mkdir(parents=True)
    repo = destination / "repository"
    shutil.copytree(
        ROOT / "evaluations/fixture",
        repo,
        ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"),
    )
    command(["git", "init", "-b", "main"], repo)
    command(["git", "config", "user.name", "Conceptualize evaluation"], repo)
    command(["git", "config", "user.email", "evaluation@localhost"], repo)
    command(["git", "config", "core.autocrlf", "false"], repo)
    (repo / ".gitignore").write_text("__pycache__/\n.pytest_cache/\n", encoding="utf-8")
    command(["git", "add", "."], repo)
    env = {
        **os.environ,
        "GIT_AUTHOR_DATE": "2026-01-01T00:00:00+00:00",
        "GIT_COMMITTER_DATE": "2026-01-01T00:00:00+00:00",
    }
    command(["git", "commit", "-m", "Evaluation baseline"], repo, env)
    if task.get("git_branch_fixture"):
        command(["git", "checkout", "-b", "feature/shipping"], repo)
        (repo / "shop/shipping_config.py").write_text(
            "STANDARD = 2\nEXPRESS = 7\n", encoding="utf-8"
        )
        command(["git", "add", "shop/shipping_config.py"], repo)
        command(["git", "commit", "-m", "Adjust express tariff on current branch"], repo, env)
    prompt = (
        task["prompt"]
        + "\n\nImplement the change in this repository and run its tests. Do not change unrelated behavior. Python test interpreter: "
        + sys.executable
    )
    (destination / "prompt.txt").write_text(prompt, encoding="utf-8")
    manifest = {
        "schema_version": 1,
        "task": task_id,
        "mode": mode,
        "repository": str(repo),
        "baseline": command(["git", "rev-parse", "HEAD"], repo),
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "check": task["check"],
        "category": task.get("category"),
        "suite_sha256": hashlib.sha256((ROOT / "evaluations/tasks.json").read_bytes()).hexdigest(),
    }
    write(destination / "manifest.json", manifest)
    return manifest


def event_metrics(events: list[dict]) -> dict:
    commands = []
    mcp = []
    usage = None
    final = None
    for event in events:
        item = event.get("item", {})
        if event.get("type") == "item.completed":
            if item.get("type") == "command_execution":
                commands.append(
                    {"command": item.get("command"), "exit_code": item.get("exit_code")}
                )
            elif item.get("type") == "mcp_tool_call":
                mcp.append(
                    {
                        "server": item.get("server"),
                        "tool": item.get("tool"),
                        "status": item.get("status"),
                    }
                )
            elif item.get("type") == "agent_message":
                final = item.get("text")
        if event.get("type") == "turn.completed":
            usage = event.get("usage")
    return {
        "command_executions": len(commands),
        "command_evidence": commands,
        "mcp_call_evidence": mcp,
        "agent_usage": usage,
        "agent_final_message": final,
        "files_inspected": None,
        "unnecessary_repository_reads": None,
        "corrective_iterations": None,
    }


def new_project(repo: Path, name: str) -> tuple[str, str]:
    from conceptualize.auth import create_key
    from conceptualize.db import Session
    from conceptualize.models import Project, User
    from conceptualize.service import index_project

    with Session() as db:
        user = User(email="evaluation-" + str(time.time_ns()) + "@localhost")
        db.add(user)
        db.flush()
        project = Project(user_id=user.id, name=name)
        db.add(project)
        db.flush()
        key = create_key(db, project.id)
        db.commit()
        index_project(db, project, repo)
        return project.id, key


def traces(url: str, key: str) -> list[dict]:
    import httpx

    with httpx.Client(
        base_url=url, headers={"Authorization": "Bearer " + key}, timeout=30
    ) as client:
        result = []
        offset = 0
        while True:
            response = client.get("/v1/traces", params={"limit": 100, "offset": offset})
            response.raise_for_status()
            items = response.json()["items"]
            for item in items:
                detail = client.get("/v1/traces/" + item["id"])
                detail.raise_for_status()
                result.append(detail.json())
            if len(items) < 100:
                return result
            offset += 100


def assess(
    directory: Path,
    agent_exit: int | None,
    elapsed: float | None,
    project: str | None,
    trace_data: list,
    model: str | None,
) -> dict:
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    repo = Path(manifest["repository"])
    events = []
    for line in (
        (directory / "agent-events.jsonl").read_text(encoding="utf-8").splitlines()
        if (directory / "agent-events.jsonl").exists()
        else []
    ):
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    env = {**os.environ, "PYTHONPATH": str(repo), "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}
    test_timeout = False
    try:
        test = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(repo / "test_shop.py"),
                str(ROOT / "evaluations/checks" / manifest["check"]),
                "-q",
                "--import-mode=importlib",
            ],
            cwd=repo,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )
    except subprocess.TimeoutExpired as exc:
        test_timeout = True

        def decoded(value):
            return (
                value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""
            )

        test = subprocess.CompletedProcess(
            exc.cmd,
            124,
            decoded(exc.stdout),
            decoded(exc.stderr) + "\nIndependent checks timed out after 120 seconds.",
        )
    (directory / "tests.txt").write_text(test.stdout + "\n" + test.stderr, encoding="utf-8")
    diff = command(["git", "diff", "HEAD", "--"], repo)
    (directory / "changes.diff").write_text(diff, encoding="utf-8")
    modified = (
        command(["git", "diff", "--name-only", "HEAD"], repo).splitlines()
        + command(["git", "ls-files", "--others", "--exclude-standard"], repo).splitlines()
    )
    metrics = event_metrics(events)
    from .exploration import coverage, exploration

    baseline_paths = command(["git", "ls-tree", "-r", "--name-only", "HEAD"], repo).splitlines()
    observations = exploration(events, baseline_paths)
    relevant = {p for p in modified if p.endswith(".py")}
    context_coverage = coverage(events, observations, relevant, test.returncode == 0)
    stderr_path = directory / "agent-stderr.txt"
    stderr = (
        stderr_path.read_text(encoding="utf-8", errors="replace") if stderr_path.exists() else ""
    )
    provider_disruptions = any(
        message in stderr
        for message in (
            "No such host is known",
            "workspace routing discovery failed",
            "Connection failed: error sending request",
        )
    )
    failure_signals = {
        "account_usage_limit": "hit your usage limit" in stderr
        or any("hit your usage limit" in str(e.get("error", e.get("message", ""))) for e in events),
        "provider_network_or_routing": provider_disruptions,
        "required_conceptualize_mcp_startup_failed": "required MCP servers failed to initialize: conceptualize"
        in stderr,
        "agent_timeout": agent_exit == 124,
        "independent_checks_timeout": test_timeout,
    }
    result = {
        **manifest,
        **metrics,
        "agent_exit_code": agent_exit,
        "task_completion": test.returncode == 0,
        "completion_basis": "independent behavior checks plus repository tests; not agent self-report",
        "tests_passed": test.returncode == 0,
        "tests_exit_code": test.returncode,
        "tests_timed_out": test_timeout,
        "provider_disruptions_observed": provider_disruptions,
        "failure_signals": failure_signals,
        "files_modified": sorted(set(modified)),
        "execution_seconds": elapsed,
        "project_id": project,
        "model": model,
        "conceptualize_operations": len(trace_data) if manifest["mode"] == "conceptualize" else 0,
        "context_tokens_returned": sum(t["returned_tokens"] for t in trace_data)
        if manifest["mode"] == "conceptualize"
        else 0,
        "trace_ids": [t["id"] for t in trace_data],
        "exploration": observations,
        "coverage": context_coverage,
        "measurement_limits": [
            "Files inspected, corrective iterations and unnecessary reads are not reliably exposed by Codex JSON events; values remain null.",
            "Agent token usage includes its full interaction; context tokens are separately recorded by Conceptualize.",
            "Task completion covers supplied checks, not arbitrary correctness.",
        ],
    }
    write(directory / "traces.json", trace_data)
    write(directory / "result.json", result)
    return result


def run(args):
    directory = Path(args.output).resolve()
    manifest = prepare(args.task, args.mode, directory)
    repo = Path(manifest["repository"])
    project, key = None, None
    env = dict(os.environ)
    cli = [
        args.codex,
        "exec",
        "--ephemeral",
        "--approve-for-me",
        "--skip-git-repo-check",
        "--json",
        "-C",
        str(repo),
    ]
    listing = json.loads(command([args.codex, "mcp", "list", "--json"], repo))
    for server in listing:
        cli += [
            "-c",
            "mcp_servers." + server["name"] + ".command=" + json.dumps(sys.executable),
            "-c",
            "mcp_servers." + server["name"] + ".enabled=false",
        ]
    if args.model:
        cli += ["--model", args.model]
    if args.mode == "conceptualize":
        project, key = new_project(repo, "Evaluation · " + args.task)
        env["CONCEPTUALIZE_API_KEY"] = key
        cli += [
            "-c",
            "mcp_servers.conceptualize.enabled=true",
            "-c",
            "mcp_servers.conceptualize.required=true",
            "-c",
            "mcp_servers.conceptualize.command=" + json.dumps(sys.executable),
            "-c",
            'mcp_servers.conceptualize.args=["-m", "conceptualize_mcp.server"]',
            "-c",
            'mcp_servers.conceptualize.env_vars=["CONCEPTUALIZE_API_KEY"]',
            "-c",
            "mcp_servers.conceptualize.env.CONCEPTUALIZE_API_URL=" + json.dumps(args.api_url),
        ]
    cli += ["-"]
    started = time.perf_counter()

    def capture(stream, output):
        with (directory / "event-timeline.jsonl").open("w", encoding="utf-8") as timeline:
            for step, line in enumerate(stream):
                output.write(line)
                output.flush()
                timeline.write(
                    json.dumps(
                        {
                            "event_step": step,
                            "arrival_elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                        }
                    )
                    + "\n"
                )
                timeline.flush()

    with (
        (directory / "agent-events.jsonl").open("w", encoding="utf-8") as out,
        (directory / "agent-stderr.txt").open("w", encoding="utf-8") as err,
    ):
        try:
            process = subprocess.Popen(
                cli,
                cwd=repo,
                env=env,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=err,
                text=True,
                encoding="utf-8",
            )
            reader = threading.Thread(target=capture, args=(process.stdout, out), daemon=True)
            reader.start()
            process.stdin.write((directory / "prompt.txt").read_text(encoding="utf-8"))
            process.stdin.close()
            process.wait(timeout=args.timeout)
            reader.join(timeout=10)
            exit_code = process.returncode
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    capture_output=True,
                    check=False,
                )
            else:
                process.kill()
            process.wait()
            reader.join(timeout=10)
            exit_code = 124
    elapsed = round(time.perf_counter() - started, 3)
    write(
        directory / "execution.json",
        {
            "agent_exit_code": exit_code,
            "execution_seconds": elapsed,
            "model": args.model,
            "project_id": project,
            "agent_timeout_seconds": args.timeout,
        },
    )
    # Remove credential if an external agent unexpectedly echoes it.
    if key:
        for name in ["agent-events.jsonl", "agent-stderr.txt"]:
            path = directory / name
            path.write_text(
                path.read_text(encoding="utf-8").replace(key, "[REDACTED]"), encoding="utf-8"
            )
    trace_data = traces(args.api_url, key) if key else []
    result = assess(directory, exit_code, elapsed, project, trace_data, args.model)
    result["agent_executable"] = str(Path(args.codex).resolve())
    result["agent_version"] = command([args.codex, "--version"], repo)
    result["agent_timeout_seconds"] = args.timeout
    result["mcp_autonomously_invoked"] = bool(trace_data) and args.mode == "conceptualize"
    write(directory / "result.json", result)
    print(
        json.dumps(
            {
                k: result[k]
                for k in [
                    "task",
                    "mode",
                    "task_completion",
                    "tests_passed",
                    "execution_seconds",
                    "conceptualize_operations",
                    "context_tokens_returned",
                    "trace_ids",
                ]
            },
            indent=2,
        )
    )


def compare(left: Path, right: Path) -> dict:
    a = json.loads(left.read_text(encoding="utf-8"))
    b = json.loads(right.read_text(encoding="utf-8"))
    if any(
        a.get(k) != b.get(k)
        for k in ["baseline", "prompt_sha256", "task", "model", "agent_version", "suite_sha256"]
    ):
        raise ValueError("Runs differ in baseline, task, prompt, model or agent version")
    if {a["mode"], b["mode"]} != {"control", "conceptualize"}:
        raise ValueError("Comparison requires one run of each mode")
    return {
        "schema_version": 1,
        "task": a["task"],
        "pair_identity": {
            k: a.get(k)
            for k in ("baseline", "prompt_sha256", "model", "agent_version", "suite_sha256")
        },
        "comparable": a.get("agent_timeout_seconds") == b.get("agent_timeout_seconds"),
        "comparison_limits": []
        if a.get("agent_timeout_seconds") == b.get("agent_timeout_seconds")
        else ["Agent timeout limits differ; these attempts cannot support a timing comparison"],
        "runs": [
            {
                k: r.get(k)
                for k in [
                    "mode",
                    "task_completion",
                    "tests_passed",
                    "files_modified",
                    "files_inspected",
                    "execution_seconds",
                    "command_executions",
                    "agent_usage",
                    "conceptualize_operations",
                    "context_tokens_returned",
                    "unnecessary_repository_reads",
                    "corrective_iterations",
                    "provider_disruptions_observed",
                    "failure_signals",
                    "agent_timeout_seconds",
                    "conceptualize_operations",
                    "exploration",
                    "coverage",
                ]
            }
            for r in [a, b]
        ],
        "interpretation": "One paired run is anecdotal evidence, not a general performance claim. Repeat tasks and vary run order. Unobserved metrics are null.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ["prepare", "run"]:
        p = sub.add_parser(action)
        p.add_argument("--task", required=True)
        p.add_argument("--mode", choices=["control", "conceptualize"], required=True)
        p.add_argument("--output", required=True)
        if action == "run":
            p.add_argument("--codex", default=shutil.which("codex") or "codex")
            p.add_argument("--model")
            p.add_argument(
                "--api-url",
                default=os.environ.get("CONCEPTUALIZE_API_URL", "http://127.0.0.1:8000"),
            )
            p.add_argument("--timeout", type=int, default=600)
    p = sub.add_parser("compare")
    p.add_argument("control", type=Path)
    p.add_argument("conceptualize", type=Path)
    p.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.action == "prepare":
        print(json.dumps(prepare(args.task, args.mode, Path(args.output)), indent=2))
    elif args.action == "run":
        run(args)
    else:
        result = compare(args.control, args.conceptualize)
        write(args.output, result)
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

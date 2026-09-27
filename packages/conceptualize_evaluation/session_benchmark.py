"""Related-task host-agent sequences with fresh versus resumed conversations."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .runner import command, event_metrics, new_project, traces, write

FILES = {
    "sessions.py": "def valid(session, now):\n    return now <= session['expires']\n\ndef create(now, ttl):\n    return {'expires': now + ttl}\n",
    "middleware.py": "from sessions import valid\n\ndef allowed(session, now):\n    return valid(session, now)\n",
    "oauth.py": "from sessions import create\n\ndef login(now):\n    return create(now, 60)\n",
    "test_auth.py": "from middleware import allowed\nfrom oauth import login\n\ndef test_login():\n    assert allowed(login(10), 11)\n",
}
TASKS = [
    "Sessions must expire exactly at their expiration timestamp. Apply this consistently to existing authentication callers and add a regression test.",
    "An explicitly revoked session must never authorize a request even before expiration. Missing revoked metadata must preserve compatibility. Add regression coverage.",
    "OAuth login needs an optional configurable lifetime (default 60). Reject negative lifetimes with ValueError and preserve expiration and revocation behavior. Add tests.",
]
CHECKS = [
    "from middleware import allowed; assert not allowed({'expires':10},10); assert allowed({'expires':10},9)",
    "from middleware import allowed; assert not allowed({'expires':10,'revoked':True},9); assert allowed({'expires':10},9)",
    "from oauth import login; assert login(10,20)['expires']==30; assert login(10)['expires']==70\ntry: login(10,-1)\nexcept ValueError: pass\nelse: raise AssertionError('negative lifetime accepted')",
]


def sequence(output, mode, memory, args):
    folder = output / f"{mode}-{memory}"
    folder.mkdir()
    repo = folder / "repository"
    repo.mkdir()
    for name, content in FILES.items():
        (repo / name).write_text(content, encoding="utf-8")
    command(["git", "init", "-b", "main"], repo)
    command(["git", "config", "user.name", "Evaluation"], repo)
    command(["git", "config", "user.email", "evaluation@localhost"], repo)
    env = dict(os.environ)
    overrides = []
    for server in json.loads(command([args.codex, "mcp", "list", "--json"], repo)):
        overrides += ["-c", f"mcp_servers.{server['name']}.command=" + json.dumps(sys.executable),
                      "-c", f"mcp_servers.{server['name']}.enabled=false"]
    key = None
    if mode == "conceptualize":
        _, key = new_project(repo, "Warm-agent " + memory)
        env["CONCEPTUALIZE_API_KEY"] = key
        env["CONCEPTUALIZE_SESSION_ID"] = str(uuid.uuid4())
        overrides += ["-c", "mcp_servers.conceptualize.enabled=true",
                      "-c", "mcp_servers.conceptualize.required=true",
                      "-c", "mcp_servers.conceptualize.command=" + json.dumps(sys.executable),
                      "-c", 'mcp_servers.conceptualize.args=["-m", "conceptualize_mcp.server"]',
                      "-c", 'mcp_servers.conceptualize.env_vars=["CONCEPTUALIZE_API_KEY","CONCEPTUALIZE_SESSION_ID"]',
                      "-c", "mcp_servers.conceptualize.env.CONCEPTUALIZE_API_URL=" + json.dumps(args.api_url)]
    thread = None
    results = []
    for step, task in enumerate(TASKS):
        stage = folder / f"stage-{step + 1}"
        stage.mkdir()
        baseline = hashlib.sha256(json.dumps({p.name: p.read_text(encoding="utf-8")
            for p in sorted(repo.glob("*.py"))}, sort_keys=True).encode()).hexdigest()
        prompt = task + "\nImplement the change and run tests. Python interpreter: " + sys.executable
        (stage / "prompt.txt").write_text(prompt, encoding="utf-8")
        if memory == "cold":
            env["CONCEPTUALIZE_SESSION_ID"] = str(uuid.uuid4())
        cli = [args.codex, "--approve-for-me", "exec"]
        if thread and memory == "warm":
            cli += ["resume", thread]
        else:
            cli += ["-C", str(repo)]
            if memory == "cold":
                cli += ["--ephemeral"]
        cli += ["--json", "--skip-git-repo-check", "--model", args.model, *overrides, "-"]
        before = {t["id"] for t in traces(args.api_url, key)} if key else set()
        started = time.perf_counter()
        with (stage / "agent-events.jsonl").open("w", encoding="utf-8") as out, (stage / "agent-stderr.txt").open("w", encoding="utf-8") as err:
            process = subprocess.Popen(cli, cwd=repo, env=env, stdin=subprocess.PIPE,
                                       stdout=out, stderr=err, text=True, encoding="utf-8")
            try:
                process.communicate(prompt, timeout=args.timeout)
            except subprocess.TimeoutExpired:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
                process.wait()
        elapsed = time.perf_counter() - started
        if key:
            for name in ("agent-events.jsonl", "agent-stderr.txt"):
                path = stage / name
                path.write_text(path.read_text(encoding="utf-8").replace(key, "[REDACTED]"), encoding="utf-8")
        events = []
        for line in (stage / "agent-events.jsonl").read_text(encoding="utf-8").splitlines():
            try:
                events.append(json.loads(line))
            except ValueError:
                pass
        thread = next((e["thread_id"] for e in events if e.get("type") == "thread.started"), thread)
        check = subprocess.run([sys.executable, "-c", CHECKS[step]], cwd=repo, capture_output=True, text=True)
        tests = subprocess.run([sys.executable, "-m", "pytest", "-q"], cwd=repo, capture_output=True, text=True)
        (stage / "checks.txt").write_text(check.stdout + check.stderr + tests.stdout + tests.stderr, encoding="utf-8")
        calls = [t for t in traces(args.api_url, key) if t["id"] not in before] if key else []
        write(stage / "traces.json", calls)
        metrics = event_metrics(events)
        interrupted = "usage limit" in ((stage / "agent-stderr.txt").read_text(encoding="utf-8") + json.dumps(events)).lower()
        blocked_workspace = any("workspace permissions" in e.get("item", {}).get("text", "").lower()
                                or "blocked by filesystem permissions" in e.get("item", {}).get("text", "").lower()
                                for e in events)
        result = {"stage": step + 1, "mode": mode, "memory": memory, "baseline_sha256": baseline,
                  "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(), "elapsed_seconds": elapsed,
                  "agent_exit_code": process.returncode, "outcome": "blocked_incomplete" if interrupted or blocked_workspace else
                  "success" if check.returncode == tests.returncode == 0 else "incomplete" if process.returncode else "completed_failure",
                  "checks_passed": check.returncode == 0, "tests_passed": tests.returncode == 0,
                  "metrics": metrics, "mcp_operations": len(calls), "thread_id": thread,
                  "model": args.model, "agent_version": command([args.codex, "--version"], repo)}
        write(stage / "result.json", result)
        results.append(result)
        print(f"{mode} {memory} stage {step + 1}: {result['outcome']}", flush=True)
    write(folder / "summary.json", results)


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--codex", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--timeout", type=int, default=600)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    write(output / "protocol.json", {"tasks": TASKS, "files": FILES,
        "limitations": ["Warm retains host conversation and MCP session; their effects cannot be separated.",
                        "Later-stage repository states may diverge following different agent implementations.",
                        "All three tasks retained regardless of result; no forced MCP invocations."]})
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(sequence, output, mode, memory, args)
                   for memory in ("cold", "warm") for mode in ("control", "conceptualize")]
        for future in futures:
            future.result()


if __name__ == "__main__":
    main()

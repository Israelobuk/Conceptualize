"""External Codex execution for reachability and adoption experiments only."""

import json
import os
import subprocess
import sys
import threading
from time import perf_counter

from .runner import command, event_metrics, write


def execute(repo, destination, prompt, codex, model, api_url, key=None, timeout=600, broken=False):
    destination.mkdir(parents=True, exist_ok=False)
    (destination / "prompt.txt").write_text(prompt, encoding="utf-8")
    cli = [codex, "--approve-for-me", "exec", "--ephemeral", "--json", "--skip-git-repo-check", "-C", str(repo), "--model", model]
    for server in json.loads(command([codex, "mcp", "list", "--json"], repo)):
        cli += ["-c", f"mcp_servers.{server['name']}.command=" + json.dumps(sys.executable),
                "-c", f"mcp_servers.{server['name']}.enabled=false"]
    environment = dict(os.environ)
    if key or broken:
        environment["CONCEPTUALIZE_API_KEY"] = key or ""
        cli += ["-c", "mcp_servers.conceptualize.enabled=true",
                "-c", "mcp_servers.conceptualize.required=true",
                "-c", "mcp_servers.conceptualize.command=" + json.dumps(sys.executable),
                "-c", 'mcp_servers.conceptualize.args=["-m", "conceptualize_mcp.server"]' if not broken else 'mcp_servers.conceptualize.args=["-c", "raise SystemExit(1)"]',
                "-c", 'mcp_servers.conceptualize.env_vars=["CONCEPTUALIZE_API_KEY"]',
                "-c", "mcp_servers.conceptualize.env.CONCEPTUALIZE_API_URL=" + json.dumps(api_url)]
    cli += ["-"]
    write(destination / "registration.json", {"argv": cli, "credential": "environment variable, value excluded", "model": model,
        "configured": bool(key or broken), "broken": broken, "api_url": api_url,
        "agent_version": command([codex, "--version"], repo)})
    started = perf_counter()
    def capture(stream, output):
        with (destination / "event-timeline.jsonl").open("w", encoding="utf-8") as timeline:
            for step, line in enumerate(stream):
                output.write(line)
                output.flush()
                timeline.write(json.dumps({"event_step": step, "arrival_elapsed_ms": round((perf_counter() - started) * 1000, 3)}) + "\n")
                timeline.flush()
    with (destination / "agent-events.jsonl").open("w", encoding="utf-8") as output, (destination / "agent-stderr.txt").open("w", encoding="utf-8") as errors:
        process = subprocess.Popen(cli, cwd=repo, env=environment, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True, encoding="utf-8")
        reader = threading.Thread(target=capture, args=(process.stdout, output), daemon=True)
        reader.start()
        process.stdin.write(prompt)
        process.stdin.close()
        try:
            process.wait(timeout=timeout)
            exit_code = process.returncode
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, check=False)
            else:
                process.kill()
            process.wait()
            exit_code = 124
        reader.join(timeout=10)
    if key:
        for name in ("agent-events.jsonl", "agent-stderr.txt"):
            path = destination / name
            path.write_text(path.read_text(encoding="utf-8").replace(key, "[REDACTED]"), encoding="utf-8")
    events = []
    for line in (destination / "agent-events.jsonl").read_text(encoding="utf-8").splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            pass
    timeline = [json.loads(line) for line in (destination / "event-timeline.jsonl").read_text().splitlines()]
    first = next((i for i, e in enumerate(events) if e.get("item", {}).get("type") == "agent_message"), None)
    stderr = (destination / "agent-stderr.txt").read_text(encoding="utf-8")
    failure_signals = {
        "account_usage_limit": "hit your usage limit" in stderr or any("hit your usage limit" in str(e) for e in events),
        "provider_interruptions_observed": any(x in stderr for x in ("workspace routing discovery failed", "No such host is known", "Connection failed: error sending request")),
        "required_mcp_startup_failed": "required MCP servers failed to initialize: conceptualize" in stderr,
        "timeout": exit_code == 124,
    }
    result = {"failure_signals": failure_signals, "host_retry_count": None, "exit_code": exit_code, "elapsed_seconds": round(perf_counter() - started, 3),
              "first_model_message_arrival_ms": timeline[first]["arrival_elapsed_ms"] if first is not None else None,
              "model": model, **event_metrics(events),
              "startup_time_ms": None, "mcp_initialization_time_ms": None,
              "timing_scope": "CLI arrival timestamps; host does not expose separate initialization/model scheduling timing."}
    write(destination / "execution.json", result)
    return result, events

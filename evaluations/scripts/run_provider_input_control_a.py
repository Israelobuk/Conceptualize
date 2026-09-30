"""Collect request-level Codex telemetry for a tool-free V0.9 host control.

The saved Codex rollout supplies one token_usage_record per response. A local
OTLP receiver supplies request durations. A run is valid only when those
records reconcile with the CLI turn aggregate and contain no tool calls.
"""

from __future__ import annotations

import argparse
import gzip
import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from conceptualize_evaluation import v09_capability_benchmark as benchmark
from conceptualize_runtime.runtime import token_count

ROOT = Path(__file__).resolve().parents[2]
CODEX_HOME = ROOT / "evaluations/runs/v05-benchmark-codex-home"
RUN_ROOT = ROOT / "evaluations/runs/v09/provider-input-overhead"
RESULTS = ROOT / "evaluations/results"
MODEL = "gpt-6-sol"
REASONING = "low"
USAGE_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens")
DISABLED_FEATURES = (
    "shell_tool", "view_image", "sleep_tool", "apps", "plugins",
    "browser_use", "computer_use", "image_generation", "multi_agent",
    "code_mode", "code_mode_host", "skill_search", "workspace_dependencies",
    "web_search_request", "tool_suggest",
)


class OtlpReceiver(ThreadingHTTPServer):
    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), OtlpHandler)
        self.received: list[dict[str, Any]] = []
        self.probed_requests: list[dict[str, Any]] = []


class OtlpHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        if self.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        try:
            payload = json.loads(body)
        except (ValueError, UnicodeDecodeError):
            self.send_error(400)
            return
        if self.path.endswith("/responses"):
            self.server.probed_requests.append({  # type: ignore[attr-defined]
                "tools": payload.get("tools", []),
                "additional_tools": payload.get("additional_tools", []),
                "request_keys": sorted(payload),
                "noop_present_anywhere": "noop" in json.dumps(payload, ensure_ascii=False),
            })
            self.send_error(400, "local tool-count preflight complete")
            return
        self.server.received.append({"path": self.path, "payload": payload})  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b"{}")

    def log_message(self, _format: str, *_args: object) -> None:
        pass


def _api_durations(received: list[dict[str, Any]]) -> list[float]:
    durations: list[float] = []
    for batch in received:
        for resource in batch["payload"].get("resourceSpans", []):
            for scope in resource.get("scopeSpans", []):
                for span in scope.get("spans", []):
                    if span.get("name") == "run_sampling_request":
                        start = int(span["startTimeUnixNano"])
                        end = int(span["endTimeUnixNano"])
                        durations.append(round((end - start) / 1_000_000, 2))
    return durations


def _preflight_tools(command: list[str], cwd: Path, env: dict[str, str],
                     prompt: str) -> dict[str, Any]:
    """Inspect the actual Responses request body against a local fake provider."""
    receiver = OtlpReceiver()
    thread = threading.Thread(target=receiver.serve_forever, daemon=True)
    thread.start()
    port = receiver.server_address[1]
    provider = (f'{{name="Tool probe",base_url="http://127.0.0.1:{port}/v1",'
                'wire_api="responses",env_key="CODEX_PROBE_FAKE_KEY",'
                'supports_websockets=false,request_max_retries=0}')
    probe_cmd = command[:-1] + ["--ephemeral", "-c", 'model_provider="probe"',
                                "-c", "model_providers.probe=" + provider, "-"]
    try:
        probe = subprocess.run(probe_cmd, input=prompt, cwd=cwd,
                               env={**env, "CODEX_PROBE_FAKE_KEY": "local-probe-only"},
                               capture_output=True, text=True, encoding="utf-8",
                               errors="replace", timeout=30, check=False)
    finally:
        receiver.shutdown()
        thread.join(timeout=5)
        receiver.server_close()
    requests = receiver.probed_requests
    if len(requests) != 1:
        raise RuntimeError(f"Tool preflight captured {len(requests)} model requests, expected 1; "
                           f"CLI exit {probe.returncode}: {probe.stderr[-1000:]}")
    observed = requests[0]
    count = len(observed["tools"]) + len(observed["additional_tools"])
    if count:
        raise RuntimeError(f"Tool preflight found {count} available tools")
    return {"available_tools": count, "request_count": len(requests)}


def _load_rollout(thread_id: str) -> list[dict[str, Any]]:
    matches = list((CODEX_HOME / "sessions").rglob(f"*{thread_id}.jsonl"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one saved rollout for {thread_id}; found {len(matches)}")
    return [json.loads(line) for line in matches[0].read_text(encoding="utf-8").splitlines()]


def _request_records(rollout: list[dict[str, Any]]) -> list[dict[str, Any]]:
    records = []
    for event in rollout:
        if event.get("type") != "token_usage_record":
            continue
        payload = event["payload"]
        usage = payload.get("usage") or {}
        cached = usage.get("cached_input_tokens")
        inputs = usage.get("input_tokens")
        records.append({
            "request_index": len(records) + 1,
            "response_id": payload.get("response_id"),
            "timestamp": event.get("timestamp"),
            "model": MODEL,
            "reasoning": REASONING,
            "input_tokens": inputs,
            "cached_input_tokens": cached,
            "uncached_input_tokens": inputs - cached if inputs is not None and cached is not None else None,
            "output_tokens": usage.get("output_tokens"),
            "elapsed_ms": None,
            "tool_available": None,
            "tool_calls": [],
        })
    return records


def reconcile(records: list[dict[str, Any]], aggregate: dict[str, Any]) -> bool:
    return bool(records) and all(
        all(isinstance(record.get(key), int) for record in records)
        and sum(record[key] for record in records) == aggregate.get(key)
        for key in USAGE_KEYS
    )


def run(kind: str, output_name: str) -> dict[str, Any]:
    run_dir = RUN_ROOT / output_name
    run_dir.mkdir(parents=True, exist_ok=False)
    cwd = run_dir / "empty-workspace"
    cwd.mkdir()
    fixture, _, _ = benchmark.verify_freeze()
    _, history = benchmark.conversation(fixture)
    prompt = "Reply with exactly: telemetry smoke." if kind == "smoke" else benchmark.generation_prompt(
        fixture, "control", history
    )
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    receiver = OtlpReceiver()
    thread = threading.Thread(target=receiver.serve_forever, daemon=True)
    thread.start()
    port = receiver.server_address[1]
    command = [shutil.which("codex") or "codex", "exec", "--ignore-user-config",
               "--ignore-rules", "--skip-git-repo-check", "--json", "--model", MODEL,
               "-c", f"model_reasoning_effort={REASONING}",
               "-c", 'approval_policy="never"', "-s", "read-only",
               "-c", "include_apply_patch_tool=false",
               "-c", 'web_search="disabled"',
               "-c", "tools.disable_defaults=true",
               "-c", "agents.max_depth=0",
               "-c", "otel.log_user_prompt=false",
               "-c", "otel.metrics_exporter=\"none\"",
               "-c", f'otel.exporter={{"otlp-http"={{endpoint="http://127.0.0.1:{port}/v1/logs",protocol="json"}}}}',
               "-c", f'otel.trace_exporter={{"otlp-http"={{endpoint="http://127.0.0.1:{port}/v1/traces",protocol="json"}}}}',
               "-"]
    for feature in DISABLED_FEATURES:
        command[2:2] = ["--disable", feature]
    env = {**os.environ, "CODEX_HOME": str(CODEX_HOME), "PYTHONPATH": os.pathsep.join(
        str(ROOT / path) for path in ("apps/api", "apps/mcp", "packages")
    )}
    preflight = _preflight_tools(command, cwd, env, prompt)
    started_at = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    try:
        process = subprocess.run(command, input=prompt, cwd=cwd, env=env, capture_output=True,
                                 text=True, encoding="utf-8", errors="replace", timeout=300)
    finally:
        receiver.shutdown()
        thread.join(timeout=5)
        receiver.server_close()
    (run_dir / "otel-raw.json").write_text(
        json.dumps(receiver.received, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    events = benchmark._extract_events(process.stdout)
    (run_dir / "agent-events.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events), encoding="utf-8"
    )
    (run_dir / "answer.md").write_text(
        benchmark._final_text(events, "agent_message"), encoding="utf-8"
    )
    (run_dir / "agent-stderr.txt").write_text(process.stderr, encoding="utf-8")
    thread_ids = [event.get("thread_id") for event in events if event.get("type") == "thread.started"]
    rollout = _load_rollout(thread_ids[0]) if len(thread_ids) == 1 else []
    raw_usage = [event for event in rollout if event.get("type") == "token_usage_record"]
    (run_dir / "request-usage-raw.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in raw_usage), encoding="utf-8"
    )
    records = _request_records(rollout)
    for record in records:
        record["tool_available"] = False
        record["local_visible_prompt_tokens"] = token_count(prompt)
    durations = _api_durations(receiver.received)
    if len(durations) == len(records):
        for record, duration in zip(records, durations):
            record["elapsed_ms"] = duration
    tool_calls = [event["item"] for event in events if event.get("type") == "item.completed"
                  and event.get("item", {}).get("type", "").endswith("tool_call")]
    aggregate = benchmark._usage(events)
    valid = (process.returncode == 0 and not tool_calls and reconcile(records, aggregate)
             and len(durations) == len(records))
    result = {
        "status": "VALID" if valid else "INVALID",
        "kind": kind,
        "timestamp_utc": started_at,
        "commit_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "fixture_sha256": benchmark.sha256(benchmark.FIXTURE),
        "host": {"cli": subprocess.check_output(["codex", "--version"], text=True).strip(),
                 "config": "ignore-user-config, ignore-rules, empty workspace, feature disables"},
        "model": MODEL, "reasoning": REASONING,
        "prompt_tokens_local": token_count(prompt),
        "history_tokens_local": token_count(history),
        "configured_tool_count": preflight["available_tools"],
        "configured_tool_count_evidence": "Captured Responses request body against local fake provider",
        "observed_tool_calls": tool_calls,
        "request_count": len(records),
        "requests": records,
        "aggregate_usage": aggregate,
        "aggregate_uncached_input_tokens": (
            aggregate["input_tokens"] - aggregate["cached_input_tokens"]
            if aggregate["input_tokens"] is not None
            and aggregate["cached_input_tokens"] is not None else None
        ),
        "input_amplification_ratio_to_local_history": (
            round(aggregate["input_tokens"] / token_count(history), 4)
            if aggregate["input_tokens"] is not None and token_count(history) else None
        ),
        "telemetry_reconciles": reconcile(records, aggregate),
        "api_duration_count": len(durations),
        "exit_code": process.returncode,
        "elapsed_ms": elapsed_ms,
        "run_dir": str(run_dir),
    }
    (run_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if kind == "control-a" and valid:
        output = RESULTS / f"provider-input-overhead-{output_name}.json"
        with output.open("x", encoding="utf-8") as file:
            file.write(json.dumps(result, indent=2) + "\n")
        result["result_file"] = str(output)
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("smoke", "control-a"))
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    result = run(args.kind, args.name)
    print(json.dumps({key: result[key] for key in (
        "status", "request_count", "aggregate_usage", "telemetry_reconciles",
        "api_duration_count", "exit_code", "run_dir"
    )}))
    if result["status"] != "VALID":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

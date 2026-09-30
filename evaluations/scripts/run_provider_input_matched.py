"""Matched-host V0.9 provider-input controls with optional inert MCP registration."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from typing import Any

from conceptualize_evaluation import v09_capability_benchmark as benchmark
from conceptualize_runtime.runtime import token_count

from evaluations.scripts.run_provider_input_control_a import (
    CODEX_HOME,
    MODEL,
    REASONING,
    RESULTS,
    ROOT,
    RUN_ROOT,
    OtlpReceiver,
    _api_durations,
    _load_rollout,
    _request_records,
    reconcile,
)
from evaluations.scripts.run_provider_input_control_b import ACTIVATION, inspect_server

SERVER = ROOT / "evaluations/scripts/minimal_inert_mcp_server.py"
PAIR_ROOT = RUN_ROOT / "matched-host-v1"
SHARED_CWD = PAIR_ROOT / "empty-workspace"
BASE_FLAGS = [
    "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check", "--json",
    "--model", MODEL, "-c", f"model_reasoning_effort={REASONING}",
    "-c", 'approval_policy="never"', "-s", "read-only",
    "-c", 'web_search="disabled"',
    "-c", "agents.max_depth=0",
    "--disable", "apps", "--disable", "plugins", "--disable", "browser_use",
    "--disable", "computer_use", "--disable", "image_generation",
    "--disable", "multi_agent", "--disable", "skill_search",
    "--disable", "tool_suggest", "--disable", "shell_tool",
    "--disable", "view_image", "--disable", "sleep_tool",
    "--disable", "code_mode", "--disable", "code_mode_host",
    "--disable", "workspace_dependencies",
]


def canonical_hash(value: Any) -> str:
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def base_configuration(prompt: str, history: str, env: dict[str, str]) -> dict[str, Any]:
    relevant_env = {key: env.get(key) for key in (
        "CODEX_HOME", "PYTHONPATH", "PATH", "USERPROFILE", "TEMP", "TMP",
        "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY",
    )}
    return {
        "cli_version": subprocess.check_output(["codex", "--version"], text=True).strip(),
        "model": MODEL,
        "reasoning": REASONING,
        "cwd": str(SHARED_CWD.resolve()),
        "base_flags": BASE_FLAGS,
        "environment_sha256": canonical_hash(relevant_env),
        "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
        "history_sha256": hashlib.sha256(history.encode("utf-8")).hexdigest(),
        "fixture_sha256": benchmark.sha256(benchmark.FIXTURE),
        "permissions": {"approval_policy": "never", "sandbox": "read-only"},
    }


def mcp_config(kind: str) -> dict[str, Any]:
    if kind == "a2":
        return {"server_count": 0, "servers": []}
    return {"server_count": 1, "servers": [{
        "name": "inert", "command": sys.executable, "args": [str(SERVER)],
        "enabled": True, "required": True,
    }]}


def command_for(kind: str, otlp_port: int) -> list[str]:
    command = [shutil.which("codex") or "codex", "exec", *BASE_FLAGS,
               "-c", "otel.log_user_prompt=false",
               "-c", 'otel.metrics_exporter="none"',
               "-c", f'otel.exporter={{"otlp-http"={{endpoint="http://127.0.0.1:{otlp_port}/v1/logs",protocol="json"}}}}',
               "-c", f'otel.trace_exporter={{"otlp-http"={{endpoint="http://127.0.0.1:{otlp_port}/v1/traces",protocol="json"}}}}']
    if kind != "a2":
        command += [
            "-c", "mcp_servers.inert.command=" + json.dumps(sys.executable),
            "-c", "mcp_servers.inert.args=" + json.dumps([str(SERVER)]),
            "-c", "mcp_servers.inert.enabled=true",
            "-c", "mcp_servers.inert.required=true",
        ]
    return [*command, "-"]


def _emitted_calls(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls = []
    for index, event in enumerate(events):
        if event.get("type") != "item.completed":
            continue
        item = event.get("item") or {}
        item_type = item.get("type")
        if item_type in ("agent_message", "error", "reasoning"):
            continue
        result = item.get("result") or {}
        content = (result.get("content") or []) if isinstance(result, dict) else []
        response_text = "\n".join(part.get("text", "") for part in content
                                  if isinstance(part, dict) and part.get("type") == "text")
        calls.append({
            "event_index": index,
            "type": item_type,
            "server": item.get("server"),
            "tool": item.get("tool") or item.get("name"),
            "classification": "mcp" if item_type == "mcp_tool_call" else "built_in_or_hosted",
            "arguments": item.get("arguments"),
            "status": item.get("status"),
            "error": item.get("error"),
            "result": result,
            "response_text": response_text,
            "response_tokens_local": token_count(response_text),
        })
    return calls


def _host_internal_mcp_events(otel: list[dict[str, Any]]) -> dict[str, int]:
    names: dict[str, int] = {}
    for batch in otel:
        for resource in batch["payload"].get("resourceSpans", []):
            for scope in resource.get("scopeSpans", []):
                for span in scope.get("spans", []):
                    name = span.get("name", "")
                    if "mcp" in name.lower() or "tool" in name.lower():
                        names[name] = names.get(name, 0) + 1
    return names


def _usage_delta(after: dict[str, Any], before: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "input_tokens": (after["aggregate_usage"].get("input_tokens"),
                         before["aggregate_usage"].get("input_tokens")),
        "cached_input_tokens": (after["aggregate_usage"].get("cached_input_tokens"),
                                before["aggregate_usage"].get("cached_input_tokens")),
        "uncached_input_tokens": (after["aggregate_uncached_input_tokens"],
                                  before["aggregate_uncached_input_tokens"]),
        "output_tokens": (after["aggregate_usage"].get("output_tokens"),
                          before["aggregate_usage"].get("output_tokens")),
        "request_count": (after["request_count"], before["request_count"]),
        "total_elapsed_ms": (after["elapsed_ms"], before["elapsed_ms"]),
    }
    return {key: round(a - b, 2) if a is not None and b is not None else None
            for key, (a, b) in fields.items()}


def run_one(kind: str, pair_index: int, prompt: str, history: str,
            env: dict[str, str], base: dict[str, Any], surface: dict[str, Any]) -> dict[str, Any]:
    run_dir = PAIR_ROOT / f"pair-{pair_index}" / kind
    run_dir.mkdir(parents=True, exist_ok=False)
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    receiver = OtlpReceiver()
    thread = threading.Thread(target=receiver.serve_forever, daemon=True)
    thread.start()
    command = command_for(kind, receiver.server_address[1])
    started_at = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    try:
        process = subprocess.run(command, input=prompt, cwd=SHARED_CWD, env=env,
                                 capture_output=True, text=True, encoding="utf-8",
                                 errors="replace", timeout=300)
    finally:
        receiver.shutdown()
        thread.join(timeout=5)
        receiver.server_close()
    elapsed_ms = round((time.perf_counter() - start) * 1000, 2)
    (run_dir / "otel-raw.json").write_text(
        json.dumps(receiver.received, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    events = benchmark._extract_events(process.stdout)
    (run_dir / "agent-events.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events), encoding="utf-8")
    (run_dir / "agent-stderr.txt").write_text(process.stderr, encoding="utf-8")
    (run_dir / "answer.md").write_text(benchmark._final_text(events, "agent_message"), encoding="utf-8")
    thread_ids = [event.get("thread_id") for event in events if event.get("type") == "thread.started"]
    rollout = _load_rollout(thread_ids[0]) if len(thread_ids) == 1 else []
    raw_usage = [event for event in rollout if event.get("type") == "token_usage_record"]
    (run_dir / "request-usage-raw.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in raw_usage), encoding="utf-8")
    records = _request_records(rollout)
    durations = _api_durations(receiver.received)
    if len(durations) == len(records):
        for record, duration in zip(records, durations):
            record["elapsed_ms"] = duration
    calls = _emitted_calls(events)
    for record in records:
        record["tool_available"] = None  # Complete model-visible catalog is opaque.
        record["local_visible_prompt_tokens"] = token_count(prompt)
    if records and calls:
        records[0]["tool_calls"] = [{"type": call["type"], "tool": call["tool"],
                                    "server": call["server"]} for call in calls]
    usage = benchmark._usage(events)
    uncached = (usage["input_tokens"] - usage["cached_input_tokens"]
                if usage["input_tokens"] is not None and usage["cached_input_tokens"] is not None
                else None)
    mcp_calls = [call for call in calls if call["classification"] == "mcp"]
    expected_mcp = (kind != "a2")
    valid = (process.returncode == 0 and reconcile(records, usage)
             and len(durations) == len(records))
    if kind == "a2":
        valid = valid and not mcp_calls
    if kind == "b1":
        valid = valid and not mcp_calls
    if kind == "b2":
        valid = (valid and len(mcp_calls) == 1 and mcp_calls[0]["server"] == "inert"
                 and mcp_calls[0]["tool"] == "noop"
                 and mcp_calls[0]["status"] == "completed"
                 and mcp_calls[0]["response_text"] == "ok" and mcp_calls[0]["error"] is None)
    result = {
        "status": "VALID" if valid else "INVALID",
        "kind": kind,
        "pair_index": pair_index,
        "timestamp_utc": started_at,
        "commit_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "codex_cli_version": base["cli_version"],
        "fixture_sha256": base["fixture_sha256"],
        "base_configuration": base,
        "base_configuration_sha256": canonical_hash(base),
        "mcp_configuration": mcp_config(kind),
        "mcp_surface": surface if expected_mcp else None,
        "methodology_limitation": "Complete unused built-in tool inventory is opaque; host flags are matched.",
        "model": MODEL,
        "reasoning": REASONING,
        "prompt_tokens_local": token_count(prompt),
        "history_tokens_local": token_count(history),
        "user_task_tokens_local": token_count(benchmark.verify_freeze()[0]["question"]),
        "mcp_instructions_tokens_local": surface["server_instruction_tokens_local"] if expected_mcp else 0,
        "mcp_schema_tokens_local": surface["tool_schema_tokens_local"] if expected_mcp else 0,
        "request_count": len(records),
        "requests": records,
        "aggregate_usage": usage,
        "aggregate_uncached_input_tokens": uncached,
        "telemetry_reconciles": reconcile(records, usage),
        "sampling_span_count": len(durations),
        "tool_calls": calls,
        "model_emitted_mcp_tool_call_count": len(mcp_calls),
        "host_internal_mcp_or_tool_spans": _host_internal_mcp_events(receiver.received),
        "exit_code": process.returncode,
        "elapsed_ms": elapsed_ms,
        "trace_path": str(run_dir),
    }
    (run_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    output = RESULTS / f"provider-input-overhead-matched-{kind}-pair-{pair_index}.json"
    with output.open("x", encoding="utf-8") as file:
        file.write(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pairs", type=int, default=1)
    parser.add_argument("--b2", action="store_true")
    args = parser.parse_args()
    if args.pairs < 1 or args.pairs > 3:
        raise SystemExit("--pairs must be between 1 and 3")
    PAIR_ROOT.mkdir(parents=True, exist_ok=True)
    SHARED_CWD.mkdir(exist_ok=True)
    if any(SHARED_CWD.iterdir()):
        raise RuntimeError("Matched working directory must be empty before all runs")
    fixture, _, _ = benchmark.verify_freeze()
    _, history = benchmark.conversation(fixture)
    prompt = benchmark.generation_prompt(fixture, "control", history)
    env = {**os.environ, "CODEX_HOME": str(CODEX_HOME), "PYTHONPATH": os.pathsep.join(
        str(ROOT / path) for path in ("apps/api", "apps/mcp", "packages")
    )}
    base = base_configuration(prompt, history, env)
    surface = asyncio.run(inspect_server())
    if surface["tool_count"] != 1 or surface["tool_schema"]["name"] != "noop":
        raise RuntimeError("Inert MCP fixture must expose exactly one noop tool")
    if mcp_config("a2")["server_count"] != 0 or mcp_config("b1")["server_count"] != 1:
        raise RuntimeError("Matched MCP registration invariant failed")
    print(json.dumps({"base_configuration_sha256": canonical_hash(base),
                      "a2_mcp_servers": 0, "b1_mcp_servers": 1}), flush=True)
    for pair_index in range(1, args.pairs + 1):
        if any(SHARED_CWD.iterdir()):
            raise RuntimeError("Matched working directory changed before pair")
        a2 = run_one("a2", pair_index, prompt, history, env, base, surface)
        print(json.dumps({"kind": "a2", "pair": pair_index, "status": a2["status"],
                          "requests": a2["request_count"], "usage": a2["aggregate_usage"]}), flush=True)
        if a2["status"] != "VALID":
            raise SystemExit("A2 invalid; stopped before B1")
        b1 = run_one("b1", pair_index, prompt, history, env, base, surface)
        paired = (b1["status"] == "VALID"
                  and b1["base_configuration_sha256"] == a2["base_configuration_sha256"]
                  and [(call["type"], call["tool"], call["server"])
                       for call in a2["tool_calls"] if call["classification"] != "mcp"]
                  == [(call["type"], call["tool"], call["server"])
                      for call in b1["tool_calls"] if call["classification"] != "mcp"])
        print(json.dumps({"kind": "b1", "pair": pair_index, "status": b1["status"],
                          "requests": b1["request_count"], "usage": b1["aggregate_usage"],
                          "matched_observed_built_in_behavior": paired,
                          "delta": _usage_delta(b1, a2)}), flush=True)
        if not paired:
            raise SystemExit("B1 pair invalid or observed built-in calls differ; stopped")
        if args.b2 and pair_index == args.pairs:
            b2 = run_one("b2", pair_index, ACTIVATION + "\n\n" + prompt,
                         history, env, base, surface)
            print(json.dumps({"kind": "b2", "pair": pair_index, "status": b2["status"],
                              "requests": b2["request_count"], "usage": b2["aggregate_usage"],
                              "delta_vs_b1": _usage_delta(b2, b1)}), flush=True)
            if b2["status"] != "VALID":
                raise SystemExit("B2 invalid; trace preserved")


if __name__ == "__main__":
    main()

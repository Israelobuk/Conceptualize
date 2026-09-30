"""Measure one inert MCP capability against the frozen V0.9 host control."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from conceptualize_evaluation import v09_capability_benchmark as benchmark
from conceptualize_runtime.runtime import token_count
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from evaluations.scripts.run_provider_input_control_a import (
    CODEX_HOME,
    DISABLED_FEATURES,
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

SERVER = ROOT / "evaluations/scripts/minimal_inert_mcp_server.py"
CONTROL_A = RESULTS / "provider-input-overhead-control-a-v2-attempt3.json"
ACTIVATION = (
    "Diagnostic instruction: Call the inert noop tool exactly once with the USER TASK "
    "as its task argument before answering. Ignore its response when composing the answer."
)


async def inspect_server() -> dict[str, Any]:
    params = StdioServerParameters(command=sys.executable, args=[str(SERVER)], env=os.environ.copy())
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            init = await session.initialize()
            listed = await session.list_tools()
    schemas = [tool.model_dump(mode="json", exclude_none=True) for tool in listed.tools]
    if len(schemas) != 1 or schemas[0].get("name") != "noop":
        raise RuntimeError(f"Expected only noop, found {[tool.get('name') for tool in schemas]}")
    properties = schemas[0].get("inputSchema", {}).get("properties", {})
    if list(properties) != ["task"] or properties["task"].get("type") != "string":
        raise RuntimeError(f"Unexpected noop schema: {properties}")
    instructions = getattr(init, "instructions", None) or ""
    schema_text = json.dumps(schemas[0], ensure_ascii=False, separators=(",", ":"))
    return {
        "tool_count": 1,
        "server_instructions": instructions,
        "server_instruction_tokens_local": token_count(instructions),
        "tool_schema": schemas[0],
        "tool_schema_tokens_local": token_count(schema_text),
        "tool_schema_bytes": len(schema_text.encode("utf-8")),
    }


def _tool_names(request: dict[str, Any]) -> list[str]:
    return [str(tool.get("name") or tool.get("type")) for tool in
            request["tools"] + request["additional_tools"]]


def preflight_one_tool(command: list[str], cwd: Path, env: dict[str, str],
                       prompt: str) -> dict[str, Any]:
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
    if len(receiver.probed_requests) != 1:
        raise RuntimeError(f"Captured {len(receiver.probed_requests)} preflight requests; "
                           f"CLI exit {probe.returncode}: {probe.stderr[-1000:]}")
    names = _tool_names(receiver.probed_requests[0])
    if len(names) != 1 or not names[0].endswith("noop"):
        raise RuntimeError(f"Expected one inert noop tool; found {names}; "
                           f"request shape {receiver.probed_requests[0]['request_keys']}; "
                           f"noop anywhere={receiver.probed_requests[0]['noop_present_anywhere']}; "
                           f"CLI stderr={probe.stderr[-1200:]}; "
                           f"CLI items={[e.get('item') for e in benchmark._extract_events(probe.stdout) if e.get('item', {}).get('type') == 'error']}")
    return {"available_tool_count": len(names), "available_tool_names": names}


def _call_metrics(calls: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for call in calls:
        response = call.get("result") or {}
        content = response.get("content") or []
        response_text = "\n".join(part.get("text", "") for part in content
                                  if isinstance(part, dict) and part.get("type") == "text")
        arguments = call.get("arguments") or {}
        result.append({
            "server": call.get("server"),
            "tool": call.get("tool"),
            "status": call.get("status"),
            "error": call.get("error"),
            "arguments": arguments,
            "arguments_tokens_local": token_count(json.dumps(arguments, ensure_ascii=False)),
            "response_text": response_text,
            "response_tokens_local": token_count(response_text),
            "response_bytes": len(response_text.encode("utf-8")),
        })
    return result


def _delta(value: float | int | None, baseline: float | int | None) -> dict[str, Any]:
    if value is None or baseline is None:
        return {"absolute": None, "percent": None}
    return {"absolute": round(value - baseline, 2),
            "percent": round((value - baseline) * 100 / baseline, 2) if baseline else None}


def _comparison(result: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    usage = result["aggregate_usage"]
    base_usage = baseline["aggregate_usage"]
    return {
        "input_tokens": _delta(usage["input_tokens"], base_usage["input_tokens"]),
        "cached_input_tokens": _delta(usage["cached_input_tokens"], base_usage["cached_input_tokens"]),
        "uncached_input_tokens": _delta(result["aggregate_uncached_input_tokens"],
                                        baseline["aggregate_uncached_input_tokens"]),
        "request_count": _delta(result["request_count"], baseline["request_count"]),
        "total_elapsed_ms": _delta(result["elapsed_ms"], baseline["elapsed_ms"]),
    }


def run(kind: str, name: str) -> dict[str, Any]:
    run_dir = RUN_ROOT / name
    run_dir.mkdir(parents=True, exist_ok=False)
    cwd = run_dir / "empty-workspace"
    cwd.mkdir()
    surface = asyncio.run(inspect_server())
    fixture, _, _ = benchmark.verify_freeze()
    _, history = benchmark.conversation(fixture)
    base_prompt = benchmark.generation_prompt(fixture, "control", history)
    prompt = base_prompt if kind == "b1" else ACTIVATION + "\n\n" + base_prompt
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
               "-c", 'otel.metrics_exporter="none"',
               "-c", f'otel.exporter={{"otlp-http"={{endpoint="http://127.0.0.1:{port}/v1/logs",protocol="json"}}}}',
               "-c", f'otel.trace_exporter={{"otlp-http"={{endpoint="http://127.0.0.1:{port}/v1/traces",protocol="json"}}}}',
               "-c", "mcp_servers.inert.command=" + json.dumps(sys.executable),
               "-c", "mcp_servers.inert.args=" + json.dumps([str(SERVER)]),
               "-c", "mcp_servers.inert.enabled=true",
               "-c", "mcp_servers.inert.required=true",
               "-"]
    for feature in DISABLED_FEATURES:
        command[2:2] = ["--disable", feature]
    env = {**os.environ, "CODEX_HOME": str(CODEX_HOME), "PYTHONPATH": os.pathsep.join(
        str(ROOT / path) for path in ("apps/api", "apps/mcp", "packages")
    )}
    try:
        preflight = preflight_one_tool(command, cwd, env, prompt)
    except RuntimeError as error:
        receiver.shutdown()
        thread.join(timeout=5)
        receiver.server_close()
        blocked = {
            "status": "BLOCKED_PRE_PROVIDER",
            "kind": kind,
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "commit_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
            "fixture_sha256": benchmark.sha256(benchmark.FIXTURE),
            "model": MODEL,
            "reasoning": REASONING,
            "prompt_tokens_local": token_count(prompt),
            "history_tokens_local": token_count(history),
            "mcp_surface": surface,
            "model_request_count": 0,
            "reason": str(error),
            "trace_path": str(run_dir),
        }
        (run_dir / "preflight-result.json").write_text(
            json.dumps(blocked, indent=2) + "\n", encoding="utf-8"
        )
        output = RESULTS / f"provider-input-overhead-control-{kind}-preflight-blocked.json"
        with output.open("x", encoding="utf-8") as file:
            file.write(json.dumps(blocked, indent=2) + "\n")
        return blocked
    started_at = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    try:
        process = subprocess.run(command, input=prompt, cwd=cwd, env=env, capture_output=True,
                                 text=True, encoding="utf-8", errors="replace", timeout=300)
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
    (run_dir / "answer.md").write_text(benchmark._final_text(events, "agent_message"), encoding="utf-8")
    (run_dir / "agent-stderr.txt").write_text(process.stderr, encoding="utf-8")
    thread_ids = [event.get("thread_id") for event in events if event.get("type") == "thread.started"]
    rollout = _load_rollout(thread_ids[0]) if len(thread_ids) == 1 else []
    raw_usage = [event for event in rollout if event.get("type") == "token_usage_record"]
    (run_dir / "request-usage-raw.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in raw_usage), encoding="utf-8")
    records = _request_records(rollout)
    for record in records:
        record["tool_available"] = True
        record["local_visible_prompt_tokens"] = token_count(prompt)
    durations = _api_durations(receiver.received)
    if len(durations) == len(records):
        for record, duration in zip(records, durations):
            record["elapsed_ms"] = duration
    calls = [event["item"] for event in events if event.get("type") == "item.completed"
             and event.get("item", {}).get("type") == "mcp_tool_call"]
    call_metrics = _call_metrics(calls)
    if records and call_metrics:
        records[0]["tool_calls"] = [item["tool"] for item in call_metrics]
        records[0]["tool_response_tokens_local"] = call_metrics[0]["response_tokens_local"]
    aggregate = benchmark._usage(events)
    uncached = (aggregate["input_tokens"] - aggregate["cached_input_tokens"]
                if aggregate["input_tokens"] is not None
                and aggregate["cached_input_tokens"] is not None else None)
    common_valid = (process.returncode == 0 and reconcile(records, aggregate)
                    and len(durations) == len(records))
    valid_b1 = kind == "b1" and not calls
    valid_b2 = (kind == "b2" and len(calls) == 1 and len(records) >= 2
                and call_metrics[0]["server"] == "inert"
                and call_metrics[0]["tool"] == "noop"
                and call_metrics[0]["status"] == "completed"
                and call_metrics[0]["response_text"] == "ok"
                and call_metrics[0]["error"] is None)
    valid = common_valid and (valid_b1 or valid_b2)
    result = {
        "status": "VALID" if valid else "INVALID",
        "kind": kind,
        "timestamp_utc": started_at,
        "commit_sha": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "fixture_sha256": benchmark.sha256(benchmark.FIXTURE),
        "host": {"cli": subprocess.check_output(["codex", "--version"], text=True).strip(),
                 "config": "Control A host flags plus one inert MCP server"},
        "model": MODEL, "reasoning": REASONING,
        "base_prompt_identical_to_control_a": base_prompt == (RUN_ROOT / "control-a-v2-attempt3" / "prompt.txt").read_text(encoding="utf-8"),
        "activation_tokens_local": 0 if kind == "b1" else token_count(ACTIVATION),
        "prompt_tokens_local": token_count(prompt),
        "history_tokens_local": token_count(history),
        "mcp_surface": surface,
        "preflight": preflight,
        "tool_calls": call_metrics,
        "tool_call_count": len(calls),
        "request_count": len(records),
        "requests": records,
        "aggregate_usage": aggregate,
        "aggregate_uncached_input_tokens": uncached,
        "telemetry_reconciles": reconcile(records, aggregate),
        "sampling_span_count": len(durations),
        "exit_code": process.returncode,
        "elapsed_ms": elapsed_ms,
        "trace_path": str(run_dir),
    }
    baseline = json.loads(CONTROL_A.read_text(encoding="utf-8"))
    result["delta_vs_control_a"] = _comparison(result, baseline)
    if kind == "b2":
        b1_path = RESULTS / "provider-input-overhead-control-b1-inert-connected.json"
        if b1_path.exists():
            result["delta_vs_b1"] = _comparison(result, json.loads(b1_path.read_text(encoding="utf-8")))
    (run_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    output = RESULTS / f"provider-input-overhead-control-{kind}-inert-{'connected' if kind == 'b1' else 'called'}.json"
    with output.open("x", encoding="utf-8") as file:
        file.write(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("kind", choices=("b1", "b2"))
    parser.add_argument("--name", required=True)
    args = parser.parse_args()
    result = run(args.kind, args.name)
    if result["status"] == "BLOCKED_PRE_PROVIDER":
        print(json.dumps({key: result[key] for key in (
            "status", "kind", "model_request_count", "trace_path"
        )}))
        raise SystemExit(2)
    print(json.dumps({key: result[key] for key in (
        "status", "request_count", "aggregate_usage", "telemetry_reconciles",
        "sampling_span_count", "tool_call_count", "exit_code", "trace_path"
    )}))
    if result["status"] != "VALID":
        raise SystemExit(1)


if __name__ == "__main__":
    main()

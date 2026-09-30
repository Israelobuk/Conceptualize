"""Request-level matched-host trace of the frozen V0.9 Conceptualize workflow."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import statistics
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
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
from evaluations.scripts.run_provider_input_matched import canonical_hash

SERVER_MODULE = "conceptualize_evaluation.v09_mcp_fixture_server"
RUN_ROOT_REAL = RUN_ROOT / "real-workflow-proven-v3"
CWD = RUN_ROOT_REAL / "empty-workspace"
KINDS = ("f-minus-1", "f0", "f1")
BASE_FLAGS = [
    "--ignore-user-config", "--skip-git-repo-check", "--json",
    "--model", MODEL, "-c", f"model_reasoning_effort={REASONING}",
    "-c", 'approval_policy="on-request"', "-s", "read-only",
]


def prompts(fixture: dict[str, Any], history: str, mode: str) -> dict[str, str]:
    if mode == "proven":
        base = "\n\n".join((benchmark.SYSTEM_INSTRUCTIONS, fixture["question"]))
        active = benchmark.generation_prompt(fixture, "conceptualize", history)
    elif mode == "full_history":
        base = benchmark.generation_prompt(fixture, "control", history)
        active = base.replace("USER TASK:\n", "USER TASK:\n@Conceptualize\n", 1)
    else:
        raise ValueError(mode)
    if active.count("@Conceptualize") != 1 or "@Conceptualize" in base:
        raise RuntimeError("Activation prompt invariant failed")
    return {"f-minus-1": base, "f0": base, "f1": active}


def command(kind: str, port: int, trace_path: Path) -> list[str]:
    result = [shutil.which("codex") or "codex", "exec", *BASE_FLAGS,
              "-c", "otel.log_user_prompt=false", "-c", 'otel.metrics_exporter="none"',
              "-c", f'otel.exporter={{"otlp-http"={{endpoint="http://127.0.0.1:{port}/v1/logs",protocol="json"}}}}',
              "-c", f'otel.trace_exporter={{"otlp-http"={{endpoint="http://127.0.0.1:{port}/v1/traces",protocol="json"}}}}']
    if kind != "f-minus-1":
        args = ["-m", SERVER_MODULE, "--trace", str(trace_path)]
        result += ["-c", "mcp_servers.conceptualize.command=" + json.dumps(sys.executable),
                   "-c", "mcp_servers.conceptualize.args=" + json.dumps(args),
                   "-c", "mcp_servers.conceptualize.enabled=true",
                   "-c", "mcp_servers.conceptualize.required=true"]
    return [*result, "-"]


def request_timeline(rollout: list[dict[str, Any]], records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Attach model actions and preceding tool output to each usage boundary."""
    usage_positions = [i for i, event in enumerate(rollout) if event.get("type") == "token_usage_record"]
    if len(usage_positions) != len(records):
        raise RuntimeError("Usage boundary count mismatch")
    timeline = []
    previous = -1
    for index, boundary in enumerate(usage_positions):
        segment = rollout[previous + 1:boundary + 1]
        actions, preceding, assistant_messages = [], [], []
        for event in segment:
            if event.get("type") != "response_item":
                continue
            payload = event.get("payload") or {}
            item_type = payload.get("type")
            if item_type in ("custom_tool_call", "function_call"):
                actions.append({"type": item_type, "name": payload.get("name"),
                                "input": payload.get("input") or payload.get("arguments"),
                                "call_id": payload.get("call_id"), "ordinal": event.get("ordinal")})
            elif item_type in ("custom_tool_call_output", "function_call_output"):
                output = payload.get("output")
                preceding.append({"type": item_type, "call_id": payload.get("call_id"),
                                  "output_tokens_local": token_count(json.dumps(output, ensure_ascii=False)),
                                  "output_preview": str(output)[:160]})
            elif item_type == "message" and payload.get("role") == "assistant":
                assistant_messages.append({"ordinal": event.get("ordinal"),
                                           "content_preview": str(payload.get("content"))[:160]})
        record = dict(records[index])
        record["preceded_by_tool_outputs"] = preceding
        record["model_actions"] = actions
        record["assistant_messages"] = assistant_messages
        record["tool_calls"] = actions
        record["phase"] = ("initial" if index == 0 else
                           "continuation_after_tool" if preceding else "additional_model_request")
        timeline.append(record)
        previous = boundary
    return timeline


def host_activity(otel: list[dict[str, Any]]) -> dict[str, Any]:
    counts: dict[str, int] = {}
    events = []
    for batch in otel:
        for resource in batch["payload"].get("resourceSpans", []):
            for scope in resource.get("scopeSpans", []):
                for span in scope.get("spans", []):
                    name = span.get("name", "")
                    if "mcp" not in name.lower() and "tool" not in name.lower():
                        continue
                    counts[name] = counts.get(name, 0) + 1
                    if any(key in name for key in ("mcp.tools.call", "list_tools", "make_rmcp_client",
                                                    "mcp_manager_init", "resource")):
                        attrs = {item["key"]: next(iter(item["value"].values()))
                                 for item in span.get("attributes", [])}
                        events.append({"name": name, "start_unix_ns": span.get("startTimeUnixNano"),
                                       "end_unix_ns": span.get("endTimeUnixNano"),
                                       "server": attrs.get("mcp.server.name") or attrs.get("server_name"),
                                       "tool": attrs.get("tool.name")})
    return {"span_counts": counts, "selected_events": events}


def mcp_calls(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    calls = []
    for event in events:
        if event.get("type") != "item.completed":
            continue
        item = event.get("item") or {}
        if item.get("type") != "mcp_tool_call":
            continue
        result = item.get("result") or {}
        content = result.get("structuredContent") or {}
        context = content.get("context")
        calls.append({"server": item.get("server"), "tool": item.get("tool"),
                      "arguments": item.get("arguments"), "status": item.get("status"),
                      "error": item.get("error"),
                      "context_tokens_local": token_count(context) if isinstance(context, str) else None,
                      "context_sha256": hashlib.sha256(context.encode("utf-8")).hexdigest()
                      if isinstance(context, str) else None})
    return calls


def run_one(kind: str, repetition: int, order: int, prompt: str, base: dict[str, Any],
            env: dict[str, str]) -> dict[str, Any]:
    run_dir = RUN_ROOT_REAL / f"run-{order:02d}-{kind}-rep-{repetition}"
    run_dir.mkdir(parents=True, exist_ok=False)
    trace_path = run_dir / "conceptualize-trace.json"
    (run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    receiver = OtlpReceiver()
    worker = threading.Thread(target=receiver.serve_forever, daemon=True)
    worker.start()
    start_time = datetime.now(timezone.utc).isoformat()
    start = time.perf_counter()
    try:
        process = subprocess.run(command(kind, receiver.server_address[1], trace_path),
                                 input=prompt, cwd=CWD, env=env, capture_output=True,
                                 text=True, encoding="utf-8", errors="replace", timeout=300)
    finally:
        receiver.shutdown()
        worker.join(timeout=5)
        receiver.server_close()
    elapsed = round((time.perf_counter() - start) * 1000, 2)
    events = benchmark._extract_events(process.stdout)
    thread_ids = [e.get("thread_id") for e in events if e.get("type") == "thread.started"]
    rollout = _load_rollout(thread_ids[0]) if len(thread_ids) == 1 else []
    records = _request_records(rollout)
    durations = _api_durations(receiver.received)
    if len(records) == len(durations):
        for record, duration in zip(records, durations):
            record["elapsed_ms"] = duration
    timeline = request_timeline(rollout, records)
    all_mcp_calls = mcp_calls(events)
    calls = [call for call in all_mcp_calls if call["server"] == "conceptualize"
             and call["tool"] == "conceptualize_context"]
    trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.exists() else None
    usage = benchmark._usage(events)
    answer = benchmark._final_text(events, "agent_message")
    activity = host_activity(receiver.received)
    valid = (process.returncode == 0 and reconcile(records, usage)
             and len(durations) == len(records)
             and (len(calls) == 1 and trace is not None if kind == "f1" else not calls))
    result = {"status": "VALID" if valid else "INVALID", "kind": kind,
              "repetition": repetition, "run_order": order, "timestamp_utc": start_time,
              "commit_sha": base["commit_sha"], "codex_cli_version": base["codex_cli_version"],
              "model": MODEL, "reasoning": REASONING,
              "fixture_sha256": base["fixture_sha256"], "base_configuration": base,
              "base_configuration_sha256": canonical_hash(base),
              "mcp_registered": kind != "f-minus-1", "activation_present": kind == "f1",
              "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
              "prompt_tokens_local": token_count(prompt), "request_count": len(records),
              "requests": timeline, "aggregate_usage": usage,
              "aggregate_uncached_input_tokens": usage["input_tokens"] - usage["cached_input_tokens"]
              if usage["input_tokens"] is not None and usage["cached_input_tokens"] is not None else None,
              "telemetry_reconciles": reconcile(records, usage),
              "sampling_span_count": len(durations), "host_internal_activity": activity,
              "model_emitted_conceptualize_calls": calls,
              "model_emitted_other_mcp_calls": [call for call in all_mcp_calls if call not in calls],
              "answer": answer,
              "context_trace_path": str(trace_path) if trace else None,
              "working_context_tokens_local": token_count(trace["context"]) if trace else None,
              "working_context_sha256": hashlib.sha256(trace["context"].encode("utf-8")).hexdigest()
              if trace else None, "elapsed_ms": elapsed, "exit_code": process.returncode,
              "trace_path": str(run_dir)}
    for name, value in (("agent-events.jsonl", "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events)),
                        ("rollout.jsonl", "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in rollout)),
                        ("otel-raw.json", json.dumps(receiver.received, ensure_ascii=False, indent=2)),
                        ("stderr.txt", process.stderr), ("answer.md", answer),
                        ("result.json", json.dumps(result, ensure_ascii=False, indent=2))):
        (run_dir / name).write_text(value, encoding="utf-8")
    return result


def summarize(runs: list[dict[str, Any]]) -> dict[str, Any]:
    summary = {}
    for kind in KINDS:
        sample = [r for r in runs if r["kind"] == kind]
        def mean(key: str) -> float:
            return round(statistics.mean(r["aggregate_usage"][key] for r in sample), 2)
        summary[kind] = {"runs": len(sample), "valid_runs": sum(r["status"] == "VALID" for r in sample),
                         "request_counts": [r["request_count"] for r in sample],
                         "mean_input": mean("input_tokens"),
                         "mean_cached": mean("cached_input_tokens"),
                         "mean_uncached": round(statistics.mean(r["aggregate_uncached_input_tokens"]
                                                              for r in sample), 2),
                         "mean_output": mean("output_tokens"),
                         "mean_elapsed_ms": round(statistics.mean(r["elapsed_ms"] for r in sample), 2)}
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt-mode", choices=("proven", "full_history"), required=True)
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if args.repetitions < 1:
        raise SystemExit("--repetitions must be positive")
    RUN_ROOT_REAL.mkdir(parents=True, exist_ok=True)
    CWD.mkdir(exist_ok=True)
    if any(CWD.iterdir()):
        raise RuntimeError("Matched working directory is not empty")
    fixture, _, freeze = benchmark.verify_freeze()
    _, history = benchmark.conversation(fixture)
    run_prompts = prompts(fixture, history, args.prompt_mode)
    env = {**os.environ, "CODEX_HOME": str(CODEX_HOME), "PYTHONPATH": os.pathsep.join(
        str(ROOT / path) for path in ("apps/api", "apps/mcp", "packages"))}
    env.pop("V09_MCP_TRACE", None)
    relevant_env = {key: env.get(key) for key in ("CODEX_HOME", "PYTHONPATH", "PATH",
                                                    "USERPROFILE", "TEMP", "TMP", "HTTP_PROXY",
                                                    "HTTPS_PROXY", "NO_PROXY")}
    base = {"commit_sha": subprocess.check_output(["git", "rev-parse", "HEAD"],
             cwd=ROOT, text=True).strip(), "codex_cli_version": subprocess.check_output(
             ["codex", "--version"], text=True).strip(), "model": MODEL, "reasoning": REASONING,
            "cwd": str(CWD.resolve()), "base_flags": BASE_FLAGS, "prompt_mode": args.prompt_mode,
            "history_sha256": hashlib.sha256(history.encode("utf-8")).hexdigest(),
            "task_sha256": hashlib.sha256(fixture["question"].encode("utf-8")).hexdigest(),
            "fixture_sha256": freeze["fixture_sha256"],
            "environment_sha256_excluding_mcp_trace": canonical_hash(relevant_env),
            "permissions": {"approval_policy": "on-request", "sandbox": "read-only"}}
    if base["commit_sha"] != "e437f491d6f884a317ca42c1fb4a402d9a818f13":
        raise RuntimeError("Unexpected commit")
    runs = []
    for repetition in range(1, args.repetitions + 1):
        for kind in KINDS:
            result = run_one(kind, repetition, len(runs) + 1, run_prompts[kind], base, env)
            runs.append(result)
            print(json.dumps({"order": result["run_order"], "kind": kind,
                              "status": result["status"], "requests": result["request_count"],
                              "usage": result["aggregate_usage"],
                              "conceptualize_calls": len(result["model_emitted_conceptualize_calls"])}), flush=True)
    summary = {"base_configuration": base, "base_configuration_sha256": canonical_hash(base),
               "prompt_mode": args.prompt_mode, "run_order": [r["kind"] for r in runs],
               "runs": runs, "summary": summarize(runs)}
    path = RESULTS / "provider-input-overhead-real-workflow-proven-v3.json"
    with path.open("x", encoding="utf-8") as file:
        json.dump(summary, file, ensure_ascii=False, indent=2)
    print(json.dumps({"result_path": str(path), "summary": summary["summary"]}), flush=True)


if __name__ == "__main__":
    main()

"""Single-problem deterministic grading for real Codex conversation-context runs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from conceptualize_runtime.adapters import ConversationAdapter
from conceptualize_runtime.runtime import token_count

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "evaluations" / "v05-conversation-problem.json"
QUESTION = "Based on everything we've decided so far, give me the current implementation plan. Include the final architecture, the constraints we must preserve, what earlier decisions have been superseded, and the next implementation step."


def _write(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _run(args: list[str], *, cwd: Path, env: dict | None = None, timeout: int = 180) -> str:
    result = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=True,
    )
    return result.stdout.strip()


def _history_text(fixture: dict) -> str:
    messages = fixture["history"]
    # Match the structured ingestion representation while keeping the control's full history.
    payload = ConversationAdapter().ingest(
        {
            "conversations": [
                {
                    "id": fixture["history_id"],
                    "title": fixture["title"],
                    "messages": messages,
                }
            ]
        }
    )
    ordered = sorted(
        (unit for unit in payload if unit.source_type == "message"),
        key=lambda unit: unit.metadata["order"],
    )
    return "\n\n".join(
        f"[{unit.metadata['timestamp']} {unit.metadata['role']}] {unit.content}"
        for unit in ordered
    )


def grade(answer: str, fixture: dict) -> dict:
    normalized = re.sub(r"\s+", " ", answer.casefold())

    def check(items: list[dict]) -> dict:
        checked = []
        for item in items:
            present = all(term.casefold() in normalized for term in item["terms"])
            checked.append({"id": item["id"], "passed": present, "terms": item["terms"]})
        return {"passed": sum(row["passed"] for row in checked), "total": len(checked), "checks": checked}

    grading = fixture["grading"]
    architecture = check(grading["required_facts"])
    constraints = check(grading["required_constraints"])
    superseded = check(grading["superseded_decisions"])
    stale = [phrase for phrase in grading["stale_decisions"] if phrase.casefold() in normalized]
    correct_next_step = any(
        all(term in normalized for term in item["terms"])
        for item in grading["required_facts"]
        if item["id"] == "next_attachment_adapter_tests"
    )
    total = architecture["total"] + constraints["total"] + superseded["total"] + 1
    passed = architecture["passed"] + constraints["passed"] + superseded["passed"] + int(correct_next_step)
    return {
        "required_architecture_facts": architecture,
        "required_constraints": constraints,
        "superseded_decisions": superseded,
        "stale_decisions_incorrectly_included": stale,
        "correct_next_step": correct_next_step,
        "coverage_percent": round(passed * 100 / total, 2),
        "passed_checks": passed,
        "total_checks": total,
        "deterministic_pass": passed == total and not stale,
        "grading_version": "v05-single-context-recovery-1",
    }


def _event_usage(events: list[dict]) -> dict:
    for event in reversed(events):
        if event.get("type") == "turn.completed":
            usage = event.get("usage") or {}
            return {
                "input_tokens": usage.get("input_tokens"),
                "cached_input_tokens": usage.get("cached_input_tokens"),
                "output_tokens": usage.get("output_tokens"),
                "aggregate_tokens": usage.get("total_tokens"),
                "reasoning_output_tokens": usage.get("reasoning_output_tokens"),
            }
    return {"input_tokens": None, "cached_input_tokens": None, "output_tokens": None, "aggregate_tokens": None}


def _mcp_payloads(tool_calls: list[dict]) -> list[dict]:
    payloads = []
    for call in tool_calls:
        for content in (call.get("result") or {}).get("content", []):
            text = content.get("text")
            if not text:
                continue
            try:
                payloads.append(json.loads(text))
            except (TypeError, ValueError):
                continue
    return payloads


def _trace_details(api_url: str, api_key: str | None, payloads: list[dict]) -> list[dict]:
    if not api_key:
        return []
    traces = []
    for payload in payloads:
        trace_id = payload.get("trace_id")
        if not trace_id:
            continue
        request = urllib.request.Request(
            api_url.rstrip("/") + "/v1/traces/" + trace_id,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                traces.append(json.loads(response.read()))
        except (urllib.error.URLError, TimeoutError, ValueError):
            continue
    return traces


def _run_codex(
    *, codex: str, model: str, prompt: str, output: Path, enabled: bool,
    api_url: str, mcp_command: str | None, mcp_args: list[str], env: dict, timeout: int,
    cwd: Path, codex_home: Path, mcp_required: bool = False,
) -> dict:
    cli = [codex, "exec", "--ephemeral", "--skip-git-repo-check", "--json", "--model", model]
    cli += ["-c", "model_reasoning_effort=low", "-c", 'approval_policy="never"', "-s", "read-only"]
    if enabled:
        if not mcp_command:
            raise ValueError("--mcp-command is required for the Conceptualize condition")
        cli += [
            "-c", "mcp_servers.conceptualize.enabled=true",
            "-c", "mcp_servers.conceptualize.required=" + ("true" if mcp_required else "false"),
            "-c", "mcp_servers.conceptualize.command=" + json.dumps(mcp_command),
            "-c", "mcp_servers.conceptualize.args=" + json.dumps(mcp_args),
            "-c", 'mcp_servers.conceptualize.env_vars=["CONCEPTUALIZE_API_KEY"]',
            "-c", "mcp_servers.conceptualize.env.CONCEPTUALIZE_API_URL=" + json.dumps(api_url),
        ]
    else:
        cli += [
            "-c", "mcp_servers.conceptualize.command=" + json.dumps(mcp_command or sys.executable),
            "-c", "mcp_servers.conceptualize.args=[]",
            "-c", "mcp_servers.conceptualize.enabled=false",
        ]
    started = time.perf_counter()
    process = subprocess.run(
        cli + ["-"], input=prompt, cwd=cwd, env={**env, "CODEX_HOME": str(codex_home)},
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    events = []
    for line in process.stdout.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    (output / "agent-events.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events), encoding="utf-8"
    )
    (output / "agent-stderr.txt").write_text(process.stderr, encoding="utf-8")
    messages = [
        event.get("item", {}).get("text", "")
        for event in events
        if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "agent_message"
    ]
    tool_calls = [
        event.get("item", {})
        for event in events
        if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "mcp_tool_call"
    ]
    answer = messages[-1] if messages else ""
    (output / "answer.md").write_text(answer, encoding="utf-8")
    _write(output / "tool-calls.json", tool_calls)
    mcp_payloads = _mcp_payloads(tool_calls)
    return {
        "exit_code": process.returncode,
        "elapsed_ms": elapsed_ms,
        "answer": answer,
        "events": events,
        "usage": _event_usage(events),
        "tool_calls": tool_calls,
        "mcp_payloads": mcp_payloads,
        "stderr": process.stderr,
    }


def run_one(fixture: dict, *, model: str, condition: str, repetition: int, output: Path,
            codex: str, api_url: str, api_key: str | None, mcp_command: str | None,
            mcp_args: list[str], timeout: int, pricing: dict | None, diagnostic: bool = False,
            mcp_required: bool = False) -> dict:
    enabled = condition != "control_full_history"
    history_text = _history_text(fixture)
    prompt = "\n\n".join(fixture["prompt_rules"])
    if enabled:
        prompt += "\n\n" + fixture["question"]
    else:
        prompt += "\n\n" + history_text + "\n\n" + fixture["question"]
    if diagnostic:
        # Directly provide the exact ContextUnitRuntime selection; this is a distinct quality diagnostic.
        from conceptualize_runtime.context import ContextUnitRuntime

        units = ConversationAdapter().ingest({"conversations": [{
            "id": fixture["history_id"], "title": fixture["title"], "messages": fixture["history"]
        }]})
        pack = ContextUnitRuntime(units).pack(
            QUESTION, fixture["settings"]["token_budget"], source_types={"message"}
        )
        prompt = "\n\n".join(fixture["prompt_rules"]) + "\n\nSelected project context:\n" + pack["context"] + "\n\n" + fixture["question"]
        condition = "forced_context_diagnostic"
        enabled = False
    output.mkdir(parents=True, exist_ok=False)
    cwd = output / "workspace"
    cwd.mkdir()
    (output / "prompt.txt").write_text(prompt, encoding="utf-8")
    _write(output / "manifest.json", {
        "benchmark": fixture["version"], "model": model, "condition": condition,
        "repetition": repetition, "question": QUESTION,
        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "history_sha256": hashlib.sha256(history_text.encode()).hexdigest(),
        "grading_version": fixture["version"], "cli_version": _run([codex, "--version"], cwd=ROOT),
        "api_url": api_url if enabled else None,
        "workspace_instructions": "fresh temporary CODEX_HOME and empty cwd; no user/project instructions or MCP servers",
    })
    env = dict(os.environ)
    if enabled and api_key:
        env["CONCEPTUALIZE_API_KEY"] = api_key
    codex_home = getattr(run_one, "codex_home", ROOT / "evaluations" / "runs" / "v05-benchmark-codex-home")
    if (codex_home / "auth.json").exists():
        env["CODEX_HOME"] = str(codex_home)
    try:
        result = _run_codex(
            codex=codex, model=model, prompt=prompt, output=output, enabled=enabled,
            api_url=api_url, mcp_command=mcp_command, mcp_args=mcp_args,
            env=env, timeout=timeout, cwd=cwd,
            codex_home=codex_home,
            mcp_required=mcp_required,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError) as exc:
        result = {
            "exit_code": getattr(exc, "returncode", 124), "elapsed_ms": None,
            "answer": "", "events": [], "usage": _event_usage([]), "tool_calls": [],
            "stderr": str(exc),
        }
        (output / "agent-stderr.txt").write_text(str(exc), encoding="utf-8")
    score = grade(result["answer"], fixture)
    telemetry = result["usage"]
    estimated = None
    if pricing and all(telemetry.get(key) is not None for key in ("input_tokens", "cached_input_tokens", "output_tokens")):
        uncached = telemetry["input_tokens"] - telemetry["cached_input_tokens"]
        estimated = (
            uncached * pricing["input_per_million"]
            + telemetry["cached_input_tokens"] * pricing["cached_input_per_million"]
            + telemetry["output_tokens"] * pricing["output_per_million"]
        ) / 1_000_000
    mcp_payloads = result.get("mcp_payloads", [])
    traces = _trace_details(api_url, api_key, mcp_payloads) if enabled else []
    trace_by_id = {trace.get("id"): trace for trace in traces}
    compact_metrics = [payload.get("metrics", {}) for payload in mcp_payloads]
    trace_results = []
    for payload in mcp_payloads:
        trace = trace_by_id.get(payload.get("trace_id"), {})
        persisted = trace.get("result") or {}
        trace_results.append({
            "trace_id": payload.get("trace_id"),
            "operation": payload.get("operation"),
            "metrics": payload.get("metrics", {}),
            "overhead": persisted.get("overhead", {}),
            "timings_ms": persisted.get("timings_ms", {}),
        })
    conceptualize_tokens = sum(row.get("returned_tokens", 0) for row in compact_metrics)
    duplicate_avoided = sum(row.get("previously_supplied_tokens", 0) for row in compact_metrics)
    result_data = {
        "benchmark": fixture["version"], "model": model, "condition": condition,
        "repetition": repetition, "exit_code": result["exit_code"],
        "success": result["exit_code"] == 0, "grade": score,
        "elapsed_ms": result["elapsed_ms"], "model_reported_usage": telemetry,
        "context_available_tokens": token_count(history_text),
        "context_string_tokens_delivered_by_conceptualize": conceptualize_tokens if mcp_payloads else (0 if enabled else None),
        "context_string_tokens_full_history": token_count(history_text) if condition == "control_full_history" else None,
        "context_string_tokens_forced_diagnostic": token_count(pack["context"]) if diagnostic else None,
        "conceptualize_available": condition == "autonomous_conceptualize_available",
        "conceptualize_invoked": bool(result["tool_calls"]),
        "adoption": "invoked" if result["tool_calls"] else ("enabled_but_unused" if condition == "autonomous_conceptualize_available" else "not_applicable"),
        "first_operation": result["tool_calls"][0].get("tool") if result["tool_calls"] else None,
        "operations": [call.get("tool") for call in result["tool_calls"]],
        "tool_calls": result["tool_calls"], "conceptualize_traces": trace_results,
        "duplicate_context_avoided_tokens": duplicate_avoided if mcp_payloads else (0 if enabled else None),
        "session_reuse": any(row.get("previously_supplied_tokens", 0) > 0 for row in compact_metrics) if mcp_payloads else (False if enabled else None),
        "mcp_tool_elapsed_ms": [row.get("overhead", {}).get("total_runtime_ms") for row in trace_results],
        "estimated_model_cost": estimated,
        "pricing_snapshot": pricing.get("version") if pricing and estimated is not None else None,
        "pricing_note": "Estimated model cost; not provider invoice." if estimated is not None else "N/A: no explicit pricing snapshot supplied.",
        "answer_file": "answer.md", "raw_events_file": "agent-events.jsonl",
        "stderr_file": "agent-stderr.txt", "limitations": [
            "Context return tokens are Conceptualize's tokenizer estimate from MCP payload metrics; model-reported input tokens are separately recorded.",
            "Persisted trace timing is unavailable if the trace endpoint cannot be reached; MCP stdio startup and host scheduling are outside runtime overhead.",
        ],
    }
    _write(output / "result.json", result_data)
    return result_data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models", nargs="+", required=True)
    parser.add_argument("--conditions", nargs="+", choices=["control_full_history", "autonomous_conceptualize_available", "forced_context_diagnostic"], default=["control_full_history", "autonomous_conceptualize_available"])
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--codex", default=shutil.which("codex") or "codex")
    parser.add_argument("--api-url", default=os.environ.get("CONCEPTUALIZE_API_URL", "http://127.0.0.1:8000"))
    parser.add_argument("--api-key", default=os.environ.get("CONCEPTUALIZE_API_KEY"))
    parser.add_argument(
        "--mcp-command",
        default=str(ROOT / ".venv" / "Scripts" / "python.exe") if os.name == "nt" else sys.executable,
    )
    parser.add_argument("--mcp-args", default="-m conceptualize_mcp.server",
                        help="MCP server arguments as a single shell-free command string")
    parser.add_argument("--mcp-required", action="store_true",
                        help="Require MCP initialization; default exposes it as an optional tool")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--pricing", type=Path)
    parser.add_argument("--codex-home", type=Path, default=ROOT / "evaluations" / "runs" / "v05-benchmark-codex-home")
    parser.add_argument("--output-root", type=Path, default=ROOT / "evaluations" / "runs" / "v05-single-problem")
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    args = parser.parse_args()
    run_one.codex_home = args.codex_home
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    if fixture["question"] != QUESTION:
        raise SystemExit("The fixture question differs from the frozen benchmark question.")
    pricing = json.loads(args.pricing.read_text(encoding="utf-8")) if args.pricing else None
    results = []
    for model in args.models:
        for condition in args.conditions:
            count = 1 if condition == "forced_context_diagnostic" else args.repetitions
            for repetition in range(1, count + 1):
                slug = re.sub(r"[^a-zA-Z0-9_.-]+", "_", model)
                path = args.output_root / slug / condition / f"rep-{repetition}"
                result = run_one(
                    fixture, model=model, condition=condition, repetition=repetition,
                    output=path, codex=args.codex, api_url=args.api_url,
                    api_key=args.api_key, mcp_command=args.mcp_command,
                    mcp_args=args.mcp_args.split(), timeout=args.timeout, pricing=pricing,
                    diagnostic=condition == "forced_context_diagnostic",
                    mcp_required=args.mcp_required,
                )
                results.append({key: value for key, value in result.items() if key not in {"tool_calls", "limitations"}})
                print(json.dumps({"model": model, "condition": condition, "repetition": repetition, "pass": result["grade"]["deterministic_pass"], "input_tokens": result["model_reported_usage"]["input_tokens"], "adoption": result["adoption"]}), flush=True)
    _write(args.output_root / "runs.json", results)


if __name__ == "__main__":
    main()

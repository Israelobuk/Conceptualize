"""Frozen A/B context-economics benchmark for V0.7."""

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
from pathlib import Path

from conceptualize_runtime.adapters import ConversationAdapter
from conceptualize_runtime.context import ContextUnitRuntime
from conceptualize_runtime.runtime import token_count

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "evaluations" / "v07"
FIXTURE_PATH = EVAL / "fixture.json"
TRUTH_PATH = EVAL / "ground-truth.json"
FREEZE_PATH = EVAL / "freeze.json"
OUT_ROOT = ROOT / "evaluations" / "runs" / "v07-economics"
RESULTS = ROOT / "evaluations" / "results"
MODEL = "gpt-6-sol"
QUESTION = (
    "Based on everything we've decided so far, summarize the current implementation plan. "
    "Include the current architecture, the constraints we must preserve, which earlier "
    "decisions are no longer current, and the next implementation step."
)
COMMON_INSTRUCTIONS = (
    "Return a concise implementation plan under these five headings, in this order: "
    "CURRENT ARCHITECTURE, CURRENT CONSTRAINTS, SUPERSEDED DECISIONS, CURRENT STATE, NEXT STEP. "
    "Use only the supplied project conversation. Distinguish the current implementation "
    "from old proposals and unrelated release discussion. Do not infer missing decisions."
)
HEADING_NAMES = (
    "CURRENT ARCHITECTURE",
    "CURRENT CONSTRAINTS",
    "SUPERSEDED DECISIONS",
    "CURRENT STATE",
    "NEXT STEP",
)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _verify_freeze() -> tuple[dict, dict, dict]:
    fixture_bytes = FIXTURE_PATH.read_bytes()
    truth_bytes = TRUTH_PATH.read_bytes()
    fixture = json.loads(fixture_bytes)
    truth = json.loads(truth_bytes)
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    actual = {
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "ground_truth_sha256": hashlib.sha256(truth_bytes).hexdigest(),
    }
    if any(freeze.get(key) != value for key, value in actual.items()):
        raise ValueError("V0.7 fixture or truth changed after freeze; refusing benchmark run")
    if fixture.get("version") != truth.get("version") or fixture["version"] != freeze["fixture_version"]:
        raise ValueError("V0.7 fixture/truth versions do not match the freeze")
    if fixture["question"] != QUESTION or freeze["question"] != QUESTION:
        raise ValueError("V0.7 question differs from the frozen benchmark question")
    return fixture, truth, freeze


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[\w]+", text.casefold()))


def _sections(answer: str) -> tuple[dict[str, str], bool]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in answer.splitlines():
        heading = re.sub(r"^[\s#>*_`-]+|[\s:*_`-]+$", "", line).strip().upper()
        if heading in HEADING_NAMES:
            current = heading
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line)
    return {name: "\n".join(lines) for name, lines in sections.items()}, all(
        name in sections for name in HEADING_NAMES
    )


def _has_alternative(text: str, alternatives: list[list[str]]) -> bool:
    normalized = _normalize(text)
    return any(all(_normalize(term) in normalized for term in alternative) for alternative in alternatives)


def grade(answer: str, truth: dict) -> dict:
    sections, headings_complete = _sections(answer)
    all_text = answer
    checks: dict[str, list[dict]] = {}
    for category in ("current_architecture", "current_constraints", "superseded_decisions", "current_state"):
        items = []
        # Proposition facts may be placed under any requested heading; grade content, not layout.
        category_text = all_text
        for fact in truth[category]:
            present = _has_alternative(category_text, fact["alternatives"])
            items.append({"id": fact["id"], "critical": fact["critical"], "present": present})
        checks[category] = items
    next_fact = truth["next_step"]
    next_present = _has_alternative(all_text, next_fact["alternatives"])
    total_facts = sum(len(items) for items in checks.values()) + 1
    passed_facts = sum(item["present"] for items in checks.values() for item in items) + int(next_present)
    critical_missing = [
        item["id"]
        for items in checks.values()
        for item in items
        if item["critical"] and not item["present"]
    ]
    if next_fact["critical"] and not next_present:
        critical_missing.append(next_fact["id"])

    stale = []
    for rule in truth["stale_claims"]:
        source = sections.get(rule["scope"].replace("_", " ").upper(), all_text)
        normalized = " ".join(source.split())
        for pattern in rule["reject_if_current_contains"]:
            match = re.search(pattern, normalized, flags=re.I)
            if not match:
                continue
            prefix = normalized[max(0, match.start() - 48):match.start()]
            if re.search(r"\b(?:not|never|no|rather than|instead of|replaced|superseded)\b(?:\s+\w+){0,4}\s*$", prefix):
                continue
            stale.append(rule["id"])
            break

    coverage = round(100 * passed_facts / max(1, total_facts), 2)
    pass_rule = truth["pass_rule"]
    passed = (
        (not pass_rule["all_critical_facts_required"] or not critical_missing)
        and coverage >= pass_rule["minimum_overall_coverage_percent"]
        and (not pass_rule["stale_current_claims_allowed"] or not stale)
        and (not pass_rule["next_step_must_be_correct"] or next_present)
    )
    return {
        "passed": passed,
        "fact_coverage_percent": coverage,
        "facts_present": passed_facts,
        "facts_total": total_facts,
        "critical_facts_missing": critical_missing,
        "stale_claims_in_current_sections": stale,
        "next_step_correct": next_present,
        "required_headings_parsed": headings_complete,
        "checks": checks,
        "next_step": {"id": next_fact["id"], "present": next_present},
    }


def _conversation(fixture: dict) -> tuple[list, str]:
    units = ConversationAdapter().ingest({"conversations": [{
        "id": fixture["history_id"], "title": fixture["title"], "messages": fixture["history"]
    }]})
    ordered = sorted(
        (unit for unit in units if unit.source_type == "message"),
        key=lambda unit: unit.metadata["order"],
    )
    full_history = "\n\n".join(
        f"[{unit.metadata['timestamp']} {unit.metadata['role']}] {unit.content}"
        for unit in ordered
    )
    return units, full_history


def compile_context(fixture: dict, budget: int) -> dict:
    units, _ = _conversation(fixture)
    return ContextUnitRuntime(units).pack(
        QUESTION,
        budget,
        source_types={"message"},
    )


def _usage(events: list[dict]) -> dict:
    for event in reversed(events):
        if event.get("type") == "turn.completed":
            usage = event.get("usage") or {}
            return {key: usage.get(key) for key in (
                "input_tokens", "cached_input_tokens", "output_tokens", "total_tokens"
            )}
    return {"input_tokens": None, "cached_input_tokens": None, "output_tokens": None, "total_tokens": None}


def _run_model(
    prompt: str,
    *,
    codex: str,
    model: str,
    codex_home: Path,
    output: Path,
    timeout: int,
    mcp_mode: str | None = None,
) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    cwd = output / "empty-workspace"
    cwd.mkdir()
    (output / "prompt.txt").write_text(prompt, encoding="utf-8")
    approval_args = (
        ["--approve-for-me", "-c", 'approval_policy="on-request"']
        if mcp_mode == "context"
        else ["-c", 'approval_policy="never"', "-s", "read-only"]
    )
    command = [
        codex, "exec", "--ephemeral", "--skip-git-repo-check", "--json", "--model", model,
        "-c", "model_reasoning_effort=low", *approval_args,
        "-c", "mcp_servers.conceptualize.command=" + json.dumps(sys.executable),
        "-c", "mcp_servers.conceptualize.args=[]",
        "-c", "mcp_servers.conceptualize.enabled=false", "-",
    ]
    if mcp_mode in {"context", "inert"}:
        server_args = ["-m", "conceptualize_evaluation.v07_mcp_fixture_server"]
        server_args.append("--trace" if mcp_mode == "context" else "--inert")
        if mcp_mode == "context":
            server_args.append(str(output / "mcp-trace.json"))
        command[-1:-1] = [
            "-c", "mcp_servers.conceptualize.args=" + json.dumps(server_args),
            "-c", "mcp_servers.conceptualize.enabled=true",
            "-c", "mcp_servers.conceptualize.required=true",
        ]
    env = {**os.environ, "CODEX_HOME": str(codex_home)}
    package_path = str(ROOT / "packages")
    env["PYTHONPATH"] = package_path + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    started = time.perf_counter()
    process = subprocess.run(
        command,
        input=prompt,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
    events = []
    for line in process.stdout.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    (output / "agent-events.jsonl").write_text(
        "".join(json.dumps(event, ensure_ascii=False) + "\n" for event in events),
        encoding="utf-8",
    )
    (output / "agent-stderr.txt").write_text(process.stderr, encoding="utf-8")
    messages = [
        event.get("item", {}).get("text", "")
        for event in events
        if event.get("type") == "item.completed"
        and event.get("item", {}).get("type") == "agent_message"
    ]
    tools = [
        event.get("item", {}).get("type")
        for event in events
        if event.get("type") == "item.completed"
        and event.get("item", {}).get("type") not in {"agent_message", "reasoning"}
    ]
    answer = messages[-1] if messages else ""
    (output / "answer.md").write_text(answer, encoding="utf-8")
    return {
        "exit_code": process.returncode,
        "elapsed_ms": elapsed_ms,
        "usage": _usage(events),
        "answer": answer,
        "tool_events": tools,
        "events": events,
        "stderr": process.stderr,
    }


def _prompt(fixture: dict, context: str | None, history: str | None) -> str:
    sections = [COMMON_INSTRUCTIONS]
    if history is not None:
        sections.append("PROJECT CONVERSATION (oldest first; the final line is the current request):\n" + history)
    else:
        sections.append("SELECTED PROJECT CONTEXT:\n" + (context or "No relevant prior context was selected."))
        sections.append("CURRENT REQUEST:\n" + QUESTION)
    return "\n\n".join(sections)


def _autonomous_prompt() -> str:
    return "\n\n".join((
        COMMON_INSTRUCTIONS,
        "CURRENT REQUEST:\n" + QUESTION,
    ))


def _guided_prompt() -> str:
    return "\n\n".join((
        COMMON_INSTRUCTIONS,
        "Use the read-only conceptualize_context tool once to retrieve relevant prior context. "
        "Set its query argument to the current request verbatim and token_budget to 4000. "
        "Then answer using the returned context.",
        "CURRENT REQUEST:\n" + QUESTION,
    ))


def _mcp_adoption_status(tool_calls: list[dict]) -> str:
    return "invoked" if tool_calls else "enabled_but_unused"


def run_repetitions(
    mode: str,
    repetitions: int,
    *,
    model: str = MODEL,
    budget: int = 4000,
    codex: str | None = None,
    codex_home: Path | None = None,
    output_root: Path = OUT_ROOT,
    timeout: int = 240,
) -> dict:
    fixture, truth, freeze = _verify_freeze()
    output_root = output_root.resolve()
    _, history = _conversation(fixture)
    history_tokens = token_count(history)
    codex = codex or shutil.which("codex") or "codex"
    codex_home = codex_home or ROOT / "evaluations" / "runs" / "v05-benchmark-codex-home"
    if not (codex_home / "auth.json").exists():
        raise FileNotFoundError("Authenticated Codex benchmark home is unavailable")
    precompiled = None
    compile_ms = None
    if mode in {"B", "sweep"}:
        start = time.perf_counter()
        precompiled = compile_context(fixture, budget)
        compile_ms = round((time.perf_counter() - start) * 1000, 3)
    records = []
    for rep in range(1, repetitions + 1):
        context = precompiled["context"] if precompiled is not None else None
        if mode == "C":
            prompt = _autonomous_prompt()
        elif mode == "C-guided":
            prompt = _guided_prompt()
        else:
            prompt = _prompt(fixture, context, history if mode in {"A", "host"} else None)
        destination = output_root / model / f"mode_{mode.lower()}_budget_{budget}" / f"rep-{rep}"
        raw = _run_model(
            prompt,
            codex=codex,
            model=model,
            codex_home=codex_home,
            output=destination,
            timeout=timeout,
            mcp_mode={"C": "context", "C-guided": "context", "host": "inert"}.get(mode),
        )
        mcp_trace_path = destination / "mcp-trace.json"
        mcp_trace = json.loads(mcp_trace_path.read_text(encoding="utf-8")) if mcp_trace_path.exists() else None
        mcp_calls = [
            {
                "type": event.get("item", {}).get("type"),
                "id": event.get("item", {}).get("id"),
                "name": event.get("item", {}).get("name"),
                "tool": event.get("item", {}).get("tool"),
                "server": event.get("item", {}).get("server"),
                "status": event.get("item", {}).get("status"),
                "error": event.get("item", {}).get("error"),
            }
            for event in raw["events"]
            if event.get("type") == "item.completed"
            and "mcp" in event.get("item", {}).get("type", "").casefold()
        ]
        result = {
            "benchmark": fixture["version"],
            "mode": mode,
            "model": model,
            "reasoning_effort": "low",
            "repetition": rep,
            "fixture_sha256": freeze["fixture_sha256"],
            "ground_truth_sha256": freeze["ground_truth_sha256"],
            "history_messages": freeze["messages"],
            "full_history_tokens_cl100k": history_tokens,
            "context_budget": budget if mode in {"B", "sweep", "C", "C-guided"} else None,
            "conceptualize": ({
                "candidate_tokens": precompiled["metrics"].get("candidate_tokens"),
                "selected_context_tokens": token_count(precompiled["context"]),
                "duplicate_tokens_suppressed": precompiled["metrics"].get("duplicate_tokens_suppressed", 0),
                "superseded_units_suppressed": precompiled["metrics"].get("superseded_units_suppressed", 0),
                "unchanged_context_tokens_avoided": precompiled["metrics"].get("unchanged_context_tokens", 0),
                "selected_units": precompiled["metrics"].get("selected_units"),
                "candidate_units": precompiled["metrics"].get("candidate_units"),
                "compile_elapsed_ms": compile_ms,
                "selected_unit_ids": [item["unit_id"] for item in precompiled.get("selection", []) if item.get("status") == "selected"],
                "selection": precompiled.get("selection", []),
                "context": precompiled["context"],
            } if precompiled is not None else ({
                **mcp_trace,
                "tool_calls": len({json.dumps(call, sort_keys=True) for call in mcp_calls}),
            } if mcp_trace is not None else None)),
            "provider_usage": raw["usage"],
            "elapsed_ms": raw["elapsed_ms"],
            "model_exit_code": raw["exit_code"],
            "non_message_tool_events": raw["tool_events"],
            "mcp_tool_events": mcp_calls,
            "conceptualize_adoption": (
                _mcp_adoption_status(mcp_calls) if mode in {"C", "C-guided"} else "not_applicable"
            ),
            "conceptualize_call_count": len(mcp_calls),
            "conceptualize_successful_call_count": sum(
                not call.get("error") and call.get("status") != "failed"
                for call in mcp_calls
            ),
            "context_string_tokens_returned": (
                mcp_trace.get("selected_context_tokens", 0) if mcp_trace else 0
            ),
            "previous_context_tokens_referenced": (
                mcp_trace.get("metrics", {}).get("unchanged_context_tokens", 0)
                if mcp_trace else 0
            ),
            "answer": raw["answer"],
            "grade": grade(raw["answer"], truth),
            "protocol_valid": raw["exit_code"] == 0 and (
                not raw["tool_events"] if mode in {"A", "B", "sweep"}
                else all(not call.get("error") and call.get("status") != "failed" for call in mcp_calls)
                if mode in {"C", "C-guided"}
                else not mcp_calls
            ),
            "raw_directory": str(destination.relative_to(ROOT)),
        }
        (destination / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        records.append(result)
    summary = {
        "benchmark": fixture["version"],
        "mode": mode,
        "model": model,
        "reasoning_effort": "low",
        "repetitions": repetitions,
        "fixture_sha256": freeze["fixture_sha256"],
        "ground_truth_sha256": freeze["ground_truth_sha256"],
        "history_tokens_cl100k": history_tokens,
        "budget": budget if mode in {"B", "sweep", "C", "C-guided"} else None,
        "runs": records,
        "pass_count": sum(record["grade"]["passed"] for record in records),
        "protocol_valid_runs": sum(record["protocol_valid"] for record in records),
        "conceptualize_adoption_count": sum(
            record.get("conceptualize_adoption") == "invoked" for record in records
        ),
        "enabled_but_unused_runs": sum(
            record.get("conceptualize_adoption") == "enabled_but_unused" for record in records
        ),
        "average_conceptualize_calls": round(
            sum(record.get("conceptualize_call_count", 0) for record in records) / len(records), 2
        ) if records else 0,
        "average_context_string_tokens_returned": round(
            sum(record.get("context_string_tokens_returned", 0) for record in records) / len(records), 2
        ) if records else 0,
        "average_input_tokens": _average(records, "input_tokens"),
        "average_cached_input_tokens": _average(records, "cached_input_tokens"),
        "average_output_tokens": _average(records, "output_tokens"),
        "average_elapsed_ms": _average(records, "elapsed_ms"),
        "pricing": None,
        "estimated_cost": None,
        "cost_limitation": "No verified versioned pricing snapshot was supplied.",
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    result_name = {
        "C": "v07-mode-c-approved.json",
        "C-guided": f"v07-mode-c-guided-{budget}.json",
    }.get(mode, f"v07-mode-{mode.lower()}-{budget if mode in {'B','sweep'} else 'na'}.json")
    result_path = RESULTS / result_name
    result_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: summary[key] for key in (
        "mode", "repetitions", "pass_count", "protocol_valid_runs", "history_tokens_cl100k",
        "average_input_tokens", "average_cached_input_tokens", "average_output_tokens", "average_elapsed_ms",
    )}, indent=2))
    return summary


def _average(records: list[dict], field: str) -> float | None:
    values = [record["provider_usage"].get(field) if field.endswith("tokens") else record.get(field) for record in records]
    values = [value for value in values if isinstance(value, (int, float))]
    return round(sum(values) / len(values), 2) if values else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", required=True, choices=["A", "B", "sweep", "C", "C-guided", "host"])
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--budget", type=int, default=4000)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--codex", default=shutil.which("codex") or "codex")
    parser.add_argument("--codex-home", type=Path, default=ROOT / "evaluations" / "runs" / "v05-benchmark-codex-home")
    parser.add_argument("--output-root", type=Path, default=OUT_ROOT)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    run_repetitions(
        args.mode,
        args.repetitions,
        model=args.model,
        budget=args.budget,
        codex=args.codex,
        codex_home=args.codex_home,
        output_root=args.output_root,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    main()

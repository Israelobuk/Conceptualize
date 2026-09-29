"""Product-activation evaluation for the V0.8 context capability."""

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
EVAL = ROOT / "evaluations" / "v08"
RESULTS = ROOT / "evaluations" / "results"
FIXTURE_PATH = EVAL / "fixture.json"
TRUTH_PATH = EVAL / "ground-truth.json"
FREEZE_PATH = EVAL / "freeze.json"
MODEL = "gpt-6-sol"
COMMON_INSTRUCTIONS = (
    "Use only the supplied project conversation and current task. Return a concise plan under "
    "these headings: CURRENT STORAGE, DATA RETENTION, SUPERSEDED PROPOSAL, IMPLEMENTATION "
    "STATE, NEXT STEP. State the agreed approach and next action clearly. Do not present "
    "historical proposals as current or infer decisions absent from the conversation."
)


def _json_bytes(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def freeze_fixture() -> dict:
    """Create the initial V0.8 fixture and ground truth once, before model runs."""
    if any(path.exists() for path in (FIXTURE_PATH, TRUTH_PATH, FREEZE_PATH)):
        raise FileExistsError("V0.8 fixture files already exist; refusing to rewrite frozen evidence")
    prior_fixture_path = ROOT / "evaluations" / "v07" / "fixture.json"
    prior_fixture = json.loads(prior_fixture_path.read_text(encoding="utf-8"))
    history = [
        message for message in prior_fixture["history"]
        if message.get("id") != "v07-question"
    ]
    version = "v0.8-offline-attachment-capability-1"
    question = (
        "Continue the attachment-storage work. Summarize the current storage approach, when a "
        "local copy can be removed, which earlier storage proposal is no longer current, and "
        "the next implementation step."
    )
    fixture = {
        "version": version,
        "title": "Offline inspection attachment implementation handoff",
        "history_id": "offline-inspection-attachments-v08",
        "history": history,
        "question": question,
        "output_requirements": [
            "Return concise bullets under CURRENT STORAGE, DATA RETENTION, SUPERSEDED PROPOSAL, "
            "IMPLEMENTATION STATE and NEXT STEP.",
            "Use only this conversation. Distinguish current implementation state from proposals.",
        ],
        "model_runs_started": False,
    }
    truth = {
        "version": version,
        "created_before_model_runs": True,
        "pass_rule": {
            "all_critical_facts_required": True,
            "minimum_overall_coverage_percent": 100,
            "stale_current_claims_allowed": 0,
            "next_step_must_be_correct": True,
        },
        "current_architecture": [
            {
                "id": "filesystem_api_preferred_when_supported",
                "critical": True,
                "alternatives": [
                    ["file system access api", "when supported"],
                    ["file system access api", "when available"],
                    ["filesystem access api", "preferred"],
                ],
            },
            {
                "id": "indexeddb_blob_fallback",
                "critical": True,
                "alternatives": [
                    ["indexeddb", "blob", "fallback"],
                    ["idb", "blob", "fallback"],
                    ["indexeddb blobs", "otherwise"],
                ],
            },
            {
                "id": "shared_attachment_read_write_delete_contract",
                "critical": True,
                "alternatives": [
                    ["adapter contract", "read", "write", "delete"],
                    ["adapter", "read", "write", "delete", "both backends"],
                    ["same read write delete contract"],
                ],
            },
        ],
        "current_constraints": [
            {
                "id": "retain_local_copy_until_authenticated_ack",
                "critical": True,
                "alternatives": [
                    ["local", "authenticated", "upload", "acknowledg"],
                    ["device", "server confirms", "upload"],
                    ["local copy", "authenticated success", "acknowledg"],
                ],
            }
        ],
        "superseded_decisions": [
            {
                "id": "localstorage_proposal_superseded",
                "critical": True,
                "alternatives": [
                    ["localstorage", "superseded"],
                    ["localstorage", "not", "current"],
                    ["localstorage", "not", "production"],
                ],
            }
        ],
        "current_state": [
            {
                "id": "attachment_implementation_unfinished",
                "critical": True,
                "alternatives": [
                    ["attachments", "unfinished"],
                    ["attachment adapter", "not complete"],
                    ["neither production backend", "passed", "common suite"],
                ],
            }
        ],
        "next_step": {
            "id": "finish_adapter_and_tests_then_integrate_sync_engine",
            "critical": True,
            "alternatives": [
                ["backend selection", "indexeddb", "fallback", "persistence", "acknowledgement", "cleanup", "syncengine"],
                ["both backends", "fallback", "reload", "acknowledgement", "syncengine"],
                ["adapter implementations", "fallback", "persistence", "cleanup", "syncengine"],
            ],
        },
        "stale_claims": [
            {
                "id": "localstorage_is_current",
                "scope": "current_storage",
                "reject_if_current_contains": [
                    r"use localstorage as (?:the )?(?:current|production)",
                    r"localstorage (?:is|remains) (?:the )?(?:current|production)",
                ],
            }
        ],
    }
    EVAL.mkdir(parents=True, exist_ok=True)
    FIXTURE_PATH.write_bytes(_json_bytes(fixture))
    TRUTH_PATH.write_bytes(_json_bytes(truth))
    freeze = {
        "fixture_version": version,
        "fixture_sha256": _sha256(FIXTURE_PATH),
        "ground_truth_sha256": _sha256(TRUTH_PATH),
        "source_fixture": {
            "path": "evaluations/v07/fixture.json",
            "version": prior_fixture["version"],
            "sha256": _sha256(prior_fixture_path),
            "relationship": "V0.8 uses a separate task and rubric over this preserved conversation history.",
        },
        "question": question,
        "messages": len(history),
        "history_tokens_cl100k": None,
        "model_runs_started": False,
        "pass_rule": truth["pass_rule"],
        "primary_input_reduction_threshold_percent": 25,
    }
    freeze["history_tokens_cl100k"] = token_count(_conversation(fixture)[1])
    FREEZE_PATH.write_bytes(_json_bytes(freeze))
    return freeze


def verify_freeze() -> tuple[dict, dict, dict]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    truth = json.loads(TRUTH_PATH.read_text(encoding="utf-8"))
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    if fixture["version"] != truth["version"] or fixture["version"] != freeze["fixture_version"]:
        raise ValueError("V0.8 fixture, truth and freeze versions do not match")
    if fixture["question"] != freeze["question"]:
        raise ValueError("V0.8 task differs from the frozen question")
    if _sha256(FIXTURE_PATH) != freeze["fixture_sha256"]:
        raise ValueError("V0.8 fixture changed after freeze")
    if _sha256(TRUTH_PATH) != freeze["ground_truth_sha256"]:
        raise ValueError("V0.8 ground truth changed after freeze")
    return fixture, truth, freeze


def _normalize(text: str) -> str:
    return " ".join(re.findall(r"[\w]+", text.casefold()))


def _sections(answer: str, names: tuple[str, ...]) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for line in answer.splitlines():
        heading = re.sub(r"^[\s#>*_`-]+|[\s:*_`-]+$", "", line).strip().upper()
        if heading in names:
            current = heading
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line)
    return {name: "\n".join(lines) for name, lines in sections.items()}


def _has_alternative(text: str, alternatives: list[list[str]]) -> bool:
    normalized = _normalize(text)
    return any(all(_normalize(term) in normalized for term in option) for option in alternatives)


def grade(answer: str, truth: dict) -> dict:
    names = (
        "CURRENT STORAGE",
        "DATA RETENTION",
        "SUPERSEDED PROPOSAL",
        "IMPLEMENTATION STATE",
        "NEXT STEP",
    )
    sections = _sections(answer, names)
    all_text = _normalize(answer)
    checks = {}
    for category in (
        "current_architecture",
        "current_constraints",
        "superseded_decisions",
        "current_state",
    ):
        checks[category] = [
            {
                "id": fact["id"],
                "critical": fact["critical"],
                "present": _has_alternative(all_text, fact["alternatives"]),
            }
            for fact in truth[category]
        ]
    next_fact = truth["next_step"]
    next_present = _has_alternative(all_text, next_fact["alternatives"])
    facts = [fact for category in checks.values() for fact in category]
    facts.append({"id": next_fact["id"], "critical": next_fact["critical"], "present": next_present})
    coverage = round(100 * sum(item["present"] for item in facts) / max(1, len(facts)), 2)
    critical_missing = [item["id"] for item in facts if item["critical"] and not item["present"]]

    stale = []
    for rule in truth["stale_claims"]:
        scope = sections.get(rule["scope"].replace("_", " ").upper(), all_text)
        normalized = " ".join(scope.split())
        for pattern in rule["reject_if_current_contains"]:
            match = re.search(pattern, normalized, flags=re.I)
            if not match:
                continue
            prefix = normalized[max(0, match.start() - 48):match.start()]
            if re.search(
                r"\b(?:not|never|no|rather than|instead of|replaced|superseded|old)\b"
                r"(?:\s+\w+){0,5}\s*$",
                prefix,
            ):
                continue
            stale.append(rule["id"])
            break

    rule = truth["pass_rule"]
    passed = (
        (not rule["all_critical_facts_required"] or not critical_missing)
        and coverage >= rule["minimum_overall_coverage_percent"]
        and (not rule["stale_current_claims_allowed"] or not stale)
        and (not rule["next_step_must_be_correct"] or next_present)
    )
    return {
        "passed": passed,
        "facts_present": sum(item["present"] for item in facts),
        "facts_total": len(facts),
        "fact_coverage_percent": coverage,
        "critical_facts_missing": critical_missing,
        "stale_claims_in_current_sections": stale,
        "next_step_correct": next_present,
        "checks": checks,
    }


def _conversation(fixture: dict) -> tuple[list, str]:
    units = ConversationAdapter().ingest({"conversations": [{
        "id": fixture["history_id"],
        "title": fixture["title"],
        "messages": fixture["history"],
    }]})
    ordered = sorted(
        (unit for unit in units if unit.source_type == "message"),
        key=lambda unit: unit.metadata["order"],
    )
    history = "\n\n".join(
        f"[{unit.metadata['timestamp']} {unit.metadata['role']}] {unit.content}"
        for unit in ordered
    )
    return units, history


def compile_context(fixture: dict, budget: int = 4000) -> dict:
    units, _ = _conversation(fixture)
    return ContextUnitRuntime(units).pack(
        fixture["question"], budget, source_types={"message"}
    )


def prompt_for(mode: str, fixture: dict, *, context: str | None = None, history: str | None = None) -> str:
    if mode == "A":
        if history is None:
            raise ValueError("Mode A requires full conversation history")
        return "\n\n".join((
            COMMON_INSTRUCTIONS,
            "PROJECT CONVERSATION (oldest first):\n" + history,
            "CURRENT USER TASK:\n" + fixture["question"],
        ))
    if mode == "B":
        return "\n\n".join((COMMON_INSTRUCTIONS, "@Conceptualize\n" + fixture["question"]))
    if mode == "host":
        if history is None:
            raise ValueError("MCP host control requires full conversation history")
        return "\n\n".join((
            COMMON_INSTRUCTIONS,
            "PROJECT CONVERSATION (oldest first):\n" + history,
            "CURRENT USER TASK:\n" + fixture["question"],
        ))
    if mode == "precompiled":
        return "\n\n".join((
            COMMON_INSTRUCTIONS,
            "SELECTED PROJECT CONTEXT:\n" + (context or "No useful context was selected."),
            "CURRENT USER TASK:\n" + fixture["question"],
        ))
    raise ValueError(f"Unknown benchmark mode: {mode}")


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
    mcp_mode: str | None,
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
        "-c", 'mcp_servers.conceptualize.args=[]',
        "-c", "mcp_servers.conceptualize.enabled=false", "-",
    ]
    env = {**os.environ, "CODEX_HOME": str(codex_home)}
    package_path = str(ROOT / "packages")
    env["PYTHONPATH"] = package_path + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    if mcp_mode in {"context", "inert"}:
        args = ["-m", "conceptualize_evaluation.v08_mcp_fixture_server"]
        if mcp_mode == "context":
            trace = output / "mcp-trace.json"
            args.extend(["--trace", str(trace)])
            env["V08_MCP_TRACE_PATH"] = str(trace)
        else:
            args.append("--inert")
        command[-1:-1] = [
            "-c", "mcp_servers.conceptualize.args=" + json.dumps(args),
            "-c", "mcp_servers.conceptualize.enabled=true",
            "-c", "mcp_servers.conceptualize.required=true",
        ]
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
    tool_events = [
        event.get("item", {})
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
        "tool_events": tool_events,
        "events": events,
        "stderr": process.stderr,
    }


def _mean(records: list[dict], key: str) -> float | None:
    values = [record.get("provider_usage", {}).get(key) for record in records]
    values = [value for value in values if isinstance(value, (int, float))]
    return round(sum(values) / len(values), 2) if values else None


def persist_summary(path: Path, summary: dict) -> None:
    """Persist result evidence only at a new path; never replace prior measurements."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"Result file already exists; refusing to overwrite: {path}")
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(summary, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def run(mode: str, repetitions: int, *, model: str = MODEL, budget: int = 4000,
        codex: str | None = None, codex_home: Path | None = None,
        output_root: Path | None = None, timeout: int = 240,
        result_file: Path | None = None) -> dict:
    fixture, truth, freeze = verify_freeze()
    if mode == "B":
        baseline_path = RESULTS / "v08-mode-a.json"
        if not baseline_path.exists():
            raise RuntimeError("Run and validate Mode A before Mode B")
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        if baseline.get("fixture_sha256") != freeze["fixture_sha256"] or baseline.get("pass_count") != 3:
            raise RuntimeError("Mode A did not achieve the frozen 3/3 validity gate; Mode B is blocked")

    output_name = {
        "A": "v08-mode-a.json",
        "B": "v08-mode-b-activated.json",
        "host": "v08-mode-host-inert.json",
        "precompiled": "v08-mode-precompiled-diagnostic.json",
    }[mode]
    summary_path = (result_file or RESULTS / output_name).resolve()
    if summary_path.exists():
        raise FileExistsError(f"Result file already exists; refusing to overwrite: {summary_path}")

    output_root = (output_root or ROOT / "evaluations" / "runs" / "v08").resolve()
    codex = codex or shutil.which("codex") or "codex"
    codex_home = codex_home or ROOT / "evaluations" / "runs" / "v05-benchmark-codex-home"
    if not (codex_home / "auth.json").exists():
        raise FileNotFoundError("Authenticated Codex benchmark home is unavailable")
    units, history = _conversation(fixture)
    history_tokens = token_count(history)
    package = compile_context(fixture, budget) if mode in {"B", "precompiled"} else None
    records = []
    for repetition in range(1, repetitions + 1):
        prompt = prompt_for(
            mode,
            fixture,
            context=package["context"] if package else None,
            history=history if mode in {"A", "host"} else None,
        )
        destination = output_root / model / f"mode-{mode}-budget-{budget}" / f"rep-{repetition}"
        raw = _run_model(
            prompt,
            codex=codex,
            model=model,
            codex_home=codex_home,
            output=destination,
            timeout=timeout,
            mcp_mode={"B": "context", "host": "inert"}.get(mode),
        )
        trace_path = destination / "mcp-trace.json"
        trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.exists() else None
        mcp_events = [
            event for event in raw["tool_events"]
            if "mcp" in str(event.get("type", "")).casefold()
        ]
        result = {
            "benchmark": fixture["version"],
            "mode": mode,
            "model": model,
            "reasoning_effort": "low",
            "repetition": repetition,
            "fixture_sha256": freeze["fixture_sha256"],
            "ground_truth_sha256": freeze["ground_truth_sha256"],
            "history_messages": len(fixture["history"]),
            "history_tokens_cl100k": history_tokens,
            "provider_usage": raw["usage"],
            "elapsed_ms": raw["elapsed_ms"],
            "model_exit_code": raw["exit_code"],
            "task_grade": grade(raw["answer"], truth),
            "tool_calls": len(mcp_events),
            "tool_events": mcp_events,
            "context": ({
                "candidate_units": package["metrics"]["candidate_units"],
                "candidate_tokens": package["metrics"]["candidate_tokens"],
                "selected_units": package["metrics"]["selected_units"],
                "selected_context_tokens": token_count(package["context"]),
                "duplicate_tokens_suppressed": package["metrics"]["duplicate_tokens_suppressed"],
                "superseded_units_suppressed": package["metrics"]["superseded_units_suppressed"],
                "unchanged_tokens_avoided": package["metrics"]["unchanged_context_tokens"],
                "selected_context": package["context"],
                "working_context": package.get("working_context", []),
                "selection": package["selection"],
            } if package else {
                "selected_context_tokens": trace.get("selected_context_tokens", 0) if trace else 0,
                "trace": trace,
            }),
            "protocol_valid": raw["exit_code"] == 0 and (
                all(event.get("status") != "failed" and not event.get("error") for event in mcp_events)
                if mode == "B" else not mcp_events if mode == "A" else True
            ),
            "answer": raw["answer"],
            "raw_directory": str(destination.relative_to(ROOT)),
        }
        (destination / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        records.append(result)
    summary = {
        "benchmark": fixture["version"],
        "mode": mode,
        "model": model,
        "reasoning_effort": "low",
        "repetitions": repetitions,
        "fixture_sha256": freeze["fixture_sha256"],
        "ground_truth_sha256": freeze["ground_truth_sha256"],
        "history_messages": len(fixture["history"]),
        "history_tokens_cl100k": history_tokens,
        "budget": budget if mode in {"B", "precompiled"} else None,
        "runs": records,
        "pass_count": sum(record["task_grade"]["passed"] for record in records),
        "protocol_valid_runs": sum(record["protocol_valid"] for record in records),
        "average_context_tokens": round(sum(
            record.get("context", {}).get("selected_context_tokens", 0) for record in records
        ) / max(1, len(records)), 2),
        "average_provider_input_tokens": _mean(records, "input_tokens"),
        "average_cached_input_tokens": _mean(records, "cached_input_tokens"),
        "average_output_tokens": _mean(records, "output_tokens"),
        "average_elapsed_ms": round(sum(record["elapsed_ms"] for record in records) / max(1, len(records)), 2),
        "average_tool_calls": round(sum(record["tool_calls"] for record in records) / max(1, len(records)), 2),
        "runs_detail": records,
    }
    persist_summary(summary_path, summary)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze-fixture", action="store_true")
    parser.add_argument("--mode", choices=["A", "B", "host", "precompiled"])
    parser.add_argument("--repetitions", type=int, default=1)
    parser.add_argument("--budget", type=int, default=4000)
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--codex", default=shutil.which("codex") or "codex")
    parser.add_argument(
        "--codex-home", type=Path,
        default=ROOT / "evaluations" / "runs" / "v05-benchmark-codex-home",
    )
    parser.add_argument("--output-root", type=Path, default=ROOT / "evaluations" / "runs" / "v08")
    parser.add_argument(
        "--result-file", type=Path,
        help="Write summary to a new path; an existing result file is never overwritten",
    )
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    if args.freeze_fixture:
        print(json.dumps(freeze_fixture(), indent=2))
        return
    if args.mode is None:
        parser.error("--mode is required unless --freeze-fixture is used")
    summary = run(
        args.mode,
        args.repetitions,
        model=args.model,
        budget=args.budget,
        codex=args.codex,
        codex_home=args.codex_home,
        output_root=args.output_root,
        timeout=args.timeout,
        result_file=args.result_file,
    )
    print(json.dumps({key: summary[key] for key in (
        "mode", "repetitions", "pass_count", "protocol_valid_runs", "history_tokens_cl100k",
        "average_context_tokens", "average_provider_input_tokens", "average_cached_input_tokens",
        "average_output_tokens", "average_elapsed_ms", "average_tool_calls",
    )}, indent=2))


if __name__ == "__main__":
    main()

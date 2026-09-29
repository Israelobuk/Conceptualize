"""Independently frozen V0.8 Benchmark v2 and deterministic proposition grader."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

from conceptualize_runtime.adapters import ConversationAdapter
from conceptualize_runtime.context import ContextUnitRuntime
from conceptualize_runtime.runtime import token_count

from conceptualize_evaluation.v08_economics import _run_model

ROOT = Path(__file__).resolve().parents[2]
V1 = ROOT / "evaluations" / "v08"
EVAL = ROOT / "evaluations" / "v08-benchmark-v2"
RESULTS = ROOT / "evaluations" / "results"
FIXTURE_PATH = EVAL / "fixture.json"
TRUTH_PATH = EVAL / "ground-truth.json"
GRADER_PATH = EVAL / "grader.json"
FREEZE_PATH = EVAL / "freeze.json"
MODEL = "gpt-6-sol"
HEADINGS = (
    "CURRENT ARCHITECTURE", "CURRENT DECISIONS", "CONSTRAINTS",
    "SUPERSEDED DECISIONS", "CURRENT STATE", "NEXT STEP",
)
INSTRUCTIONS = (
    "Use only the supplied project conversation and the current task. Return concise bullets "
    "under exactly these headings: CURRENT ARCHITECTURE, CURRENT DECISIONS, CONSTRAINTS, "
    "SUPERSEDED DECISIONS, CURRENT STATE, NEXT STEP. State the current plan and next action. "
    "Do not present superseded proposals as current."
)


def _write_new(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _truth() -> dict:
    # Alternatives are authored from the project facts before any v2 model answers exist.
    return {
        "version": "v0.8-benchmark-2",
        "created_before_model_runs": True,
        "pass_rule": {
            "all_critical_facts_required": True,
            "minimum_coverage_percent": 100,
            "stale_current_claims_allowed": 0,
        },
        "facts": [
            {"id": "ARCH_01", "section": "CURRENT ARCHITECTURE", "critical": True,
             "proposition": "File System Access API is the preferred storage when available.",
             "acceptable": [
                 ["file system access api", "preferred"], ["file system access", "preferred"],
                 ["filesystem", "preferred", "available"], ["filesystem", "first choice"],
                 ["file system access", "primary", "supported"],
             ], "contradictions": ["filesystem is not preferred", "indexeddb is preferred instead"]},
            {"id": "ARCH_02", "section": "CURRENT ARCHITECTURE", "critical": True,
             "proposition": "IndexedDB blob storage is the fallback.",
             "acceptable": [
                 ["indexeddb", "blob", "fallback"], ["indexed db", "blob", "fallback"],
                 ["idb", "blob", "fallback"], ["indexeddb", "otherwise"],
             ], "contradictions": ["indexeddb is not the fallback", "there is no indexeddb fallback"]},
            {"id": "ARCH_03", "section": "CURRENT ARCHITECTURE", "critical": True,
             "proposition": "Both backends implement one shared attachment read/write/delete contract.",
             "acceptable": [
                 ["shared", "adapter", "read", "write", "delete"],
                 ["same", "contract", "read", "write", "delete"],
                 ["common", "interface", "reading", "writing", "deleting"],
                 ["adapter", "read", "write", "delete", "both", "backends"],
                 ["shared", "attachment", "contract", "read", "write", "delete"],
             ], "contradictions": ["backends use different interfaces"]},
            {"id": "DEC_01", "section": "CURRENT DECISIONS", "critical": True,
             "proposition": "New attachments use preferred filesystem storage; IndexedDB blob storage is the fallback.",
             "acceptable": [
                 ["new", "attachments", "filesystem", "indexeddb", "fallback"],
                 ["attachments", "file system access", "indexeddb", "otherwise"],
                 ["primary", "filesystem", "fallback", "indexeddb", "blob"],
             ], "contradictions": ["new attachments use localstorage only"]},
            {"id": "CON_01", "section": "CONSTRAINTS", "critical": True,
             "proposition": "Keep local attachment data until an authenticated upload is acknowledged by the server.",
             "acceptable": [
                 ["local", "authenticated", "upload", "acknowledg"],
                 ["device", "server", "confirms", "authenticated", "upload"],
                 ["local copy", "successful", "authenticated", "upload", "server"],
                 ["do not", "delete", "until", "server", "acknowledges", "upload"],
                 ["local", "authenticated", "upload", "acknowledged"],
             ], "contradictions": ["delete local data before acknowledgement", "local data need not be retained until acknowledgement"]},
            {"id": "OLD_01", "section": "SUPERSEDED DECISIONS", "critical": True,
             "proposition": "The earlier localStorage-only proposal is superseded and is not current.",
             "acceptable": [
                 ["localstorage", "superseded"], ["localstorage", "not", "current"],
                 ["localstorage", "replaced"], ["old", "localstorage", "proposal"],
                 ["local storage", "no longer", "current"],
             ], "contradictions": ["localstorage remains current", "localstorage is the current proposal"]},
            {"id": "STATE_01", "section": "CURRENT STATE", "critical": True,
             "proposition": "The adapter/backend implementation and shared contract tests are not complete.",
             "acceptable": [
                 ["adapter", "not", "complete"], ["implementation", "unfinished"],
                 ["contract tests", "not", "passed"], ["backend", "tests", "incomplete"],
                 ["neither", "backend", "passed", "shared", "tests"],
             ], "contradictions": ["adapter is complete and contract tests pass"]},
            {"id": "NEXT_01", "section": "NEXT STEP", "critical": True,
             "proposition": "Complete and test backend selection, persistence/reload, fallback, acknowledgement-safe cleanup, then integrate with SyncEngine.",
             "acceptable": [
                 ["finish", "adapter", "tests", "fallback", "persistence", "cleanup", "syncengine"],
                 ["complete", "backend", "selection", "reload", "fallback", "acknowledgement", "syncengine"],
                 ["implement", "both", "backends", "contract", "tests", "then", "syncengine"],
                 ["adapter", "contract", "persistence", "fallback", "acknowledged", "cleanup", "before", "syncengine"],
             ], "contradictions": ["integrate syncengine before completing adapter tests"]},
        ],
        "stale_propositions": [
            {"id": "STALE_01", "section": "CURRENT DECISIONS", "patterns": [
                "localstorage is current", "localstorage remains current", "use localstorage in production",
                "local storage is the production backend", "localstorage is the preferred backend",
            ]},
            {"id": "STALE_02", "section": "CONSTRAINTS", "patterns": [
                "delete local files before upload acknowledgement", "remove local data before server acknowledgement",
                "local data can be deleted before the upload is acknowledged",
            ]},
        ],
    }


def create_fixture() -> dict:
    """Create v2 in new paths, retaining v1 and its output byte-for-byte."""
    if any(path.exists() for path in (FIXTURE_PATH, TRUTH_PATH, GRADER_PATH, FREEZE_PATH)):
        raise FileExistsError("V0.8 Benchmark v2 artifacts already exist; refusing to overwrite")
    source = json.loads((V1 / "fixture.json").read_text(encoding="utf-8"))
    history = [m for m in source["history"] if m.get("id") != "v07-question"]
    # A realistic handoff note makes the intended current project state unambiguous while
    # the earlier long conversation still contains repeated, quoted, stale and unrelated work.
    handoff = (
        "Current attachment handoff (authoritative project state): The File System Access API "
        "is the preferred storage backend when supported. IndexedDB blob storage is the fallback. "
        "Both backends must implement the same attachment adapter contract: write, read, and delete. "
        "Keep local attachment data until the server acknowledges an authenticated upload. The "
        "older localStorage-only proposal is superseded. The adapter implementations and shared "
        "contract tests are still incomplete. Next, finish and test backend selection, persistence "
        "across reload, fallback behavior, and acknowledgement-safe cleanup; then integrate the "
        "adapter with SyncEngine."
    )
    history.append({
        "id": "v08-v2-current-handoff",
        "role": "assistant",
        "timestamp": "2026-09-28T16:00:00Z",
        "content": handoff,
        "metadata": {"importance": "high", "kind": "current_state", "explicit": True},
    })
    question = (
        "Continue the attachment-storage work using the current project state. Summarize the "
        "current architecture and decisions, the data-retention constraint, which earlier decision "
        "was superseded, what remains unfinished, and the next implementation step. Return concise "
        "bullets under CURRENT ARCHITECTURE, CURRENT DECISIONS, CONSTRAINTS, SUPERSEDED DECISIONS, "
        "CURRENT STATE, and NEXT STEP."
    )
    fixture = {
        "version": "v0.8-benchmark-2",
        "title": "Offline inspection app attachment storage handoff (benchmark v2)",
        "history_id": "offline-inspection-attachments-v08-v2",
        "history": history,
        "question": question,
        "source_v1_fixture_sha256": hashlib.sha256((V1 / "fixture.json").read_bytes()).hexdigest(),
        "model_runs_started": False,
    }
    truth = _truth()
    grader = {
        "version": "v0.8-benchmark-2",
        "algorithm": "section-scoped predetermined normalized token-set inclusion",
        "normalization": ["casefold", "punctuation-to-space", "whitespace-collapse", "simple-suffix-normalization"],
        "variants_are_predeclared": True,
        "truth_sha256_is_embedded_in_freeze": True,
    }
    _write_new(FIXTURE_PATH, fixture)
    _write_new(TRUTH_PATH, truth)
    _write_new(GRADER_PATH, grader)
    freeze = {
        "fixture_version": fixture["version"],
        "fixture_sha256": _sha(FIXTURE_PATH),
        "ground_truth_sha256": _sha(TRUTH_PATH),
        "grader_sha256": _sha(GRADER_PATH),
        "grader_implementation_sha256": _sha(Path(__file__)),
        "source_v1_fixture_sha256": fixture["source_v1_fixture_sha256"],
        "question": question,
        "messages": len(history),
        "history_tokens_cl100k": token_count(_format_history(fixture)),
        "model_runs_started": False,
        "pass_rule": truth["pass_rule"],
    }
    _write_new(FREEZE_PATH, freeze)
    return freeze


def _format_history(fixture: dict) -> str:
    return "\n\n".join(
        f"[{m.get('timestamp', '')} {m.get('role', 'user')}] {m.get('content', '')}"
        for m in fixture["history"]
    )


def verify_freeze() -> tuple[dict, dict, dict]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    truth = json.loads(TRUTH_PATH.read_text(encoding="utf-8"))
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    checks = (
        (fixture["version"] == truth["version"] == freeze["fixture_version"], "version"),
        (fixture["question"] == freeze["question"], "task"),
        (_sha(FIXTURE_PATH) == freeze["fixture_sha256"], "fixture"),
        (_sha(TRUTH_PATH) == freeze["ground_truth_sha256"], "ground truth"),
        (_sha(GRADER_PATH) == freeze["grader_sha256"], "grader"),
        (_sha(Path(__file__)) == freeze["grader_implementation_sha256"], "grader implementation"),
    )
    for valid, name in checks:
        if not valid:
            raise ValueError(f"V0.8 benchmark v2 frozen {name} changed")
    return fixture, truth, freeze


def _normal(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+", text.casefold())
    normalized = []
    for token in tokens:
        if len(token) > 4 and token.endswith("ies"):
            token = token[:-3] + "y"
        elif len(token) > 3 and token.endswith("s") and not token.endswith(("ss", "us", "is")):
            token = token[:-1]
        normalized.append(token)
    return normalized


def _sections(answer: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    active: str | None = None
    headings = {re.sub(r"[^A-Z0-9 ]", "", name.upper()).strip(): name for name in HEADINGS}
    for line in answer.splitlines():
        heading = re.sub(r"[^A-Z0-9 ]", "", line.strip(" #>*_`:-").upper()).strip()
        if heading in headings:
            active = headings[heading]
            sections.setdefault(active, [])
        elif active:
            sections[active].append(line)
    # Unheaded responses remain gradeable against the full answer for host formatting variance.
    if not sections:
        return {name: answer for name in HEADINGS}
    return {name: " ".join(lines) for name, lines in sections.items()}


def _has_variant(text: str, alternatives: list[list[str]]) -> bool:
    tokens = set(_normal(text))
    for variant in alternatives:
        wanted = set(_normal(" ".join(variant)))
        if wanted and wanted <= tokens:
            return True
    return False


def grade(answer: str, truth: dict | None = None) -> dict:
    truth = truth or json.loads(TRUTH_PATH.read_text(encoding="utf-8"))
    sections = _sections(answer)
    results = []
    for fact in truth["facts"]:
        section = sections.get(fact["section"], "")
        contradiction = any(
            " ".join(_normal(pattern)) in " ".join(_normal(section))
            for pattern in fact.get("contradictions", [])
        )
        results.append({
            "id": fact["id"], "section": fact["section"], "critical": fact["critical"],
            "present": _has_variant(section, fact["acceptable"]) and not contradiction,
            "contradicted": contradiction,
        })
    stale = []
    for item in truth["stale_propositions"]:
        section = sections.get(item["section"], "")
        normalized_tokens = set(_normal(section))
        for pattern in item["patterns"]:
            phrase_tokens = set(_normal(pattern))
            if phrase_tokens and phrase_tokens <= normalized_tokens:
                stale.append(item["id"])
                break
    coverage = round(100 * sum(item["present"] for item in results) / max(1, len(results)), 2)
    missing = [item["id"] for item in results if item["critical"] and not item["present"]]
    rule = truth["pass_rule"]
    return {
        "passed": not missing and coverage >= rule["minimum_coverage_percent"] and not stale,
        "coverage_percent": coverage,
        "facts_present": len(results) - len(missing),
        "facts_total": len(results),
        "critical_missing": missing,
        "stale_current_claims": sorted(set(stale)),
        "propositions": results,
    }


def _prompt(mode: str, fixture: dict) -> str:
    base = INSTRUCTIONS
    if mode == "A":
        return "\n\n".join((base, "PROJECT CONVERSATION (oldest first):\n" + _format_history(fixture),
                              "CURRENT USER TASK:\n" + fixture["question"]))
    if mode == "B":
        return "\n\n".join((base, "@Conceptualize\n" + fixture["question"]))
    raise ValueError(f"Unsupported v2 mode: {mode}")


def run_baseline(repetitions: int = 3, *, codex: str | None = None,
                 codex_home: Path | None = None, timeout: int = 240) -> dict:
    fixture, truth, freeze = verify_freeze()
    result_path = RESULTS / "v08-v2-mode-a.json"
    if result_path.exists():
        raise FileExistsError(f"Refusing to overwrite v2 results: {result_path}")
    raw_root = ROOT / "evaluations" / "runs" / "v08-v2"
    codex = codex or shutil.which("codex") or "codex"
    codex_home = codex_home or ROOT / "evaluations" / "runs" / "v05-benchmark-codex-home"
    if not (codex_home / "auth.json").exists():
        raise FileNotFoundError("Authenticated Codex benchmark home is unavailable")
    _, history_units = _conversation(fixture)
    records = []
    for repetition in range(1, repetitions + 1):
        output = raw_root / MODEL / f"mode-A-rep-{repetition}"
        raw = _run_model(_prompt("A", fixture), codex=codex, model=MODEL,
                         codex_home=codex_home, output=output, timeout=timeout, mcp_mode=None)
        grade_result = grade(raw["answer"], truth)
        records.append({
            "repetition": repetition, "answer": raw["answer"], "grade": grade_result,
            "provider_usage": raw["usage"], "elapsed_ms": raw["elapsed_ms"],
            "exit_code": raw["exit_code"], "conceptualize_calls": len(raw["tool_events"]),
        })
    result = {
        "benchmark": fixture["version"], "mode": "A_full_context_normal_agent",
        "model": MODEL, "reasoning_effort": "low", "repetitions": repetitions,
        "fixture_sha256": freeze["fixture_sha256"],
        "ground_truth_sha256": freeze["ground_truth_sha256"], "grader_sha256": freeze["grader_sha256"],
        "history_messages": freeze["messages"], "history_tokens_cl100k": freeze["history_tokens_cl100k"],
        "pass_count": sum(record["grade"]["passed"] for record in records),
        "records": records,
        "average_provider_input": _mean(records, "input_tokens"),
        "average_cached_input": _mean(records, "cached_input_tokens"),
        "average_provider_output": _mean(records, "output_tokens"),
        "average_elapsed_ms": round(sum(r["elapsed_ms"] for r in records) / repetitions, 2),
        "note": "Baseline calibration only. Conceptualize condition is blocked unless pass_count >= 2; 3/3 is target.",
    }
    _write_new(result_path, result)
    return result


def _conversation(fixture: dict) -> tuple[list, str]:
    units = ConversationAdapter().ingest({"conversations": [{
        "id": fixture["history_id"], "title": fixture["title"], "messages": fixture["history"],
    }]})
    ordered = sorted((u for u in units if u.source_type == "message"), key=lambda u: u.metadata["order"])
    history = "\n\n".join(f"[{u.metadata['timestamp']} {u.metadata['role']}] {u.content}" for u in ordered)
    return units, history


def compile_context(fixture: dict, budget: int = 4000) -> dict:
    units, _ = _conversation(fixture)
    return ContextUnitRuntime(units).pack(fixture["question"], budget, source_types={"message"})


def _mean(records: list[dict], key: str) -> float | None:
    values = [record.get("provider_usage", {}).get(key) for record in records]
    values = [value for value in values if isinstance(value, (int, float))]
    return round(sum(values) / len(values), 2) if values else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "verify", "baseline"))
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if args.action == "freeze":
        result = create_fixture()
    elif args.action == "verify":
        _, _, result = verify_freeze()
    else:
        result = run_baseline(args.repetitions)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

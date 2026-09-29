"""V0.8 Benchmark v4: deterministic whole-answer proposition grading."""

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
V3 = ROOT / "evaluations" / "v08-benchmark-v3"
EVAL = ROOT / "evaluations" / "v08-benchmark-v4"
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
    "Use only the supplied project conversation and current task. Return concise bullets under "
    "these headings: CURRENT ARCHITECTURE, CURRENT DECISIONS, CONSTRAINTS, SUPERSEDED DECISIONS, "
    "CURRENT STATE, NEXT STEP. State the current plan. Do not present historical proposals as current."
)
NEGATION = re.compile(r"\b(?:not|never|no longer|isn't|aren't|wasn't|weren't|doesn't|don't|cannot|can't)\b", re.I)
FUTURE_ONLY = re.compile(r"\b(?:may|might|could|possibly|perhaps|proposed|proposal|consider|eventually|someday|in the future|one day)\b", re.I)
STALE_MARKERS = re.compile(r"\b(?:superseded|replaced|obsolete|historical|formerly|old proposal|previous proposal|no longer current|not current)\b", re.I)


def _ground_truth() -> dict:
    # Lexical variants are authored from the frozen project state before any v4 answers.
    return {
        "version": "v0.8-benchmark-4",
        "created_before_model_runs": True,
        "grading_unit": "semantic proposition presence across the complete answer",
        "pass_rule": {"all_critical_facts_required": True, "minimum_coverage_percent": 100,
                      "stale_current_claims_allowed": 0},
        "facts": [
            {"id": "ARCH_01", "critical": True, "kind": "current", "proposition": "File System Access storage is preferred when supported.",
             "slots": [["file system access api", "filesystem access api", "filesystem"],
                       ["preferred", "prefer", "first choice", "primary"], ["available", "supported", "permitted"]],
             "canonical": "File System Access API is the preferred storage when available.",
             "paraphrase": "The attachment adapter prefers filesystem storage when available.",
             "negations": ["filesystem is not preferred", "filesystem is not the preferred option", "indexeddb is preferred instead"],
             "contradictions": ["indexeddb is the preferred backend", "filesystem access is not preferred"]},
            {"id": "ARCH_02", "critical": True, "kind": "current", "proposition": "IndexedDB blob storage is the fallback.",
             "slots": [["indexeddb", "indexed db", "idb"], ["blob", "blobs"], ["fallback", "fall back", "otherwise"]],
             "canonical": "IndexedDB blob storage is the fallback.",
             "paraphrase": "When filesystem access is unavailable, attachment blobs go into IndexedDB as a fallback.",
             "negations": ["indexeddb is not the fallback", "there is no indexeddb fallback"],
             "contradictions": ["filesystem is the only attachment backend"]},
            {"id": "DEC_01", "critical": True, "kind": "current_design", "proposition": "Both attachment backends are designed to share a read/write/delete adapter contract.",
             "slots": [["both backends", "both storage backends", "shared", "common", "same"],
                       ["adapter contract", "shared contract", "common interface", "contract", "interface"],
                       ["read", "reading"], ["write", "writing"], ["delete", "deleting"]],
             "canonical": "Both backends use the same adapter contract for read, write, and delete.",
             "paraphrase": "The shared attachment interface lets both storage options read, write, and delete.",
             "next_step_paraphrase": "Implement the attachment backend selection and shared read/write/delete contract, test both backends, then connect the adapter to SyncEngine.",
             "negations": ["backends do not share a contract", "the backends use different interfaces", "there is no shared adapter contract"],
             "contradictions": ["backends use different interfaces", "no shared attachment contract"]},
            {"id": "CON_01", "critical": True, "kind": "current", "proposition": "Retain local attachment data until the server acknowledges its authenticated upload.",
             "slots": [["local", "device"], ["authenticated", "auth"], ["upload", "uploaded"],
                       ["acknowledged", "acknowledgement", "acknowledge", "ack", "confirms", "confirmed"]],
             "canonical": "Keep local attachment data until the server acknowledges the authenticated upload.",
             "paraphrase": "Do not remove the device copy before the server confirms the authenticated upload.",
             "negations": ["delete local data before acknowledgement", "remove local data before server acknowledgement", "local data need not be retained until acknowledgement"],
             "contradictions": ["delete local data before acknowledgement", "remove local data before acknowledgement"]},
            {"id": "OLD_01", "critical": True, "kind": "superseded", "proposition": "The older localStorage-only proposal is superseded and is not current.",
             "slots": [["localstorage", "local storage"], ["superseded", "replaced", "historical", "old", "former"],
                       ["not current", "no longer current", "not the current", "not part of the current", "not in the current"]],
             "canonical": "The old localStorage-only proposal was superseded and is not current.",
             "paraphrase": "LocalStorage is the former approach; it is no longer current.",
             "negations": [], "contradictions": ["localstorage remains current", "localstorage is the current production backend"]},
            {"id": "STATE_01", "critical": True, "kind": "current", "proposition": "Production attachment adapters/backends and shared contract tests remain incomplete.",
             "slots": [["adapter", "backend", "attachment"],
                       ["incomplete", "unfinished", "not complete", "not finished", "not done", "need implementation"],
                       ["contract test", "shared test", "common test"]],
             "canonical": "The production attachment adapter is unfinished and shared contract tests are incomplete.",
             "paraphrase": "Production attachment backends still need implementation, and their common tests are not done.",
             "negations": ["adapter is complete and contract tests pass"],
             "contradictions": ["adapter is complete and contract tests pass"]},
            {"id": "NEXT_01", "critical": True, "kind": "next_step", "proposition": "Complete/test backend selection, reload persistence, permission fallback and acknowledgement-safe cleanup, then integrate with SyncEngine.",
             "slots": [["implement", "finish", "complete", "build"],
                       ["backend selection", "both backends", "backend implementations", "adapter"],
                       ["test", "contract test", "shared behavior", "verify"],
                       ["reload persistence", "persistence across reload", "reload", "persistence"],
                       ["fallback", "permission fallback"],
                       ["acknowledgement safe cleanup", "acknowledged upload cleanup", "cleanup", "ack", "acknowledgement gated deletion"],
                       ["syncengine", "sync engine"]],
             "canonical": "Finish backend selection and adapter tests for reload persistence, permission fallback, and cleanup after upload acknowledgement, then integrate with SyncEngine.",
             "paraphrase": "Implement both attachment backends, verify reload and permission fallback plus acknowledgement-gated deletion, and only then connect the adapter to the sync engine.",
             "negations": ["do not integrate syncengine", "syncengine integration is not next"],
             "contradictions": ["integrate syncengine before completing adapter tests"]},
        ],
        "stale_propositions": [
            {"id": "STALE_01", "anchors": ["localstorage", "local storage"],
             "current_claims": ["current", "production backend", "preferred backend", "in production"],
             "negated_forms": ["not current", "no longer current", "superseded", "historical", "old proposal", "former approach", "replaced"]},
            {"id": "STALE_02", "anchors": ["delete local", "remove local", "delete device", "remove device"],
             "current_claims": ["before acknowledgement", "before server acknowledgement", "before upload acknowledgement"],
             "negated_forms": ["do not", "don't", "never", "must not", "should not", "cannot"]},
        ],
    }


def _write_new(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def create_fixture() -> dict:
    if any(path.exists() for path in (FIXTURE_PATH, TRUTH_PATH, GRADER_PATH, FREEZE_PATH)):
        raise FileExistsError("V0.8 Benchmark v4 artifacts already exist; refusing to overwrite")
    fixture = json.loads((V3 / "fixture.json").read_text(encoding="utf-8"))
    fixture["version"] = "v0.8-benchmark-4"
    fixture["history_id"] = "offline-inspection-attachments-v08-v4"
    fixture["source_v3_fixture_sha256"] = _sha(V3 / "fixture.json")
    truth = _ground_truth()
    grader_spec = {
        "version": fixture["version"],
        "primary_unit": "whole-answer semantic proposition presence",
        "algorithm": "normalized token-set slots inside line/paragraph windows, explicit negation/stale/future checks, contradiction rules",
        "sections": "diagnostic and status-context only; not a requirement for proposition credit",
        "normalization": ["casefold", "punctuation-to-space", "whitespace-collapse", "limited configured singular/plural and lexical alternatives"],
        "model_judge": False,
    }
    _write_new(FIXTURE_PATH, fixture)
    _write_new(TRUTH_PATH, truth)
    _write_new(GRADER_PATH, grader_spec)
    freeze = {
        "fixture_version": fixture["version"], "fixture_sha256": _sha(FIXTURE_PATH),
        "ground_truth_sha256": _sha(TRUTH_PATH), "grader_sha256": _sha(GRADER_PATH),
        "grader_implementation_sha256": _sha(Path(__file__)),
        "source_v3_fixture_sha256": fixture["source_v3_fixture_sha256"],
        "question": fixture["question"], "messages": len(fixture["history"]),
        "history_tokens_cl100k": token_count(_format_history(fixture)), "model_runs_started": False,
        "pass_rule": truth["pass_rule"],
    }
    _write_new(FREEZE_PATH, freeze)
    return freeze


def _format_history(fixture: dict) -> str:
    return "\n\n".join(f"[{m.get('timestamp', '')} {m.get('role', 'user')}] {m.get('content', '')}" for m in fixture["history"])


def verify_freeze() -> tuple[dict, dict, dict]:
    fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    truth = json.loads(TRUTH_PATH.read_text(encoding="utf-8"))
    freeze = json.loads(FREEZE_PATH.read_text(encoding="utf-8"))
    checks = [(fixture["version"] == truth["version"] == freeze["fixture_version"], "version"),
              (fixture["question"] == freeze["question"], "task"),
              (_sha(FIXTURE_PATH) == freeze["fixture_sha256"], "fixture"),
              (_sha(TRUTH_PATH) == freeze["ground_truth_sha256"], "ground truth"),
              (_sha(GRADER_PATH) == freeze["grader_sha256"], "grader"),
              (_sha(Path(__file__)) == freeze["grader_implementation_sha256"], "grader implementation")]
    for valid, item in checks:
        if not valid:
            raise ValueError(f"V0.8 Benchmark v4 frozen {item} changed")
    return fixture, truth, freeze


def _tokens(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.casefold())
    result = []
    for word in words:
        if len(word) > 4 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
            word = word[:-1]
        result.append(word)
    return result


def _windows(answer: str) -> list[dict]:
    headings = {h: h for h in HEADINGS}
    active = "UNSPECIFIED"
    chunks = []
    for line in answer.splitlines():
        title = re.sub(r"[^A-Z0-9 ]", "", line.strip(" #>*_`:-").upper()).strip()
        if title in headings:
            active = title
            continue
        content = re.sub(r"^\s*[-*+]\s*", "", line).strip()
        if content:
            chunks.append({"section": active, "text": content, "tokens": set(_tokens(content))})
    if not chunks and answer.strip():
        chunks.append({"section": "UNSPECIFIED", "text": answer.strip(), "tokens": set(_tokens(answer))})
    return chunks


def _fact_window(text: str, slots: list[list[str]], window_size: int = 32) -> str | None:
    words = _tokens(text)
    if not words:
        return None
    best: tuple[int, int] | None = None
    for start in range(len(words)):
        limit = min(len(words), start + window_size)
        for end in range(start + 1, limit + 1):
            local = set(words[start:end])
            if all(any(set(_tokens(option)) <= local for option in alternatives) for alternatives in slots):
                if best is None or end - start < best[1] - best[0]:
                    best = (start, end)
                break
    if best is None:
        return None
    # Status and polarity are evaluated close to the matched proposition, so an unrelated
    # historical clause elsewhere on the same bullet cannot erase a current fact.
    start, end = best
    return " ".join(words[max(0, start - 16):min(len(words), end + 16)])


def _phrase_in(text: str, phrase: str) -> bool:
    haystack, needle = _tokens(text), _tokens(phrase)
    if not needle:
        return False
    return any(haystack[i:i + len(needle)] == needle for i in range(len(haystack)))


def _phrases_near(text: str, anchor: str, state: str, maximum_span: int = 14) -> str | None:
    tokens = _tokens(text)
    anchor_tokens, state_tokens = _tokens(anchor), _tokens(state)
    if not anchor_tokens or not state_tokens:
        return None
    anchors = [i for i in range(len(tokens) - len(anchor_tokens) + 1)
               if tokens[i:i + len(anchor_tokens)] == anchor_tokens]
    states = [i for i in range(len(tokens) - len(state_tokens) + 1)
              if tokens[i:i + len(state_tokens)] == state_tokens]
    for left in anchors:
        for right in states:
            low = min(left, right)
            high = max(left + len(anchor_tokens), right + len(state_tokens))
            if high - low <= maximum_span:
                return " ".join(tokens[low:high])
    return None


def _fact_present(fact: dict, windows: list[dict]) -> tuple[bool, bool, str | None]:
    matches = []
    for chunk in windows:
        local = _fact_window(chunk["text"], fact["slots"])
        if local is None:
            continue
        if any(_phrase_in(local, phrase) for phrase in fact["negations"]):
            continue
        if fact["kind"] in {"current", "current_design", "next_step"}:
            if chunk["section"] == "SUPERSEDED DECISIONS" or STALE_MARKERS.search(local):
                continue
            if fact["kind"] == "current" and FUTURE_ONLY.search(local):
                continue
        if fact["kind"] == "current_design" and FUTURE_ONLY.search(local):
            continue
        if any(_phrase_in(local, phrase) for phrase in fact["contradictions"]):
            continue
        matches.append(chunk)
    if matches:
        return True, False, matches[0]["section"]
    # Diagnostic: identify a lexical hit rejected for negation/obsolete/future status.
    rejected = []
    for chunk in windows:
        if _fact_window(chunk["text"], fact["slots"]) is not None:
            rejected.append(chunk)
    return False, bool(rejected), rejected[0]["section"] if rejected else None


def _stale_claims(windows: list[dict], rules: list[dict]) -> list[str]:
    result = []
    for rule in rules:
        for chunk in windows:
            text = chunk["text"]
            for anchor in rule["anchors"]:
                if not _phrase_in(text, anchor):
                    continue
                for state in rule["current_claims"]:
                    local = _phrases_near(text, anchor, state)
                    if local is None:
                        continue
                    if any(_phrase_in(local, marker) for marker in rule["negated_forms"]):
                        continue
                    result.append(rule["id"])
                    break
    return sorted(set(result))


def grade(answer: str, truth: dict | None = None) -> dict:
    truth = truth or json.loads(TRUTH_PATH.read_text(encoding="utf-8"))
    windows = _windows(answer)
    facts = []
    for fact in truth["facts"]:
        present, rejected, section = _fact_present(fact, windows)
        facts.append({"id": fact["id"], "critical": fact["critical"], "present": present,
                      "negated_or_stale_match": rejected, "matched_section": section})
    stale = _stale_claims(windows, truth["stale_propositions"])
    coverage = round(100 * sum(row["present"] for row in facts) / max(1, len(facts)), 2)
    missing = [row["id"] for row in facts if row["critical"] and not row["present"]]
    rule = truth["pass_rule"]
    return {"passed": not missing and coverage >= rule["minimum_coverage_percent"] and not stale,
            "coverage_percent": coverage, "facts_present": len(facts) - len(missing),
            "facts_total": len(facts), "critical_missing": missing,
            "stale_current_claims": stale, "propositions": facts}


def _conversation(fixture: dict) -> tuple[list, str]:
    units = ConversationAdapter().ingest({"conversations": [{"id": fixture["history_id"],
        "title": fixture["title"], "messages": fixture["history"]}]})
    ordered = sorted((unit for unit in units if unit.source_type == "message"), key=lambda unit: unit.metadata["order"])
    history = "\n\n".join(f"[{u.metadata['timestamp']} {u.metadata['role']}] {u.content}" for u in ordered)
    return units, history


def compile_context(fixture: dict, budget: int = 4000) -> dict:
    units, _ = _conversation(fixture)
    return ContextUnitRuntime(units).pack(fixture["question"], budget, source_types={"message"})


def _usage(events: list[dict]) -> dict:
    for event in reversed(events):
        if event.get("type") == "turn.completed":
            usage = event.get("usage") or {}
            return {key: usage.get(key) for key in ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens")}
    return {"input_tokens": None, "cached_input_tokens": None, "output_tokens": None, "total_tokens": None}


def _run_model(prompt: str, *, mode: str, output: Path, codex: str, codex_home: Path, timeout: int) -> dict:
    output.mkdir(parents=True, exist_ok=False)
    cwd = output / "empty-workspace"
    cwd.mkdir()
    (output / "prompt.txt").write_text(prompt, encoding="utf-8")
    mcp_mode = mode == "B"
    approval = (["--approve-for-me", "-c", 'approval_policy="on-request"'] if mcp_mode
                else ["-c", 'approval_policy="never"', "-s", "read-only"])
    command = [codex, "exec", "--ephemeral", "--skip-git-repo-check", "--json", "--model", MODEL,
               "-c", "model_reasoning_effort=low", *approval,
               "-c", "mcp_servers.conceptualize.command=" + json.dumps(sys.executable),
               "-c", 'mcp_servers.conceptualize.args=[]', "-c", "mcp_servers.conceptualize.enabled=false", "-"]
    env = {**os.environ, "CODEX_HOME": str(codex_home)}
    module_paths = [ROOT / "apps" / "api", ROOT / "apps" / "mcp", ROOT / "packages"]
    env["PYTHONPATH"] = os.pathsep.join(str(path) for path in module_paths) + (
        os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else ""
    )
    trace_path = output / "mcp-trace.json"
    if mcp_mode:
        server_args = ["-m", "conceptualize_evaluation.v08_benchmark_v4_mcp", "--trace", str(trace_path)]
        command[-1:-1] = ["-c", "mcp_servers.conceptualize.args=" + json.dumps(server_args),
                          "-c", "mcp_servers.conceptualize.enabled=true", "-c", "mcp_servers.conceptualize.required=true"]
        env["V08_V4_MCP_TRACE"] = str(trace_path)
    started = time.perf_counter()
    process = subprocess.run(command, input=prompt, cwd=cwd, env=env, capture_output=True, text=True,
                             encoding="utf-8", errors="replace", timeout=timeout)
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    events = []
    for line in process.stdout.splitlines():
        try:
            events.append(json.loads(line))
        except ValueError:
            continue
    (output / "agent-events.jsonl").write_text("".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events), encoding="utf-8")
    (output / "agent-stderr.txt").write_text(process.stderr, encoding="utf-8")
    tool_events = [e for e in events if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "mcp_tool_call"]
    answers = [e.get("item", {}).get("text", "") for e in events
               if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "agent_message"]
    answer = answers[-1] if answers else ""
    (output / "answer.md").write_text(answer, encoding="utf-8")
    return {"answer": answer, "exit_code": process.returncode, "elapsed_ms": elapsed,
            "provider_usage": _usage(events), "tool_events": tool_events, "events": events, "stderr": process.stderr}


def _prompt(mode: str, fixture: dict, history: str) -> str:
    task = fixture["question"]
    if mode == "A":
        return "\n\n".join((INSTRUCTIONS, "PROJECT CONVERSATION (oldest first):\n" + history, "CURRENT USER TASK:\n" + task))
    return "\n\n".join((INSTRUCTIONS, "@Conceptualize\n" + task))


def _mean(records: list[dict], key: str) -> float | None:
    vals = [row.get("provider_usage", {}).get(key) for row in records]
    vals = [value for value in vals if isinstance(value, (int, float))]
    return round(sum(vals) / len(vals), 2) if vals else None


def run_condition(mode: str, repetitions: int = 3, *, codex: str | None = None,
                  codex_home: Path | None = None, timeout: int = 240) -> dict:
    fixture, truth, freeze = verify_freeze()
    if mode not in {"A", "B"}:
        raise ValueError("V4 supports only primary conditions A and B")
    if mode == "B":
        baseline_path = RESULTS / "v08-v4-mode-a.json"
        if not baseline_path.exists():
            raise RuntimeError("V4 baseline evidence must exist before activated condition")
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        if baseline.get("fixture_sha256") != freeze["fixture_sha256"] or baseline.get("pass_count", 0) < 2:
            raise RuntimeError("V4 baseline did not meet >=2/3 gate; @Conceptualize is blocked")
    result_path = RESULTS / f"v08-v4-mode-{mode.lower()}.json"
    if result_path.exists():
        raise FileExistsError(f"Refusing to overwrite v4 result: {result_path}")
    codex = codex or shutil.which("codex") or "codex"
    codex_home = codex_home or ROOT / "evaluations" / "runs" / "v05-benchmark-codex-home"
    if not (codex_home / "auth.json").exists():
        raise FileNotFoundError("Authenticated Codex benchmark home is unavailable")
    _, history = _conversation(fixture)
    records = []
    for repetition in range(1, repetitions + 1):
        output = ROOT / "evaluations" / "runs" / "v08-v4" / MODEL / f"mode-{mode}-rep-{repetition}"
        raw = _run_model(_prompt(mode, fixture, history), mode=mode, output=output,
                         codex=codex, codex_home=codex_home, timeout=timeout)
        trace = json.loads((output / "mcp-trace.json").read_text(encoding="utf-8")) if (output / "mcp-trace.json").exists() else None
        records.append({"repetition": repetition, "answer": raw["answer"], "grade": grade(raw["answer"], truth),
                        "provider_usage": raw["provider_usage"], "elapsed_ms": raw["elapsed_ms"],
                        "exit_code": raw["exit_code"], "conceptualize_calls": len(raw["tool_events"]),
                        "tool_events": raw["tool_events"], "context_trace": trace})
    result = {"benchmark": fixture["version"], "mode": "A_full_context_normal_agent" if mode == "A" else "B_activated_conceptualize",
        "model": MODEL, "reasoning_effort": "low", "repetitions": repetitions,
        "fixture_sha256": freeze["fixture_sha256"], "ground_truth_sha256": freeze["ground_truth_sha256"],
        "grader_sha256": freeze["grader_sha256"], "grader_implementation_sha256": freeze["grader_implementation_sha256"],
        "history_messages": freeze["messages"], "history_tokens_cl100k": freeze["history_tokens_cl100k"],
        "pass_count": sum(r["grade"]["passed"] for r in records), "records": records,
        "average_provider_input": _mean(records, "input_tokens"), "average_cached_input": _mean(records, "cached_input_tokens"),
        "average_provider_output": _mean(records, "output_tokens"),
        "average_elapsed_ms": round(sum(r["elapsed_ms"] for r in records) / repetitions, 2)}
    _write_new(result_path, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "verify", "baseline", "activated"))
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    result = create_fixture() if args.action == "freeze" else (verify_freeze()[2] if args.action == "verify" else run_condition("A" if args.action == "baseline" else "B", args.repetitions))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

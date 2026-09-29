"""V0.8 Benchmark v3: section-aware, proposition-slot deterministic grading."""

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
V2 = ROOT / "evaluations" / "v08-benchmark-v2"
EVAL = ROOT / "evaluations" / "v08-benchmark-v3"
RESULTS = ROOT / "evaluations" / "results"
FIXTURE_PATH = EVAL / "fixture.json"
TRUTH_PATH = EVAL / "ground-truth.json"
GRADER_PATH = EVAL / "grader.json"
FREEZE_PATH = EVAL / "freeze.json"
HEADINGS = (
    "CURRENT ARCHITECTURE", "CURRENT DECISIONS", "CONSTRAINTS",
    "SUPERSEDED DECISIONS", "CURRENT STATE", "NEXT STEP",
)
MODEL = "gpt-6-sol"
INSTRUCTIONS = (
    "Use only the supplied project conversation and current task. Return concise bullets under "
    "these headings: CURRENT ARCHITECTURE, CURRENT DECISIONS, CONSTRAINTS, SUPERSEDED DECISIONS, "
    "CURRENT STATE, NEXT STEP. State the current plan. Do not present historical proposals as current."
)


def _dump(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _ground_truth() -> dict:
    # Required slots are semantic components with alternatives authored from the source facts.
    # Slots are checked within relevant answer sections; order and punctuation do not matter.
    return {
        "version": "v0.8-benchmark-3",
        "created_before_model_runs": True,
        "pass_rule": {"all_critical_facts_required": True, "minimum_coverage_percent": 100,
                      "stale_current_claims_allowed": 0},
        "facts": [
            {"id": "ARCH_01", "section_any": ["CURRENT ARCHITECTURE", "CURRENT DECISIONS"],
             "critical": True, "proposition": "File System Access API storage is preferred when supported.",
             "slots": [["file system access api", "filesystem access api", "filesystem"],
                       ["preferred", "prefer", "first choice", "primary"],
                       ["available", "supported", "permitted"]],
             "canonical": "File System Access API is the preferred storage when available.",
             "paraphrase": "The adapter prefers filesystem storage when available.",
             "contradictions": ["filesystem is not preferred", "indexeddb is preferred instead"]},
            {"id": "ARCH_02", "section_any": ["CURRENT ARCHITECTURE", "CURRENT DECISIONS"],
             "critical": True, "proposition": "IndexedDB blobs provide fallback attachment storage.",
             "slots": [["indexeddb", "indexed db", "idb"], ["blob", "blobs"],
                       ["fallback", "fall back", "otherwise"]],
             "canonical": "IndexedDB blob storage is the fallback.",
             "paraphrase": "If filesystem access is unavailable, attachment blobs use IndexedDB as the fallback.",
             "contradictions": ["indexeddb is not the fallback", "there is no indexeddb fallback"]},
            {"id": "DEC_01", "section_any": ["CURRENT ARCHITECTURE", "CURRENT DECISIONS"],
             "critical": True, "proposition": "Both backends provide the shared attachment read/write/delete contract.",
             "slots": [["both", "shared", "common", "same"],
                       ["backends", "backend", "adapter", "contract", "interface"],
                       ["read", "reading"], ["write", "writing"], ["delete", "deleting"]],
             "canonical": "Both backends implement one shared adapter contract for read, write, and delete.",
             "paraphrase": "The two storage options expose the same interface for reading, writing, and deleting attachments.",
             "contradictions": ["backends use different interfaces"]},
            {"id": "CON_01", "section_any": ["CONSTRAINTS"], "critical": True,
             "proposition": "Keep local data until the server acknowledges an authenticated upload.",
             "slots": [["local", "device"], ["authenticated", "auth"], ["upload", "uploaded"],
                       ["acknowledged", "acknowledgement", "acknowledge", "ack", "confirms", "confirmed"]],
             "canonical": "Keep local attachment data until the server acknowledges the authenticated upload.",
             "paraphrase": "Don't remove the device copy until the authenticated upload is confirmed by the server.",
             "contradictions": ["delete local data before acknowledgement", "local data need not be retained until acknowledgement"]},
            {"id": "OLD_01", "section_any": ["SUPERSEDED DECISIONS"], "critical": True,
             "proposition": "The localStorage-only proposal is superseded and not current.",
             "slots": [["localstorage", "local storage"], ["superseded", "replaced", "historical", "old"],
                       ["not current", "no longer current", "not the current", "not in the current"]],
             "canonical": "The earlier localStorage-only proposal was superseded and is not current.",
             "paraphrase": "The old LocalStorage method is no longer current.",
             "contradictions": ["localstorage remains current", "localstorage is the current proposal"]},
            {"id": "STATE_01", "section_any": ["CURRENT STATE"], "critical": True,
             "proposition": "Attachment adapters/backends and their shared contract tests remain incomplete.",
             "slots": [["adapter", "backend", "attachment"],
                       ["incomplete", "unfinished", "not complete", "not finished", "not done", "need implementation"] ,
                       ["contract test", "shared test", "common test"]],
             "canonical": "The adapter implementation is unfinished and the shared contract tests have not passed.",
             "paraphrase": "Production attachment backends still need implementation, and their common tests aren't done.",
             "contradictions": ["adapter is complete and contract tests pass"]},
            {"id": "NEXT_01", "section_any": ["NEXT STEP"], "critical": True,
             "proposition": "Finish backend selection and adapter tests for persistence/reload, fallback, and acknowledgement-safe cleanup before integrating with SyncEngine.",
             "slots": [["implement", "finish", "complete", "build"],
                       ["backend selection", "both backends", "backend implementations", "adapter"],
                       ["test", "contract test", "shared behavior", "verify"],
                       ["reload persistence", "persistence across reload", "reload", "persistence"],
                       ["fallback", "permission fallback"],
                       ["acknowledgement safe cleanup", "acknowledged upload cleanup", "cleanup", "ack",
                        "acknowledgement gated deletion"],
                       ["syncengine", "sync engine"]],
             "canonical": "Complete backend selection and both adapters; test contract behavior, reload persistence, permission fallback, and cleanup after upload acknowledgement, then connect the adapter to SyncEngine.",
             "paraphrase": "Implement both attachment backends, verify reload and permission fallback plus acknowledgement-gated deletion, and only then integrate with the sync engine.",
             "contradictions": ["integrate syncengine before completing adapter tests"]},
        ],
        "stale_propositions": [
            {"id": "STALE_01", "sections": ["CURRENT ARCHITECTURE", "CURRENT DECISIONS"],
             "anchor": ["localstorage", "local storage"], "stale_state": ["current", "production", "preferred"],
             "negation": ["not", "never", "no", "without", "superseded", "historical", "old", "former"]},
            {"id": "STALE_02", "sections": ["CONSTRAINTS"],
             "anchor": ["delete local", "remove local", "delete device", "remove device"],
             "stale_state": ["before acknowledgement", "before server acknowledgement", "before upload acknowledgement"],
             "negation": ["not", "never", "no", "must not", "should not"]},
        ],
    }


def create_fixture() -> dict:
    if any(path.exists() for path in (FIXTURE_PATH, TRUTH_PATH, GRADER_PATH, FREEZE_PATH)):
        raise FileExistsError("V0.8 Benchmark v3 artifacts already exist; refusing to overwrite")
    fixture = json.loads((V2 / "fixture.json").read_text(encoding="utf-8"))
    fixture["version"] = "v0.8-benchmark-3"
    fixture["history_id"] = "offline-inspection-attachments-v08-v3"
    fixture["source_v2_fixture_sha256"] = _sha(V2 / "fixture.json")
    truth = _ground_truth()
    grader_spec = {
        "version": "v0.8-benchmark-3",
        "algorithm": "section-scoped semantic slots; each slot accepts a predeclared normalized phrase set; contradiction and stale-state checks",
        "normalization": ["casefold", "punctuation-to-space", "whitespace-collapse", "limited configured singular/plural and lexical alternatives"],
        "allow_relevant_heading_variants": True,
        "ai_judge": False,
    }
    _dump(FIXTURE_PATH, fixture)
    _dump(TRUTH_PATH, truth)
    _dump(GRADER_PATH, grader_spec)
    history = _format_history(fixture)
    freeze = {
        "fixture_version": fixture["version"], "fixture_sha256": _sha(FIXTURE_PATH),
        "ground_truth_sha256": _sha(TRUTH_PATH), "grader_sha256": _sha(GRADER_PATH),
        "grader_implementation_sha256": _sha(Path(__file__)),
        "source_v2_fixture_sha256": fixture["source_v2_fixture_sha256"],
        "question": fixture["question"], "messages": len(fixture["history"]),
        "history_tokens_cl100k": token_count(history), "model_runs_started": False,
        "pass_rule": truth["pass_rule"],
    }
    _dump(FREEZE_PATH, freeze)
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
    for ok, name in checks:
        if not ok:
            raise ValueError(f"V0.8 Benchmark v3 frozen {name} changed")
    return fixture, truth, freeze


def _tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.casefold())
    result = set()
    for word in words:
        if len(word) > 4 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
            word = word[:-1]
        result.add(word)
    return result


def _token_list(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", text.casefold())
    result = []
    for word in words:
        if len(word) > 4 and word.endswith("ies"):
            word = word[:-3] + "y"
        elif len(word) > 3 and word.endswith("s") and not word.endswith(("ss", "us", "is")):
            word = word[:-1]
        result.append(word)
    return result


def _sections(answer: str) -> dict[str, str]:
    values: dict[str, list[str]] = {}
    active = None
    lookup = {re.sub(r"[^A-Z0-9 ]", "", heading).strip(): heading for heading in HEADINGS}
    for line in answer.splitlines():
        clean = re.sub(r"[^A-Z0-9 ]", "", line.strip(" #>*_`:-").upper()).strip()
        if clean in lookup:
            active = lookup[clean]
            values.setdefault(active, [])
        elif active:
            values[active].append(line)
    if not values:
        return {heading: answer for heading in HEADINGS}
    return {heading: " ".join(lines) for heading, lines in values.items()}


def _slots_present(text: str, slots: list[list[str]]) -> bool:
    words = _tokens(text)
    return all(any(_tokens(option) <= words for option in slot) for slot in slots)


def _contradicted(text: str, patterns: list[str]) -> bool:
    words = _token_list(text)
    for pattern in patterns:
        phrase = _token_list(pattern)
        if phrase and any(words[index:index + len(phrase)] == phrase for index in range(len(words))):
            return True
    return False


def _stale_claim(section: str, rule: dict) -> bool:
    folded = section.casefold()
    for anchor in rule["anchor"]:
        for state in rule["stale_state"]:
            pattern = re.compile(re.escape(anchor) + r".{0,70}" + re.escape(state), re.I | re.S)
            for match in pattern.finditer(folded):
                before_state = folded[match.start():match.end()]
                state_index = before_state.lower().rfind(state)
                prefix = folded[max(0, match.start() - 24):match.start() + state_index]
                if not any(re.search(r"\b" + re.escape(neg) + r"\b", prefix, re.I) for neg in rule["negation"]):
                    return True
    return False


def grade(answer: str, truth: dict | None = None) -> dict:
    truth = truth or json.loads(TRUTH_PATH.read_text(encoding="utf-8"))
    sections = _sections(answer)
    checks = []
    for fact in truth["facts"]:
        text = " ".join(sections.get(section, "") for section in fact["section_any"])
        contradiction = _contradicted(text, fact["contradictions"])
        checks.append({"id": fact["id"], "critical": fact["critical"],
                       "present": _slots_present(text, fact["slots"]) and not contradiction,
                       "contradicted": contradiction})
    stale = [rule["id"] for rule in truth["stale_propositions"]
             if any(_stale_claim(sections.get(section, ""), rule) for section in rule["sections"])]
    coverage = round(100 * sum(check["present"] for check in checks) / max(1, len(checks)), 2)
    missing = [check["id"] for check in checks if check["critical"] and not check["present"]]
    rule = truth["pass_rule"]
    return {"passed": not missing and coverage >= rule["minimum_coverage_percent"] and not stale,
            "coverage_percent": coverage, "facts_present": len(checks) - len(missing),
            "facts_total": len(checks), "critical_missing": missing,
            "stale_current_claims": stale, "propositions": checks}


def _conversation(fixture: dict) -> tuple[list, str]:
    units = ConversationAdapter().ingest({"conversations": [{"id": fixture["history_id"],
        "title": fixture["title"], "messages": fixture["history"]}]})
    ordered = sorted((u for u in units if u.source_type == "message"), key=lambda u: u.metadata["order"])
    return units, "\n\n".join(f"[{u.metadata['timestamp']} {u.metadata['role']}] {u.content}" for u in ordered)


def compile_context(fixture: dict, budget: int = 4000) -> dict:
    units, _ = _conversation(fixture)
    return ContextUnitRuntime(units).pack(fixture["question"], budget, source_types={"message"})


def run_baseline(repetitions: int = 3, *, codex: str | None = None, codex_home: Path | None = None,
                 timeout: int = 240) -> dict:
    fixture, truth, freeze = verify_freeze()
    result_path = RESULTS / "v08-v3-mode-a.json"
    if result_path.exists():
        raise FileExistsError(f"Refusing to overwrite v3 result: {result_path}")
    codex = codex or shutil.which("codex") or "codex"
    codex_home = codex_home or ROOT / "evaluations" / "runs" / "v05-benchmark-codex-home"
    if not (codex_home / "auth.json").exists():
        raise FileNotFoundError("Authenticated Codex benchmark home is unavailable")
    _, history = _conversation(fixture)
    records = []
    for repetition in range(1, repetitions + 1):
        prompt = "\n\n".join((INSTRUCTIONS, "PROJECT CONVERSATION (oldest first):\n" + history,
                               "CURRENT USER TASK:\n" + fixture["question"]))
        output = ROOT / "evaluations" / "runs" / "v08-v3" / MODEL / f"mode-A-rep-{repetition}"
        raw = _run_model(prompt, codex=codex, model=MODEL, codex_home=codex_home,
                         output=output, timeout=timeout, mcp_mode=None)
        records.append({"repetition": repetition, "answer": raw["answer"], "grade": grade(raw["answer"], truth),
                        "provider_usage": raw["usage"], "elapsed_ms": raw["elapsed_ms"],
                        "exit_code": raw["exit_code"], "conceptualize_calls": 0})
    summary = {"benchmark": fixture["version"], "mode": "A_full_context_normal_agent",
        "model": MODEL, "reasoning_effort": "low", "repetitions": repetitions,
        "fixture_sha256": freeze["fixture_sha256"], "ground_truth_sha256": freeze["ground_truth_sha256"],
        "grader_sha256": freeze["grader_sha256"], "grader_implementation_sha256": freeze["grader_implementation_sha256"],
        "history_messages": freeze["messages"], "history_tokens_cl100k": freeze["history_tokens_cl100k"],
        "pass_count": sum(r["grade"]["passed"] for r in records), "records": records,
        "average_provider_input": _mean(records, "input_tokens"),
        "average_cached_input": _mean(records, "cached_input_tokens"),
        "average_provider_output": _mean(records, "output_tokens"),
        "average_elapsed_ms": round(sum(r["elapsed_ms"] for r in records) / repetitions, 2),
        "note": "Baseline calibration only. @Conceptualize is blocked unless >=2/3 pass; target is 3/3."}
    _dump(result_path, summary)
    return summary


def _mean(records: list[dict], key: str) -> float | None:
    values = [r.get("provider_usage", {}).get(key) for r in records]
    values = [v for v in values if isinstance(v, (int, float))]
    return round(sum(values) / len(values), 2) if values else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "verify", "baseline"))
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    result = create_fixture() if args.action == "freeze" else (verify_freeze()[2] if args.action == "verify" else run_baseline(args.repetitions))
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

"""V0.9 blind semantic evaluation of the Conceptualize capability."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from conceptualize_runtime.adapters import ConversationAdapter
from conceptualize_runtime.context import ContextUnitRuntime
from conceptualize_runtime.runtime import token_count

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "evaluations" / "v08-benchmark-v4" / "fixture.json"
EVAL = ROOT / "evaluations" / "v09-benchmark"
RESULTS = ROOT / "evaluations" / "results"
RUNS = ROOT / "evaluations" / "runs" / "v09"
FIXTURE = EVAL / "fixture.json"
TRUTH = EVAL / "ground-truth.json"
PROMPT_TEMPLATE = EVAL / "semantic-evaluator-prompt.txt"
FREEZE = EVAL / "freeze.json"
GENERATION_MODEL = "gpt-6-sol"
GENERATION_REASONING = "low"
EVALUATOR_MODEL = "gpt-6-astra"
EVALUATOR_REASONING = "low"
PASS_RULE = {
    "all_critical_propositions_present": True,
    "minimum_total_coverage_percent": 85,
    "maximum_stale_as_current": 0,
    "maximum_contradictions": 0,
}
SYSTEM_INSTRUCTIONS = (
    "You are continuing work on a project from its prior conversation. Use the available project "
    "context to answer the user's task directly. Distinguish current decisions from superseded "
    "proposals. Be concise, but include the relevant architecture, constraints, current status, "
    "and next step."
)
EVALUATOR_TEMPLATE = """You are a blinded semantic evaluator. Judge only whether each frozen proposition is represented with the correct meaning and temporal status in the supplied artifact. Do not use exact-wording, heading, or sentence-position requirements. A harmless paraphrase counts. Mere mention is not endorsement. Do not infer facts beyond the supplied ground truth.

Benchmark task:
{{TASK}}

Frozen ground-truth propositions and pass criteria:
{{GROUND_TRUTH}}

Status rules:
- present: the proposition is clearly asserted with the required status. For a superseded proposition, it must be identified as old/replaced and not current.
- absent: the proposition is omitted, too vague, or mentioned only as a possibility/future proposal when current status is required.
- contradicted: the artifact clearly asserts the opposite of a current proposition or denies an explicitly frozen state.
- stale_as_current: an explicitly superseded proposition is presented as current, preferred, or implemented. Mentioning it as historical/superseded is not an error.
Use the entire artifact. Headings do not determine credit. Future work is not current implementation. If wording is genuinely ambiguous, choose absent and explain briefly. Evidence must be a short exact quotation from the artifact; use an empty string only when no evidence exists.

Return exactly one JSON object, without markdown, matching this schema:
{"answer_id":"string","propositions":[{"id":"string","status":"present|absent|contradicted|stale_as_current","evidence":"short exact quote or empty string","reason":"brief semantic rationale"}],"critical_proposition_coverage_percent":0,"total_proposition_coverage_percent":0,"stale_current_errors":0,"contradiction_count":0,"pass":false}

Coverage is the fraction of propositions with status present. Critical coverage counts critical propositions only. Pass only when every critical proposition is present, total coverage meets the frozen minimum, and stale-current and contradiction counts are within the frozen limits. Include every proposition exactly once, in frozen order. The answer ID is only a neutral identifier; do not infer its experimental condition.

Evaluate this artifact:
answer_id: {{ANSWER_ID}}
{{ARTIFACT}}
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_new(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(content)


def _truth() -> dict[str, Any]:
    facts = [
        {"id": "ARCH_01", "critical": True, "status": "current", "proposition":
         "The current client is a browser PWA for desktop and mobile, using the existing HTTPS JSON API.",
         "opposite": "The current client is a native desktop application or does not use the HTTPS API."},
        {"id": "ARCH_02", "critical": True, "status": "current", "proposition":
         "Local persistence and synchronization are separate layers that can be replaced independently."},
        {"id": "DEC_01", "critical": True, "status": "current", "proposition":
         "Inspection records use IndexedDB; attachments prefer File System Access when available and fall back to IndexedDB blobs."},
        {"id": "DEC_02", "critical": True, "status": "current_design", "proposition":
         "Both attachment storage backends share the same read, write, and delete interface."},
        {"id": "CON_01", "critical": True, "status": "current_constraint", "proposition":
         "Keep each local attachment until its own authenticated upload is acknowledged by the server."},
        {"id": "OLD_01", "critical": True, "status": "superseded", "proposition":
         "The localStorage-only production storage decision is superseded and is not current."},
        {"id": "STATE_01", "critical": True, "status": "current_state", "proposition":
         "Record persistence and metadata synchronization are integrated, but production attachment backends, shared contract tests, and end-to-end attachment transfer remain unfinished."},
        {"id": "NEXT_01", "critical": True, "status": "next_step", "proposition":
         "Implement backend selection and shared adapter behavior, test reload persistence, permission fallback, and acknowledgement-safe cleanup, then integrate the adapter with SyncEngine."},
    ]
    return {"version": "v0.9-capability-semantic-v1", "facts": facts,
            "pass_rule": PASS_RULE,
            "status_definitions": {"current": "Asserted as true in the current project state.",
                                   "current_design": "An adopted design, even if its implementation is unfinished.",
                                   "current_constraint": "A requirement that remains binding.",
                                   "superseded": "An old decision that must not be treated as current.",
                                   "current_state": "Implemented versus unfinished state.",
                                   "next_step": "The next planned action and required sequencing."}}


def create_frozen_fixture() -> dict[str, Any]:
    if any(path.exists() for path in (FIXTURE, TRUTH, PROMPT_TEMPLATE, FREEZE)):
        raise FileExistsError("V0.9 frozen benchmark artifacts exist; refusing to overwrite")
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    source["version"] = "v0.9-capability-semantic-v1"
    source["title"] = "Offline inspection PWA attachment-state continuation"
    source["history_id"] = "offline-inspection-attachments-v09"
    source["question"] = (
        "Continue the attachment-storage work from the project history. Describe the current "
        "architecture and decisions, the constraints that still apply, which earlier choice is "
        "no longer current, what is implemented versus unfinished, and the next step."
    )
    write_new(FIXTURE, json.dumps(source, ensure_ascii=False, indent=2) + "\n")
    truth = _truth()
    write_new(TRUTH, json.dumps(truth, ensure_ascii=False, indent=2) + "\n")
    write_new(PROMPT_TEMPLATE, EVALUATOR_TEMPLATE)
    # Freeze records hashes and source provenance before any benchmark answer is generated.
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    units, history = conversation(fixture)
    freeze = {"benchmark": "v0.9-capability-semantic-v1", "fixture_sha256": sha256(FIXTURE),
              "ground_truth_sha256": sha256(TRUTH), "evaluator_prompt_sha256": sha256(PROMPT_TEMPLATE),
              "fixture_source": "v0.8-benchmark-v4/fixture.json", "source_fixture_sha256": sha256(SOURCE),
              "history_messages": len(fixture["history"]), "history_tokens_cl100k": token_count(history),
              "task": fixture["question"], "generation_model": GENERATION_MODEL,
              "generation_reasoning": GENERATION_REASONING, "evaluator_model": EVALUATOR_MODEL,
              "evaluator_reasoning": EVALUATOR_REASONING, "evaluator_temperature": "not exposed by Codex CLI",
              "pass_rule": PASS_RULE, "model_runs_started": False,
              "context_units": len(units), "freeze_created_before_answers": True}
    write_new(FREEZE, json.dumps(freeze, ensure_ascii=False, indent=2) + "\n")
    return freeze


def verify_freeze() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    freeze = json.loads(FREEZE.read_text(encoding="utf-8"))
    checks = {"fixture_sha256": sha256(FIXTURE), "ground_truth_sha256": sha256(TRUTH),
              "evaluator_prompt_sha256": sha256(PROMPT_TEMPLATE)}
    for key, value in checks.items():
        if freeze[key] != value:
            raise RuntimeError(f"Frozen V0.9 artifact changed: {key}")
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    if fixture["question"] != freeze["task"] or truth["pass_rule"] != freeze["pass_rule"]:
        raise RuntimeError("Frozen V0.9 task or pass criteria changed")
    return fixture, truth, freeze


def conversation(fixture: dict[str, Any]) -> tuple[list[Any], str]:
    units = ConversationAdapter().ingest({"conversations": [{"id": fixture["history_id"],
        "title": fixture["title"], "messages": fixture["history"]}]})
    messages = sorted((u for u in units if u.source_type == "message"),
                      key=lambda u: u.metadata["order"])
    history = "\n\n".join(
        f"[{u.metadata['timestamp']} {u.metadata['role']}] {u.content}" for u in messages)
    return units, history


def compile_working_context(
    fixture: dict[str, Any], token_budget: int = 4000, *, task: str | None = None
) -> dict[str, Any]:
    units, _ = conversation(fixture)
    return ContextUnitRuntime(units).pack(task or fixture["question"], token_budget,
                                          source_types={"message"})


def _extract_events(stdout: str) -> list[dict[str, Any]]:
    events = []
    for line in stdout.splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict):
            events.append(event)
    return events


def _usage(events: list[dict[str, Any]]) -> dict[str, Any]:
    for event in reversed(events):
        if event.get("type") == "turn.completed":
            usage = event.get("usage") or {}
            return {key: usage.get(key) for key in
                    ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens")}
    return {"input_tokens": None, "cached_input_tokens": None,
            "output_tokens": None, "total_tokens": None}


def _final_text(events: list[dict[str, Any]], item_type: str) -> str:
    items = [event.get("item", {}) for event in events
             if event.get("type") == "item.completed" and event.get("item", {}).get("type") == item_type]
    return items[-1].get("text", "") if items else ""


def _post_capability_items(events: list[dict[str, Any]]) -> list[str] | None:
    tool_positions = [index for index, event in enumerate(events)
                      if event.get("type") == "item.completed" and
                      event.get("item", {}).get("type") == "mcp_tool_call"]
    if not tool_positions:
        return None
    return [event.get("item", {}).get("type", "unknown") for event in events[max(tool_positions) + 1:]
            if event.get("type") == "item.completed" and
            event.get("item", {}).get("type") != "mcp_tool_call"]


def _codex_call(prompt: str, *, model: str, output_dir: Path, codex_home: Path,
                timeout: int, mcp_enabled: bool = False,
                mcp_trace: Path | None = None) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=False)
    cwd = output_dir / "empty-workspace"
    cwd.mkdir()
    (output_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    command = [shutil.which("codex") or "codex", "exec", "--ephemeral", "--ignore-user-config", "--skip-git-repo-check",
               "--json", "--model", model, "-c", "model_reasoning_effort=low"]
    if mcp_enabled:
        server = ["-m", "conceptualize_evaluation.v09_mcp_fixture_server", "--trace", str(mcp_trace)]
        command.extend(["--approve-for-me", "-c", 'approval_policy="on-request"', "-s", "read-only",
                        "-c", "mcp_servers.conceptualize.command=" + json.dumps(sys.executable),
                        "-c", "mcp_servers.conceptualize.args=" + json.dumps(server),
                        "-c", "mcp_servers.conceptualize.enabled=true",
                        "-c", "mcp_servers.conceptualize.required=true"])
    else:
        command.extend(["-c", 'approval_policy="never"', "-s", "read-only"])
    command.append("-")
    env = {**os.environ, "CODEX_HOME": str(codex_home)}
    env["PYTHONPATH"] = os.pathsep.join(str(ROOT / folder) for folder in
        ("apps/api", "apps/mcp", "packages")) + (
            os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    if mcp_trace:
        env["V09_MCP_TRACE"] = str(mcp_trace)
    (output_dir / "command-metadata.json").write_text(json.dumps(
        {"model": model, "reasoning": "low", "mcp_enabled": mcp_enabled,
         "mcp_server": "conceptualize_evaluation.v09_mcp_fixture_server" if mcp_enabled else None},
        indent=2) + "\n", encoding="utf-8")
    started = time.perf_counter()
    process = subprocess.run(command, input=prompt, cwd=cwd, env=env, capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=timeout)
    elapsed = round((time.perf_counter() - started) * 1000, 2)
    events = _extract_events(process.stdout)
    (output_dir / "agent-events.jsonl").write_text(
        "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in events), encoding="utf-8")
    (output_dir / "agent-stderr.txt").write_text(process.stderr, encoding="utf-8")
    return {"events": events, "text": _final_text(events, "agent_message"),
            "usage": _usage(events), "elapsed_ms": elapsed, "exit_code": process.returncode,
            "tool_events": [e for e in events if e.get("type") == "item.completed" and
                            e.get("item", {}).get("type") == "mcp_tool_call"],
            "stderr": process.stderr}


def generation_prompt(fixture: dict[str, Any], mode: str, history: str) -> str:
    task = fixture["question"]
    if mode == "control":
        return "\n\n".join((SYSTEM_INSTRUCTIONS, "PROJECT HISTORY (oldest first):\n" + history,
                              "USER TASK:\n" + task))
    return "\n\n".join((SYSTEM_INSTRUCTIONS, "@Conceptualize\n" + task))


def evaluator_prompt(task: str, truth: dict[str, Any], answer_id: str, artifact: str) -> str:
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    rendered = template.replace("{{TASK}}", task).replace(
        "{{GROUND_TRUTH}}", json.dumps(truth, ensure_ascii=False, sort_keys=True)).replace(
        "{{ANSWER_ID}}", answer_id).replace("{{ARTIFACT}}", artifact)
    return rendered


def _json_object(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Evaluator did not return a JSON object")
    value = json.loads(text[start:end + 1])
    if not isinstance(value, dict):
        raise ValueError("Evaluator JSON must be an object")
    return value


def validate_grade(grade: dict[str, Any], truth: dict[str, Any], answer_id: str) -> None:
    if grade.get("answer_id") != answer_id:
        raise ValueError("Evaluator answer_id mismatch")
    expected = [fact["id"] for fact in truth["facts"]]
    observed = [fact.get("id") for fact in grade.get("propositions", [])]
    if observed != expected:
        raise ValueError("Evaluator omitted, duplicated, or reordered frozen propositions")
    allowed = {"present", "absent", "contradicted", "stale_as_current"}
    if any(fact.get("status") not in allowed for fact in grade["propositions"]):
        raise ValueError("Evaluator returned an unsupported proposition status")
    critical_ids = {fact["id"] for fact in truth["facts"] if fact["critical"]}
    by_id = {fact["id"]: fact for fact in grade["propositions"]}
    critical_present = sum(by_id[fact_id]["status"] == "present" for fact_id in critical_ids)
    critical_coverage = round(100 * critical_present / max(1, len(critical_ids)), 2)
    total_present = sum(fact["status"] == "present" for fact in grade["propositions"])
    total_coverage = round(100 * total_present / max(1, len(expected)), 2)
    stale = sum(fact["status"] == "stale_as_current" for fact in grade["propositions"])
    contradictions = sum(fact["status"] == "contradicted" for fact in grade["propositions"])
    expected_pass = (critical_present == len(critical_ids) and
                     total_coverage >= truth["pass_rule"]["minimum_total_coverage_percent"] and
                     stale <= truth["pass_rule"]["maximum_stale_as_current"] and
                     contradictions <= truth["pass_rule"]["maximum_contradictions"])
    if (grade.get("critical_proposition_coverage_percent") != critical_coverage or
            grade.get("total_proposition_coverage_percent") != total_coverage or
            grade.get("stale_current_errors") != stale or
            grade.get("contradiction_count") != contradictions or
            grade.get("pass") is not expected_pass):
        raise ValueError("Evaluator aggregate fields disagree with its proposition statuses")


def context_utilization_metrics(
    truth: dict[str, Any], retrieval_grade: dict[str, Any],
    working_context_grade: dict[str, Any], answer_grade: dict[str, Any],
) -> dict[str, Any]:
    """Separate source retrieval, context compilation, and final answer use."""
    def status_map(grade: dict[str, Any]) -> dict[str, str]:
        return {item["id"]: item["status"] for item in grade["propositions"]}

    retrieval = status_map(retrieval_grade)
    working = status_map(working_context_grade)
    answer = status_map(answer_grade)
    facts = truth["facts"]
    working_available = [fact for fact in facts if working.get(fact["id"]) == "present"]
    critical_available = [
        fact for fact in working_available if fact.get("critical") is True
    ]
    used = [fact for fact in working_available if answer.get(fact["id"]) == "present"]
    critical_used = [
        fact for fact in critical_available if answer.get(fact["id"]) == "present"
    ]
    propositions = []
    for fact in facts:
        fact_id = fact["id"]
        retrieval_status = retrieval.get(fact_id, "absent")
        working_status = working.get(fact_id, "absent")
        answer_status = answer.get(fact_id, "absent")
        if working_status == "present" and answer_status != "present":
            failure = "MODEL_UTILIZATION_OMISSION"
        elif retrieval_status != "present":
            failure = "RETRIEVAL_FAILURE"
        elif working_status != "present":
            failure = "WORKING_CONTEXT_COMPILATION_OMISSION"
        elif answer_status != "present":
            failure = "MODEL_UTILIZATION_OMISSION"
        else:
            failure = None
        propositions.append({
            "id": fact_id,
            "critical": fact.get("critical") is True,
            "retrieval_status": retrieval_status,
            "working_context_status": working_status,
            "final_answer_status": answer_status,
            "failure_classification": failure,
        })

    def percentage(numerator: int, denominator: int) -> float | None:
        return round(100 * numerator / denominator, 2) if denominator else None

    return {
        "context_retrieval_coverage_percent": percentage(
            sum(retrieval.get(fact["id"]) == "present" for fact in facts), len(facts)
        ),
        "working_context_coverage_percent": percentage(len(working_available), len(facts)),
        "final_answer_coverage_percent": percentage(
            sum(answer.get(fact["id"]) == "present" for fact in facts), len(facts)
        ),
        "context_utilization_rate_percent": percentage(len(used), len(working_available)),
        "critical_context_utilization_rate_percent": percentage(
            len(critical_used), len(critical_available)
        ),
        "working_context_propositions_available": len(working_available),
        "critical_propositions_available": len(critical_available),
        "propositions": propositions,
    }


def _run_judge(artifact: str, answer_id: str, *, fixture: dict[str, Any], truth: dict[str, Any],
               codex_home: Path, timeout: int, run_dir: Path) -> dict[str, Any]:
    prompt = evaluator_prompt(fixture["question"], truth, answer_id, artifact)
    raw = _codex_call(prompt, model=EVALUATOR_MODEL, output_dir=run_dir,
                      codex_home=codex_home, timeout=timeout)
    grade = _json_object(raw["text"])
    validate_grade(grade, truth, answer_id)
    return {"evaluation_id": answer_id, "grade": grade, "provider_usage": raw["usage"],
            "elapsed_ms": raw["elapsed_ms"], "exit_code": raw["exit_code"]}


def _synthetic_cases() -> list[dict[str, Any]]:
    complete = """Atlas is a browser PWA for desktop and mobile over the HTTPS JSON API. Persistence and sync are independently replaceable. Inspection records live in IndexedDB; attachments use filesystem access where supported and IndexedDB blobs otherwise. Both attachment stores implement the same read/write/delete methods. Keep each device copy until its authenticated upload is acknowledged by the server. The localStorage-only production plan has been replaced. Record storage and metadata sync work; production attachment stores, common tests, and end-to-end transfer are still unfinished. Next, implement the shared adapter and backend choice, test reload persistence, permission fallback and acknowledgement-safe cleanup, then wire it to SyncEngine."""
    paraphrase = """Today crews use the web app on phones and desktops against the HTTPS service. Offline record persistence is separate from transfer logic. Records are in the browser database; photo files use the user's file-system permission when possible and browser-database blobs if not. Either photo implementation exposes the same operations for saving, loading, and removing data. A device must retain a photo until that specific signed-in upload receives server confirmation. The old localStorage-only plan was abandoned. Record saving and metadata transfer are working, while real photo storage, shared behavior tests, and full upload flow are not done. Finish the adapter/backend choice, verify persistence after reload, denied-permission fallback and safe post-ack cleanup, and only then connect it to the sync engine."""
    variants = [
        {"name": "COMPLETE", "artifact": complete,
         "expected": {fact_id: "present" for fact_id in ("ARCH_01", "ARCH_02", "DEC_01", "DEC_02", "CON_01", "OLD_01", "STATE_01", "NEXT_01")}, "pass": True},
        {"name": "PARAPHRASED_COMPLETE", "artifact": paraphrase,
         "expected": {fact_id: "present" for fact_id in ("ARCH_01", "ARCH_02", "DEC_01", "DEC_02", "CON_01", "OLD_01", "STATE_01", "NEXT_01")}, "pass": True},
        {"name": "OMISSION", "artifact": complete.replace("Keep each device copy until its authenticated upload is acknowledged by the server. ", ""),
         "expected": {"CON_01": "absent"}, "pass": False},
        {"name": "CONTRADICTION", "artifact": complete.replace("attachments use filesystem access where supported and IndexedDB blobs otherwise", "attachments use IndexedDB only; filesystem access is rejected"),
         "expected": {"DEC_01": "contradicted"}, "pass": False},
        {"name": "STALE_AS_CURRENT", "artifact": complete.replace("The localStorage-only production plan has been replaced.", "The localStorage-only store is the current production choice."),
         "expected": {"OLD_01": "stale_as_current"}, "pass": False},
        {"name": "STALE_CORRECTLY_LABELED", "artifact": complete,
         "expected": {"OLD_01": "present"}, "pass": True},
        {"name": "FUTURE_VS_CURRENT", "artifact": complete.replace("Inspection records live in IndexedDB; attachments use filesystem access where supported and IndexedDB blobs otherwise.", "Inspection records live in IndexedDB. The team might consider filesystem access for attachments someday."),
         "expected": {"DEC_01": "absent"}, "pass": False},
        {"name": "HEADING_INDEPENDENT", "artifact": "## Miscellaneous\n\n" + complete,
         "expected": {fact_id: "present" for fact_id in ("ARCH_01", "ARCH_02", "DEC_01", "DEC_02", "CON_01", "OLD_01", "STATE_01", "NEXT_01")}, "pass": True},
    ]
    return variants


def run_evaluator_self_tests(*, codex_home: Path, timeout: int = 120) -> dict[str, Any]:
    fixture, truth, _ = verify_freeze()
    records = []
    for index, case in enumerate(_synthetic_cases(), 1):
        record = _run_judge(case["artifact"], f"synthetic_{index:02d}", fixture=fixture,
                            truth=truth, codex_home=codex_home, timeout=timeout,
                            run_dir=RUNS / "evaluator-self-test-retry-2" / case["name"])
        by_id = {item["id"]: item["status"] for item in record["grade"]["propositions"]}
        checks = {fact_id: by_id.get(fact_id) == status for fact_id, status in case["expected"].items()}
        checks["pass_rule"] = record["grade"]["pass"] is case["pass"]
        record.update({"case": case["name"], "expected_statuses": case["expected"],
                      "checks": checks, "passed": all(checks.values())})
        records.append(record)
    result = {"benchmark": "v0.9-capability-semantic-v1", "evaluator_model": EVALUATOR_MODEL,
              "prompt_sha256": sha256(PROMPT_TEMPLATE), "self_test_count": len(records),
              "passed": sum(record["passed"] for record in records), "records": records}
    out = RESULTS / "v09-evaluator-self-test.json"
    write_new(out, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    if result["passed"] != result["self_test_count"]:
        raise RuntimeError("Semantic evaluator reliability checks failed; baseline must not run")
    return result


def _records_path(condition: str) -> Path:
    return RESULTS / f"v09-{condition}.json"


def run_generation_condition(condition: str, *, repetitions: int = 3, codex_home: Path,
                             timeout: int = 240) -> dict[str, Any]:
    fixture, truth, freeze = verify_freeze()
    if condition not in {"control", "conceptualize"}:
        raise ValueError("condition must be control or conceptualize")
    if condition == "conceptualize":
        baseline_path = _records_path("control")
        if not baseline_path.exists():
            raise RuntimeError("V0.9 full-context baseline must be run first")
        baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
        if baseline.get("pass_count", 0) < 2:
            raise RuntimeError("Baseline below 2/3; activated comparison is gated")
    result_path = _records_path(condition)
    if result_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing V0.9 result: {result_path}")
    _, history = conversation(fixture)
    generation_records = []
    for repetition in range(1, repetitions + 1):
        run_dir = RUNS / condition / f"rep-{repetition}"
        trace_path = run_dir / "conceptualize-trace.json"
        prompt = generation_prompt(fixture, condition, history)
        raw = _codex_call(prompt, model=GENERATION_MODEL, output_dir=run_dir,
                          codex_home=codex_home, timeout=timeout,
                          mcp_enabled=condition == "conceptualize",
                          mcp_trace=trace_path if condition == "conceptualize" else None)
        trace = json.loads(trace_path.read_text(encoding="utf-8")) if trace_path.exists() else None
        answer = raw["text"]
        (run_dir / "answer.md").write_text(answer, encoding="utf-8")
        generation_records.append({"repetition": repetition, "answer": answer,
            "provider_usage": raw["usage"], "elapsed_ms": raw["elapsed_ms"],
            "exit_code": raw["exit_code"], "tool_events": raw["tool_events"],
            "capability_activated": condition == "conceptualize",
            "capability_calls": len(raw["tool_events"]), "context_trace": trace,
            "post_capability_normal_actions": _post_capability_items(raw["events"])})
    # Blind conditions after the complete set has been generated; IDs reveal no condition.
    blind = [(f"answer_{index:03d}", record) for index, record in enumerate(generation_records, 1)]
    blind.reverse()
    for answer_id, record in blind:
        judged = _run_judge(record["answer"], answer_id, fixture=fixture, truth=truth,
                            codex_home=codex_home, timeout=timeout,
                            run_dir=RUNS / "semantic-judges" / condition / answer_id)
        record["blind_evaluation_id"] = answer_id
        record["semantic_evaluation"] = judged["grade"]
        record["evaluator_usage"] = judged["provider_usage"]
        record["evaluator_elapsed_ms"] = judged["elapsed_ms"]
    result = {"benchmark": "v0.9-capability-semantic-v1", "condition": condition,
              "model": GENERATION_MODEL, "reasoning": GENERATION_REASONING,
              "evaluator_model": EVALUATOR_MODEL, "evaluator_reasoning": EVALUATOR_REASONING,
              "evaluator_prompt_sha256": freeze["evaluator_prompt_sha256"],
              "fixture_sha256": freeze["fixture_sha256"], "ground_truth_sha256": freeze["ground_truth_sha256"],
              "history_messages": freeze["history_messages"],
              "history_tokens_cl100k": freeze["history_tokens_cl100k"],
              "repetitions": repetitions,
              "pass_count": sum(row["semantic_evaluation"]["pass"] for row in generation_records),
              "records": generation_records}
    write_new(result_path, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    _write_audit(result, truth)
    if condition == "conceptualize":
        contexts = [row["context_trace"]["context"] for row in generation_records if row.get("context_trace")]
        context_grades = []
        for index, context in enumerate(contexts, 1):
            eval_id = f"context_{index:03d}"
            record = _run_judge(context, eval_id, fixture=fixture, truth=truth,
                                codex_home=codex_home, timeout=timeout,
                                run_dir=RUNS / "semantic-judges" / "context" / eval_id)
            context_grades.append({"evaluation_id": eval_id, "grade": record["grade"],
                                   "provider_usage": record["provider_usage"],
                                   "elapsed_ms": record["elapsed_ms"]})
        context_result = {"benchmark": "v0.9-capability-semantic-v1",
            "fixture_sha256": freeze["fixture_sha256"], "ground_truth_sha256": freeze["ground_truth_sha256"],
            "method": "same blinded evaluator and frozen proposition set applied directly to Working Context",
            "records": context_grades,
            "mean_total_coverage": round(sum(r["grade"]["total_proposition_coverage_percent"] for r in context_grades) / max(1, len(context_grades)), 2)}
        write_new(RESULTS / "v09-context-sufficiency.json",
                  json.dumps(context_result, ensure_ascii=False, indent=2) + "\n")
    return result


def _write_audit(result: dict[str, Any], truth: dict[str, Any]) -> None:
    rows = [f"# Human audit — V0.9 {result['condition']}", "",
            "Blind semantic evaluator decisions are shown verbatim. This artifact does not regrade answers.", ""]
    for record in result["records"]:
        grade = record["semantic_evaluation"]
        by_id = {item["id"]: item for item in grade["propositions"]}
        rows.extend([f"## Run {record['repetition']} ({record['blind_evaluation_id']})", "",
                     f"Pass: **{grade['pass']}**; critical coverage: {grade['critical_proposition_coverage_percent']}%; total coverage: {grade['total_proposition_coverage_percent']}%.", "",
                     "| Proposition | Ground truth | Evaluator status | Answer evidence |", "|---|---|---|---|"])
        for fact in truth["facts"]:
            item = by_id[fact["id"]]
            quote = item["evidence"].replace("|", "\\|").replace("\n", " ")
            rows.append(f"| {fact['id']} | {fact['proposition']} | {item['status']} | {quote} |")
        rows.append("")
    target = RESULTS / f"v09-{result['condition']}-human-audit.md"
    write_new(target, "\n".join(rows))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("freeze", "verify", "self-test", "control", "conceptualize"))
    parser.add_argument("--codex-home", type=Path, default=ROOT / "evaluations" / "runs" / "v05-benchmark-codex-home")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--timeout", type=int, default=240)
    args = parser.parse_args()
    if args.action == "freeze":
        result = create_frozen_fixture()
    elif args.action == "verify":
        result = verify_freeze()[2]
    elif args.action == "self-test":
        result = run_evaluator_self_tests(codex_home=args.codex_home, timeout=args.timeout)
    else:
        result = run_generation_condition(args.action, repetitions=args.repetitions,
                                          codex_home=args.codex_home, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

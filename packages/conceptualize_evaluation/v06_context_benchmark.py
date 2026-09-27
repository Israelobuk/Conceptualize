"""Run deterministic V0.6 context, continuation, and redundancy fixtures."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from time import perf_counter

from conceptualize_runtime.adapters import ConversationAdapter
from conceptualize_runtime.context import ContextUnit, ContextUnitRuntime
from conceptualize_runtime.runtime import token_count

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "evaluations" / "v06" / "fixtures.json"
RESULT = ROOT / "evaluations" / "results" / "v06-context-engine.json"


def _units(fixture: dict) -> list[ContextUnit]:
    if fixture["kind"] in {"repository"}:
        return [ContextUnit(**item) for item in fixture["files"]]
    return ConversationAdapter().ingest({
        "conversations": [{"id": fixture["id"], "title": fixture["category"], "messages": fixture.get("messages", [])}]
    })


def run(fixture_set: dict) -> dict:
    rows = []
    session_deliveries: list[dict] = []
    previous_context = ""
    for fixture in fixture_set["fixtures"]:
        runtime = ContextUnitRuntime(_units(fixture))
        source_types = {"repository_file"} if fixture["kind"] == "repository" else {"message"}
        targets = ["contracts/payment.py"] if fixture["kind"] == "repository" else []
        history = session_deliveries if fixture["kind"] == "topic" else []
        if fixture["kind"] == "session":
            first = runtime.pack(
                "SQLite offline drafts upload confirmation", fixture_set["token_budget"],
                source_types=source_types,
            )
            previous_context = first["context"]
            session_deliveries = first["deliveries"]
            history = session_deliveries
        started = perf_counter()
        result = runtime.pack(
            fixture["query"], fixture_set["token_budget"], source_types=source_types,
            targets=targets, history=history,
        )
        elapsed_ms = round((perf_counter() - started) * 1000, 3)
        context = result["context"]
        selected = [row for row in result["selection"] if row["status"] == "selected"]
        required = fixture.get("required_facts", fixture.get("required_files", []))
        surfaced = fixture.get("required_files", [])
        if surfaced:
            selected_ids = "\n".join(row["source_id"] for row in selected)
            required_available = [path in selected_ids for path in required]
        elif fixture["kind"] == "session":
            combined = previous_context + "\n" + context
            required_available = [fact.casefold() in combined.casefold() for fact in required]
        else:
            required_available = [fact.casefold() in context.casefold() for fact in required]
        excluded = fixture.get("irrelevant_markers", []) + fixture.get("excluded_markers", [])
        row = {
            "id": fixture["id"], "category": fixture["category"], "query": fixture["query"],
            "success": all(required_available), "required_facts": required,
            "required_fact_selected": required_available,
            "excluded_markers": excluded,
            "excluded_markers_present": [marker for marker in excluded if marker.casefold() in context.casefold()],
            "candidate_units": result["metrics"].get("candidate_units"),
            "selected_units": result["metrics"].get("selected_units"),
            "candidate_tokens": result["metrics"].get("candidate_tokens"),
            "selected_tokens": result["metrics"].get("selected_tokens"),
            "new_context_tokens": result["metrics"].get("new_context_tokens"),
            "duplicate_tokens_suppressed": result["metrics"].get("duplicate_tokens_suppressed"),
            "low_relevance_tokens_suppressed": result["metrics"].get("low_relevance_tokens_suppressed"),
            "unchanged_tokens_avoided": result["metrics"].get("unchanged_context_tokens"),
            "superseded_units_suppressed": result["metrics"].get("superseded_units_suppressed"),
            "relationships_followed": result["metrics"].get("relationships_followed"),
            "sources_represented": result["metrics"].get("sources_represented"),
            "budget_utilization": result["metrics"].get("budget_utilization"),
            "elapsed_ms": elapsed_ms,
            "selection": result["selection"], "context": context,
        }
        if fixture["kind"] == "conversation":
            selected_messages = [u for u in runtime.units if u.source_id in {s["source_id"] for s in selected}]
            session_deliveries = result["deliveries"]
            row["redundancy_diagnostic"] = {
                "duplicate_tokens_suppressed": result["metrics"].get("duplicate_tokens_suppressed", 0),
                "source_messages_preserved": len([u for u in runtime.units if u.source_type == "message"]),
                "selected_messages": len(selected_messages),
                "suppressed_duplicate_items": [
                    {"source_id": item["source_id"], "duplicate_of": item.get("duplicate_of"),
                     "omission_reason": item.get("omission_reason")}
                    for item in result["selection"] if item.get("duplicate_of")
                ],
            }
        elif fixture["kind"] == "session":
            row["previous_call_context_tokens"] = token_count(previous_context)
            row["followup_context_tokens"] = token_count(context)
            row["delta_is_smaller"] = token_count(context) < token_count(previous_context)
            row["previous_context"] = result.get("previous_context", [])
            row["first_call_candidate_tokens"] = first["metrics"].get("candidate_tokens")
            row["first_call_new_context_tokens"] = first["metrics"].get("new_context_tokens")
        elif fixture["kind"] == "topic":
            row["topic_shift_context_is_relevant"] = all(term.casefold() in context.casefold() for term in required)
        elif fixture["kind"] == "negative":
            row["minimal_context"] = not context.strip()
        rows.append(row)
        if fixture["kind"] == "session":
            previous_context = context
        if fixture["kind"] == "topic":
            session_deliveries = result["deliveries"]

    return {
        "benchmark": "Conceptualize V0.6 deterministic context engine",
        "fixture_version": fixture_set["version"], "run_type": "runtime only; no AI model invoked",
        "tokenizer": "cl100k_base estimate", "token_budget": fixture_set["token_budget"],
        "tasks": rows,
        "aggregate": {
            "tasks": len(rows), "passed_required_fact_or_file_checks": sum(r["success"] for r in rows),
            "all_required_context_surfaced": all(r["success"] for r in rows),
            "total_candidate_tokens": sum(r["candidate_tokens"] or 0 for r in rows),
            "total_selected_tokens": sum(r["selected_tokens"] or 0 for r in rows),
            "duplicate_tokens_suppressed": sum(r["duplicate_tokens_suppressed"] or 0 for r in rows),
            "superseded_units_suppressed": sum(r["superseded_units_suppressed"] or 0 for r in rows),
            "context_delta_smaller": next((r["delta_is_smaller"] for r in rows if r["id"] == "session-continuation"), None),
            "negative_control_minimal": next((r["minimal_context"] for r in rows if r["id"] == "negative-control"), None),
        },
        "limitations": ["Synthetic deterministic fixtures measure retrieval behavior, not model-answer correctness.",
                        "Token figures count compiled context strings and do not include MCP or host prompt framing."],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--output", type=Path, default=RESULT)
    args = parser.parse_args()
    report = run(json.loads(args.fixture.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["aggregate"], indent=2))


if __name__ == "__main__":
    main()

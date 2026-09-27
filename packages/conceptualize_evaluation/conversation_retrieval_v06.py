"""Compare complete-task and reduced agent-generated queries on the frozen history."""

import argparse
import json
from pathlib import Path
from time import perf_counter

from conceptualize_runtime.adapters import ConversationAdapter
from conceptualize_runtime.context import ContextUnitRuntime
from conceptualize_runtime.runtime import token_count

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "evaluations" / "v05-conversation-problem.json"
OUTPUT = ROOT / "evaluations" / "results" / "v06-conversation-retrieval.json"
AGENT_QUERY = (
    "Retrieve supplied project history needed to summarize current implementation plan: "
    "final architecture, constraints to preserve, superseded decisions, next implementation step."
)


def run(fixture: dict) -> dict:
    units = ConversationAdapter().ingest({"conversations": [{
        "id": fixture["history_id"], "title": fixture["title"], "messages": fixture["history"]
    }]})
    full_history = "\n\n".join(message["content"] for message in fixture["history"])
    reports = []
    for name, query in (("complete_task", fixture["question"]), ("observed_agent_query", AGENT_QUERY)):
        started = perf_counter()
        packed = ContextUnitRuntime(units).pack(
            query, fixture["settings"]["token_budget"], source_types={"message"}
        )
        elapsed = round((perf_counter() - started) * 1000, 3)
        text = packed["context"].casefold()
        required = fixture["grading"]["required_facts"] + fixture["grading"]["required_constraints"]
        fact_results = [
            {"id": fact["id"], "available": all(term.casefold() in text for term in fact["terms"])}
            for fact in required
        ]
        selected_ids = {row["source_id"] for row in packed["selection"] if row["status"] == "selected"}
        irrelevant = [
            message["id"] for message in fixture["history"]
            if any(marker.casefold() in message["content"].casefold() for marker in fixture["grading"]["unrelated_noise"])
            and message["id"] in selected_ids
        ]
        reports.append({
            "query_kind": name, "query": query,
            "candidate_units": packed["metrics"]["candidate_units"],
            "selected_units": packed["metrics"]["selected_units"],
            "candidate_tokens": packed["metrics"]["candidate_tokens"],
            "selected_context_tokens": packed["metrics"]["new_context_tokens"],
            "full_history_tokens": token_count(full_history),
            "duplicate_tokens_suppressed": packed["metrics"]["duplicate_tokens_suppressed"],
            "low_relevance_tokens_suppressed": packed["metrics"].get("low_relevance_tokens_suppressed", 0),
            "superseded_units_suppressed": packed["metrics"]["superseded_units_suppressed"],
            "required_facts_available": sum(item["available"] for item in fact_results),
            "required_facts_total": len(fact_results),
            "fact_coverage_percent": round(100 * sum(item["available"] for item in fact_results) / len(fact_results), 2),
            "fact_results": fact_results, "known_irrelevant_messages_selected": irrelevant,
            "elapsed_ms": elapsed,
            "selection": packed["selection"], "context": packed["context"],
        })
    return {
        "benchmark": "V0.6 conversation retrieval query fidelity diagnostic",
        "fixture_version": fixture["version"], "history_messages": len(fixture["history"]),
        "token_budget": fixture["settings"]["token_budget"], "tokenizer": "cl100k_base estimate",
        "queries": reports,
        "diagnostic": "The autonomous run's model-generated query omits some entities from the complete user task. Differences in context selection between these two cases isolate that query-information loss; they are not model-answer quality results.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=FIXTURE)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    result = run(json.loads(args.fixture.read_text(encoding="utf-8")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps([
        {key: row[key] for key in ("query_kind", "candidate_units", "selected_units", "full_history_tokens", "selected_context_tokens", "fact_coverage_percent", "known_irrelevant_messages_selected")}
        for row in result["queries"]
    ], indent=2))


if __name__ == "__main__":
    main()

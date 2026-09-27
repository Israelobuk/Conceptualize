import json
from pathlib import Path

from conceptualize_evaluation.conversation_agent_benchmark import QUESTION, grade

FIXTURE = Path(__file__).resolve().parents[1] / "evaluations" / "v05-conversation-problem.json"


def test_frozen_problem_has_exact_question_and_separated_history():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    assert fixture["question"] == QUESTION
    assert len(fixture["history"]) >= 30
    text = "\n".join(message["content"] for message in fixture["history"]).lower()
    assert "supersede my localstorage proposal" in text
    assert "authenticated upload succeeds" in text
    assert "north region" in text
    assert fixture["grading"]["created_before_runs"] is True


def test_deterministic_grader_rejects_missing_constraint_and_stale_choice():
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    complete = """PWA over HTTPS JSON API. LocalStore uses IndexedDB inspection records and filesystem when available with IndexedDB blob fallback adapter contract. SyncEngine resumable and idempotent UUID with version conflict and exponential backoff for transient errors. Next attachment adapter fallback tests. Keep local until authenticated upload, preserve draft conflict, no websocket, screen reader status, plain text. Exclude analytics admin push background. localStorage superseded."""
    assert grade(complete, fixture)["deterministic_pass"]
    assert not grade(complete.replace("no websocket", "websocket push"), fixture)["deterministic_pass"]
    assert not grade(complete.replace("localStorage superseded", "use localStorage as the production store"), fixture)["deterministic_pass"]

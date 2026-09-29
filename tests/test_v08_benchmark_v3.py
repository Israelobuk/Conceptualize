"""Pre-run tests for the v3 semantic-slot rubric; no model answers are used."""

from __future__ import annotations

import pytest
from conceptualize_evaluation.v08_benchmark_v3 import HEADINGS, _ground_truth, grade


def _single(fact: dict, phrase: str) -> str:
    return f"{fact['section_any'][0]}\n{phrase}"


@pytest.mark.parametrize("fact", _ground_truth()["facts"], ids=lambda fact: fact["id"])
def test_canonical_proposition_passes_its_fact_check(fact: dict) -> None:
    result = grade(_single(fact, fact["canonical"]), _ground_truth())
    item = next(check for check in result["propositions"] if check["id"] == fact["id"])
    assert item["present"]


@pytest.mark.parametrize("fact", _ground_truth()["facts"], ids=lambda fact: fact["id"])
def test_predeclared_paraphrase_passes_its_fact_check(fact: dict) -> None:
    result = grade(_single(fact, fact["paraphrase"]), _ground_truth())
    item = next(check for check in result["propositions"] if check["id"] == fact["id"])
    assert item["present"]


@pytest.mark.parametrize("fact", _ground_truth()["facts"], ids=lambda fact: fact["id"])
def test_irrelevant_sentence_does_not_pass_a_fact(fact: dict) -> None:
    result = grade(_single(fact, "The team discussed a separate project concern."), _ground_truth())
    item = next(check for check in result["propositions"] if check["id"] == fact["id"])
    assert not item["present"]


@pytest.mark.parametrize(
    "fact", [fact for fact in _ground_truth()["facts"] if fact["contradictions"]],
    ids=lambda fact: fact["id"],
)
def test_explicit_contradiction_cancels_fact(fact: dict) -> None:
    result = grade(_single(fact, fact["canonical"] + " " + fact["contradictions"][0]), _ground_truth())
    item = next(check for check in result["propositions"] if check["id"] == fact["id"])
    assert item["contradicted"]
    assert not item["present"]


def test_authoritative_current_decision_is_not_flagged_stale() -> None:
    text = "SUPERSEDED DECISIONS\nLocalStorage is an old approach, not part of today's plan."
    result = grade(text, _ground_truth())
    assert result["stale_current_claims"] == []


def test_localstorage_claimed_as_current_is_stale() -> None:
    text = "CURRENT DECISIONS\nLocalStorage remains the current proposal."
    result = grade(text, _ground_truth())
    assert "STALE_01" in result["stale_current_claims"]
    assert not result["passed"]


def test_negated_early_cleanup_is_not_flagged_as_stale() -> None:
    text = "CONSTRAINTS\nDo not delete local data before server acknowledgement."
    result = grade(text, _ground_truth())
    assert "STALE_02" not in result["stale_current_claims"]


def test_required_output_sections_are_the_user_requested_sections() -> None:
    assert len(HEADINGS) == 6
    assert HEADINGS[-1] == "NEXT STEP"

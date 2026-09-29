"""Adversarial tests for V4 whole-answer proposition grading; run before model evaluation."""

from __future__ import annotations

import pytest
from conceptualize_evaluation.v08_benchmark_v4 import _ground_truth, grade


def _one(fact: dict, text: str, heading: str | None = None) -> dict:
    heading = heading or fact.get("diagnostic_heading", "CURRENT ARCHITECTURE")
    return grade(f"{heading}\n{text}", _ground_truth())


def _row(result: dict, fact_id: str) -> dict:
    return next(item for item in result["propositions"] if item["id"] == fact_id)


@pytest.mark.parametrize("fact", _ground_truth()["facts"], ids=lambda fact: fact["id"])
def test_canonical_wording_is_recognized_anywhere(fact: dict) -> None:
    assert _row(_one(fact, fact["canonical"]), fact["id"])["present"]


@pytest.mark.parametrize("fact", _ground_truth()["facts"], ids=lambda fact: fact["id"])
def test_predeclared_paraphrase_is_recognized(fact: dict) -> None:
    assert _row(_one(fact, fact["paraphrase"], "CURRENT STATE"), fact["id"])["present"]


@pytest.mark.parametrize("fact", _ground_truth()["facts"], ids=lambda fact: fact["id"])
def test_fact_is_credited_under_a_different_heading(fact: dict) -> None:
    heading = "NEXT STEP" if fact["id"] == "DEC_01" else "CONSTRAINTS"
    phrase = fact.get("next_step_paraphrase", fact["canonical"])
    assert _row(_one(fact, phrase, heading), fact["id"])["present"]


@pytest.mark.parametrize(
    ("fact_id", "reordered"),
    [
        ("ARCH_01", "When supported, filesystem storage is the preferred option."),
        ("ARCH_02", "Fallback attachment blobs are stored in IndexedDB."),
        ("DEC_01", "Read, write, and delete use one adapter contract shared across both backends."),
        ("CON_01", "The server must acknowledge an authenticated upload before local attachment data is removed."),
        ("OLD_01", "Superseded is the former LocalStorage-only proposal; it is not current."),
        ("STATE_01", "Incomplete remain the shared contract tests and production attachment adapters."),
        ("NEXT_01", "Only after fallback, reload persistence, acknowledgement-safe cleanup, and adapter tests are complete should SyncEngine integration happen."),
    ],
)
def test_word_order_variation_is_recognized(fact_id: str, reordered: str) -> None:
    fact = next(row for row in _ground_truth()["facts"] if row["id"] == fact_id)
    assert _row(_one(fact, reordered), fact_id)["present"]


@pytest.mark.parametrize("fact", [f for f in _ground_truth()["facts"] if f["negations"]], ids=lambda f: f["id"])
def test_negated_or_contradictory_claim_does_not_get_credit(fact: dict) -> None:
    result = _one(fact, fact["canonical"] + ". " + fact["negations"][0])
    assert not _row(result, fact["id"])["present"]


@pytest.mark.parametrize("fact", [f for f in _ground_truth()["facts"] if f["kind"] in {"current", "current_design"}], ids=lambda f: f["id"])
def test_superseded_current_fact_is_not_credited(fact: dict) -> None:
    answer = "SUPERSEDED DECISIONS\n" + fact["canonical"] + " This is obsolete and no longer current."
    assert not _row(grade(answer, _ground_truth()), fact["id"])["present"]


@pytest.mark.parametrize("fact", [f for f in _ground_truth()["facts"] if f["kind"] in {"current", "current_design"}], ids=lambda f: f["id"])
def test_future_only_version_does_not_satisfy_current_fact(fact: dict) -> None:
    answer = "NEXT STEP\nWe may eventually adopt this idea: " + fact["canonical"]
    assert not _row(grade(answer, _ground_truth()), fact["id"])["present"]


@pytest.mark.parametrize("fact", _ground_truth()["facts"], ids=lambda fact: fact["id"])
def test_irrelevant_distant_keyword_match_does_not_get_credit(fact: dict) -> None:
    far_apart = " unrelated detail " * 40
    fragments = [" ".join(group[0]) for group in fact["slots"]]
    text = far_apart.join(fragments)
    assert not _row(_one(fact, text), fact["id"])["present"]


@pytest.mark.parametrize("fact", _ground_truth()["facts"], ids=lambda fact: fact["id"])
def test_explicit_contradiction_cancels_fact(fact: dict) -> None:
    contradiction = fact["contradictions"][0]
    result = _one(fact, fact["canonical"] + ". " + contradiction)
    assert not _row(result, fact["id"])["present"]


def test_known_v3_failure_counts_contract_when_stated_as_next_work() -> None:
    truth = _ground_truth()
    answer = (
        "NEXT STEP\nImplement attachment backend selection and the shared write/read/delete contract. "
        "Test both backends for reload persistence, permission fallback, and acknowledgement-gated cleanup; "
        "then connect the adapter to SyncEngine."
    )
    result = grade(answer, truth)
    assert _row(result, "DEC_01")["present"]
    assert _row(result, "DEC_01")["matched_section"] == "NEXT STEP"


def test_future_only_shared_contract_under_next_step_is_not_current_design() -> None:
    result = grade(
        "NEXT STEP\nWe may eventually consider a shared read/write/delete contract for both backends.",
        _ground_truth(),
    )
    assert not _row(result, "DEC_01")["present"]


def test_localstorage_historical_description_is_not_stale_current_claim() -> None:
    result = grade(
        "SUPERSEDED DECISIONS\nThe LocalStorage proposal is historical and not current.",
        _ground_truth(),
    )
    assert result["stale_current_claims"] == []


def test_localstorage_asserted_as_current_is_prohibited() -> None:
    result = grade("CURRENT DECISIONS\nLocalStorage remains the current production backend.", _ground_truth())
    assert "STALE_01" in result["stale_current_claims"]

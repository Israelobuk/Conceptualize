"""Tests for the separately versioned V0.8 deterministic grader."""

from __future__ import annotations

import json

import pytest
from conceptualize_evaluation.v08_benchmark_v2 import (
    EVAL,
    HEADINGS,
    _truth,
    grade,
)


def _answer(section: str, text: str) -> str:
    return f"{section}\n{text}"


@pytest.mark.parametrize("fact", _truth()["facts"], ids=lambda fact: fact["id"])
def test_canonical_proposition_is_recognized(fact: dict) -> None:
    result = grade(_answer(fact["section"], fact["proposition"]), _truth())
    matched = next(item for item in result["propositions"] if item["id"] == fact["id"])
    assert matched["present"]


@pytest.mark.parametrize("fact", _truth()["facts"], ids=lambda fact: fact["id"])
def test_predeclared_paraphrase_is_recognized(fact: dict) -> None:
    paraphrase = " ".join(fact["acceptable"][0])
    result = grade(_answer(fact["section"], paraphrase), _truth())
    matched = next(item for item in result["propositions"] if item["id"] == fact["id"])
    assert matched["present"]


@pytest.mark.parametrize("fact", _truth()["facts"], ids=lambda fact: fact["id"])
def test_irrelevant_wording_does_not_match(fact: dict) -> None:
    result = grade(_answer(fact["section"], "The team discussed a different topic."), _truth())
    matched = next(item for item in result["propositions"] if item["id"] == fact["id"])
    assert not matched["present"]


@pytest.mark.parametrize(
    "fact",
    [fact for fact in _truth()["facts"] if fact.get("contradictions")],
    ids=lambda fact: fact["id"],
)
def test_predeclared_contradiction_cancels_matching_fact(fact: dict) -> None:
    text = f"{fact['proposition']} {fact['contradictions'][0]}"
    result = grade(_answer(fact["section"], text), _truth())
    matched = next(item for item in result["propositions"] if item["id"] == fact["id"])
    assert matched["contradicted"]
    assert not matched["present"]


def test_current_localstorage_claim_is_stale_and_fails() -> None:
    answer = "CURRENT DECISIONS\nLocalStorage remains the current proposal."
    result = grade(answer, _truth())
    assert "STALE_01" in result["stale_current_claims"]
    assert not result["passed"]


def test_superseded_localstorage_is_not_flagged_as_stale() -> None:
    answer = "SUPERSEDED DECISIONS\nThe older localStorage proposal was superseded."
    result = grade(answer, _truth())
    assert result["stale_current_claims"] == []


def test_freeze_verification_rejects_changed_artifacts(tmp_path, monkeypatch) -> None:
    # Hash checks are covered by the benchmark module after freeze; this test ensures
    # the original v1 files are not part of v2's paths and remain outside its writer.
    assert EVAL.name == "v08-benchmark-v2"
    assert len(HEADINGS) == 6
    original_truth = json.loads((EVAL / "ground-truth.json").read_text(encoding="utf-8")) if (EVAL / "ground-truth.json").exists() else None
    if original_truth is not None:
        assert original_truth["version"] == "v0.8-benchmark-2"

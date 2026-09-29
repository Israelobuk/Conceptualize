import hashlib
import json
from pathlib import Path

import pytest
from conceptualize_evaluation import v08_economics


def test_v08_fixture_truth_and_rubric_are_frozen_and_separate_from_v07():
    fixture, truth, freeze = v08_economics.verify_freeze()
    root = Path(__file__).resolve().parents[1]
    v07_fixture = json.loads((root / "evaluations/v07/fixture.json").read_text(encoding="utf-8"))

    assert fixture["version"] == truth["version"] == freeze["fixture_version"]
    assert len(fixture["history"]) >= 80
    assert fixture["question"] == freeze["question"]
    assert fixture["question"] != v07_fixture["question"]
    assert freeze["fixture_sha256"] == hashlib.sha256(
        (root / "evaluations/v08/fixture.json").read_bytes()
    ).hexdigest()
    assert freeze["ground_truth_sha256"] == hashlib.sha256(
        (root / "evaluations/v08/ground-truth.json").read_bytes()
    ).hexdigest()


def test_v08_activation_changes_only_the_capability_activation_prefix():
    fixture, _, _ = v08_economics.verify_freeze()
    control = v08_economics.prompt_for("A", fixture, history="prior work")
    activated = v08_economics.prompt_for("B", fixture)
    task = fixture["question"]

    assert f"CURRENT USER TASK:\n{task}" in control
    assert f"@Conceptualize\n{task}" in activated
    assert control.split("CURRENT USER TASK:\n", 1)[1] == activated.split(
        "@Conceptualize\n", 1
    )[1]
    assert "conceptualize_context" not in activated
    assert "token budget" not in activated.casefold()


def test_v08_grader_uses_frozen_facts_and_rejects_stale_storage_as_current():
    _, truth, _ = v08_economics.verify_freeze()
    answer = """
    CURRENT STORAGE
    Use the File System Access API when supported; otherwise store attachment blobs in IndexedDB.
    Keep one read/write/delete adapter contract. The local copy stays until authenticated upload
    acknowledgement. The old localStorage proposal is superseded. Attachments remain unfinished.
    NEXT STEP
    Finish backend selection, IndexedDB fallback, persistence and acknowledgement cleanup tests,
    then connect the adapter to SyncEngine.
    """

    grade = v08_economics.grade(answer, truth)

    assert grade["passed"] is True
    assert grade["critical_facts_missing"] == []
    assert grade["stale_claims_in_current_sections"] == []


def test_v08_grader_flags_a_stale_localstorage_current_claim():
    _, truth, _ = v08_economics.verify_freeze()
    grade = v08_economics.grade(
        "CURRENT STORAGE\nUse localStorage as the production attachment store.", truth
    )

    assert grade["passed"] is False
    assert "localstorage_is_current" in grade["stale_claims_in_current_sections"]


def test_evaluation_mcp_surface_uses_the_product_capability_schema():
    from conceptualize_evaluation.v08_mcp_fixture_server import mcp

    tools = mcp._tool_manager.list_tools()

    assert len(tools) == 1
    assert tools[0].name == "conceptualize_context"
    assert tools[0].parameters["properties"].keys() == {"task"}
    assert "context capability" in tools[0].description.casefold()


def test_result_writer_preserves_existing_evaluation_evidence(tmp_path):
    target = tmp_path / "mode-a.json"
    target.write_text('{"original":true}\n', encoding="utf-8")

    with pytest.raises(FileExistsError, match="refusing to overwrite"):
        v08_economics.persist_summary(target, {"replacement": True})

    assert json.loads(target.read_text(encoding="utf-8")) == {"original": True}

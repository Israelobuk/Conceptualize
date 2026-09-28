from conceptualize_evaluation.v07_economics import _verify_freeze, grade

GOOD_ANSWER = """
## CURRENT ARCHITECTURE
The Atlas browser PWA uses the existing HTTPS JSON API. LocalStore persists inspection
records in IndexedDB. The attachment adapter uses filesystem storage where supported and
falls back to IndexedDB blobs through the same read/write/delete contract. SyncEngine is
resumable; client UUIDs make replay idempotent, and version checks reject stale updates.

## CURRENT CONSTRAINTS
Keep photos and drafts local until authenticated upload is acknowledged; retain drafts for
conflict review. Use exponential backoff with jitter for transient failures, not validation
errors. V1 fields are plain text and offline status is accessible to screen readers. Sync is
client-triggered on app launch, pull to refresh, and local edits; no websocket or background
periodic sync is needed. Do not add the analytics dashboard or push notifications.

## SUPERSEDED DECISIONS
The localStorage proposal was replaced by IndexedDB. The native desktop proposal was replaced
by the browser PWA. Filesystem-only attachment storage was updated to use an IndexedDB blob
fallback. WebSocket push is not current.

## CURRENT STATE
IndexedDB record persistence can save and restore drafts. SyncEngine metadata sync with UUID
idempotency and version conflict handling is implemented. End-to-end attachments are unfinished.

## NEXT STEP
Implement the shared attachment adapter for filesystem and IndexedDB fallback, then add
read/write/delete contract and fallback tests before wiring it into SyncEngine.
"""


def test_v07_frozen_truth_and_fixture_are_hashed_before_runs():
    fixture, truth, freeze = _verify_freeze()
    assert fixture["version"] == "v0.7-context-economics-atlas-9"
    assert truth["created_before_model_runs"] is True
    assert freeze["history_tokens_cl100k"] >= 8000
    assert freeze["model_runs_started"] is False


def test_proposition_grader_accepts_paraphrase_and_structured_sections():
    fixture, truth, _ = _verify_freeze()
    result = grade(GOOD_ANSWER, truth)
    assert result["required_headings_parsed"]
    assert result["critical_facts_missing"] == []
    assert result["stale_claims_in_current_sections"] == []
    assert result["fact_coverage_percent"] >= truth["pass_rule"]["minimum_overall_coverage_percent"]
    assert result["passed"]


def test_proposition_grader_accepts_facts_under_another_requested_heading():
    _, truth, _ = _verify_freeze()
    answer = GOOD_ANSWER.replace(
        "Sync is client-triggered on app launch, pull to refresh, and local edits; no websocket or background periodic sync is needed. ",
        "",
    ).replace(
        "## SUPERSEDED DECISIONS",
        "Sync is client-triggered on app launch, pull to refresh, and local edits; no websocket or background periodic sync is needed.\n\n## SUPERSEDED DECISIONS",
    )
    assert grade(answer, truth)["passed"]


def test_proposition_grader_rejects_missing_critical_fact_or_stale_current_claim():
    _, truth, _ = _verify_freeze()
    missing_next_step = GOOD_ANSWER.replace("then add\nread/write/delete contract and fallback tests before wiring it into SyncEngine.", "later.")
    assert not grade(missing_next_step, truth)["passed"]
    stale = GOOD_ANSWER.replace(
        "The Atlas browser PWA uses the existing HTTPS JSON API.",
        "Use localStorage as the current production record store with the browser PWA.",
    )
    assert "localstorage_is_current" in grade(stale, truth)["stale_claims_in_current_sections"]
    assert not grade(stale, truth)["passed"]

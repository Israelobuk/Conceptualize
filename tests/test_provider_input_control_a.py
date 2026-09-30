"""Request-level accounting checks for the provider-input control harness."""

from evaluations.scripts.run_provider_input_control_a import (
    _api_durations,
    _request_records,
    reconcile,
)


def test_request_usage_reconciles_only_when_every_request_matches_turn_totals() -> None:
    rollout = [
        {"type": "token_usage_record", "timestamp": "2026-09-30T00:00:01Z",
         "payload": {"response_id": "resp_1", "usage": {
             "input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 10}}},
        {"type": "token_usage_record", "timestamp": "2026-09-30T00:00:02Z",
         "payload": {"response_id": "resp_2", "usage": {
             "input_tokens": 150, "cached_input_tokens": 90, "output_tokens": 20}}},
    ]
    records = _request_records(rollout)
    assert [row["request_index"] for row in records] == [1, 2]
    assert [row["uncached_input_tokens"] for row in records] == [60, 60]
    assert reconcile(records, {"input_tokens": 250, "cached_input_tokens": 130,
                               "output_tokens": 30})
    assert not reconcile(records, {"input_tokens": 250, "cached_input_tokens": 130,
                                   "output_tokens": 31})


def test_request_duration_uses_sampling_span_not_other_api_calls() -> None:
    batches = [{"payload": {"resourceSpans": [{"scopeSpans": [{"spans": [
        {"name": "models_lookup", "startTimeUnixNano": "1000000000",
         "endTimeUnixNano": "1800000000"},
        {"name": "run_sampling_request", "startTimeUnixNano": "2000000000",
         "endTimeUnixNano": "3200000000"},
    ]}]}]}}]
    assert _api_durations(batches) == [1200.0]

import json

from conceptualize_mcp.server import compact_response


def test_model_projection_keeps_useful_context_and_stale_ids_but_not_diagnostics():
    rows = [{"path": f"f{n}.py", "status": "omitted", "score": n, "score_reasons": [{"signal": "explicit", "weight": 100}]} for n in range(500)]
    payload = {"operation": "inspect", "context": "SOURCE\ndef price(): return 42", "trace_id": "trace",
        "metrics": {"candidate_tokens": 50000, "returned_tokens": 10, "token_budget": 1000, "new_context_tokens": 10},
        "included_files": ["target.py"], "selection": rows, "structural_selection": rows,
        "files_considered": [f"f{n}.py" for n in range(500)], "timings_ms": {"scoring": 42},
        "environment": {"consumers": ["other.py"]}, "invalidations": [{"context_id": "old", "changed_files": ["target.py"], "potentially_affected_relationships": rows}]}
    result = compact_response(payload)
    assert result["context"] == payload["context"]
    assert result["trace_id"] == "trace"
    assert result["environment"]["consumers"] == ["other.py"]
    assert result["invalidations"][0]["context_id"] == "old"
    assert not ({"selection", "structural_selection", "timings_ms", "files_considered"} & result.keys())
    assert len(json.dumps(result)) < len(json.dumps(payload)) / 10
    assert payload["selection"] == rows

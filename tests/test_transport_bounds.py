import json

from conceptualize_mcp.server import compact_response


def test_compact_metadata_preserves_stale_ids_and_selected_explanations():
    edges = [{"source": f"f{n}.py", "target": "base.py", "kind": "imports"} for n in range(500)]
    selected = {"path": "base.py", "status": "selected", "score_reasons": [{"signal": "explicit", "weight": 100}]}
    payload = {"trace_id": "trace", "selection": [selected] + [
        {"path": f"f{n}.py", "status": "omitted", "score_reasons": []} for n in range(500)],
        "relationships": edges, "invalidations": [
            {"context_id": f"ctx_{n}", "changed_files": ["base.py"], "potentially_affected_relationships": edges}
            for n in range(100)]}
    result = compact_response(payload)
    assert len(json.dumps(result)) < 50000
    assert result["selection"][0]["score_reasons"] == selected["score_reasons"]
    assert [x["context_id"] for x in result["invalidations"]] == [f"ctx_{n}" for n in range(100)]
    assert result["metadata_counts"]["relationships"] == 500
    assert result["metadata_counts"]["omitted_candidates"] == 500
    assert len(payload["relationships"]) == 500

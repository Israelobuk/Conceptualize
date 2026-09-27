from conceptualize_evaluation.protocol_benchmark import make_scale, stage_statistics


def test_scale_fixture_has_known_consumers_at_requested_size(tmp_path):
    make_scale(tmp_path / "repo", 60)
    assert len(list((tmp_path / "repo").rglob("*.py"))) == 60
    assert "receipt.total" in (tmp_path / "repo/consumers/c0000.py").read_text()


def test_stage_statistics_do_not_fill_missing_transport_with_zero():
    data = stage_statistics([{"overhead": {"graph_ms": 1, "transport_ms": None}}, {"overhead": {"graph_ms": 9}}])
    assert data["graph_ms"] == {"count": 2, "p50": 1, "p95": 9, "missing": 0}
    assert data["transport_ms"] == {"count": 0, "p50": None, "p95": None, "missing": 2}

from conceptualize_evaluation.runner import event_metrics, prepare


def test_paired_runs_have_identical_baselines(tmp_path):
    a = prepare("receipts", "control", tmp_path / "control")
    b = prepare("receipts", "conceptualize", tmp_path / "conceptualize")
    assert a["baseline"] == b["baseline"]
    assert a["prompt_sha256"] == b["prompt_sha256"]
    assert (tmp_path / "control" / "repository" / "shop" / "checkout.py").read_bytes() == (
        tmp_path / "conceptualize" / "repository" / "shop" / "checkout.py"
    ).read_bytes()


def test_events_do_not_invent_unexposed_metrics():
    result = event_metrics(
        [
            {
                "type": "item.completed",
                "item": {"type": "command_execution", "command": "rg Receipt shop", "exit_code": 0},
            },
            {
                "type": "turn.completed",
                "usage": {"input_tokens": 20, "output_tokens": 10, "cached_input_tokens": 5},
            },
        ]
    )
    assert result["command_executions"] == 1
    assert result["agent_usage"]["input_tokens"] == 20
    assert result["files_inspected"] is None
    assert result["unnecessary_repository_reads"] is None
    assert result["corrective_iterations"] is None


def test_comparison_rejects_different_baseline(tmp_path):
    import json

    import pytest
    from conceptualize_evaluation.runner import compare

    left = {
        "baseline": "a",
        "prompt_sha256": "p",
        "task": "receipts",
        "model": "same",
        "agent_version": "v",
        "mode": "control",
    }
    right = {**left, "baseline": "b", "mode": "conceptualize"}
    a = tmp_path / "a.json"
    b = tmp_path / "b.json"
    a.write_text(json.dumps(left), encoding="utf-8")
    b.write_text(json.dumps(right), encoding="utf-8")
    with pytest.raises(ValueError, match="Runs differ"):
        compare(a, b)


def test_utf8_agent_evidence_survives_assessment(tmp_path):
    from conceptualize_evaluation.runner import assess

    run_dir = tmp_path / "run"
    prepare("receipts", "control", run_dir)
    (run_dir / "agent-events.jsonl").write_text(
        '{"type":"item.completed","item":{"type":"agent_message","text":"日本語 → evidence"}}\n',
        encoding="utf-8",
    )
    result = assess(run_dir, 0, 1.0, None, [], "same")
    assert result["agent_final_message"] == "日本語 → evidence"
    assert result["tests_passed"] is False


def test_assessment_timeout_preserves_a_failed_result(tmp_path, monkeypatch):
    import subprocess
    import sys

    from conceptualize_evaluation import runner

    run_dir = tmp_path / "run"
    prepare("receipts", "control", run_dir)
    original = subprocess.run

    def run(args, *pos, **kwargs):
        if args[:3] == [sys.executable, "-m", "pytest"]:
            raise subprocess.TimeoutExpired(args, 120, output=b"partial checks")
        return original(args, *pos, **kwargs)

    monkeypatch.setattr(runner.subprocess, "run", run)
    result = runner.assess(run_dir, 124, 600, None, [], "same")
    assert result["tests_timed_out"] and not result["task_completion"]
    assert result["failure_signals"]["agent_timeout"]
    assert "partial checks" in (run_dir / "tests.txt").read_text(encoding="utf-8")


def test_ten_task_suite_does_not_invent_missing_runs(tmp_path):
    from conceptualize_evaluation.suite import report

    result = report(tmp_path)
    assert len(result["missing_tasks"]) == 10
    assert result["rows"] == []
    assert result["aggregate"]["control"]["median_seconds"] is None

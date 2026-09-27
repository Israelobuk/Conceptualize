import json

from conceptualize_evaluation.conversation_benchmark import FIXTURE, run


def test_fixture_is_short_and_runtime_selection_preserves_all_checked_facts():
    report = run(json.loads(FIXTURE.read_text(encoding="utf-8")))

    assert report["run_type"] == "runtime-only diagnostic; no host AI model was invoked"
    assert report["aggregate"]["tasks"] == 4
    assert report["aggregate"]["control_passes"] == 4
    assert report["aggregate"]["conceptualize_fact_coverage_passes"] == 4
    assert report["aggregate"]["model_input_tokens"] is None
    assert report["aggregate"]["estimated_cost"] is None
    assert report["categories"]["effectiveness"]["model_answer_correctness"] is None
    assert report["categories"]["economics"]["estimated_cost_difference"] is None
    assert all(task["conceptualize"]["selection"] for task in report["tasks"])

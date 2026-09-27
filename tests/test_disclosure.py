from conceptualize_runtime.index import parse_file
from conceptualize_runtime.runtime import ContextRuntime


def runtime():
    return ContextRuntime(
        {
            p: parse_file(p, t)
            for p, t in {
                "src/base.py": "def base():\n    return 1\n",
                "src/service.py": "from .base import base\ndef run():\n    return base()\n",
                "tests/check.py": "from src.service import run\ndef test_run():\n    assert run()==1\n",
            }.items()
        }
    )


def test_scores_are_additive_explainable_and_configurable():
    r = runtime().execute(
        "pack",
        {"paths": ["src/service.py"], "token_budget": 2000, "score_weights": {"explicit": 120}},
    )
    for row in r["selection"]:
        assert row["score"] == sum(x["weight"] for x in row["score_reasons"])
        assert row["graph_distance"] is not None
    target = next(x for x in r["selection"] if x["path"] == "src/service.py")
    assert any(x["signal"] == "explicit" and x["weight"] == 120 for x in target["score_reasons"])


def test_structure_has_signatures_not_implementation():
    result = runtime().execute(
        "expand", {"target": "src/service.py", "level": "structure", "token_budget": 1000}
    )
    assert "def run()" in result["context"]
    assert "return base()" not in result["context"]
    assert result["level"] == "structure"


def test_overlapping_explicit_symbols_do_not_duplicate_source():
    engine = ContextRuntime(
        {
            "thing.py": parse_file(
                "thing.py", "class Thing:\n    def work(self):\n        return 42\n"
            )
        }
    )
    result = engine.execute("pack", {"paths": ["Thing", "work"], "token_budget": 1000})
    assert result["context"].count("return 42") == 1


def test_session_delta_preserves_ranges_and_change_invalidation():
    engine = runtime()
    first = engine.execute("expand", {"target": "src/service.py::run", "token_budget": 1000})
    history = [{**u, "trace_id": "first"} for u in first["deliveries"]]
    second = engine.execute(
        "pack", {"paths": ["src/service.py"], "token_budget": 2000, "_history": history}
    )
    assert "return base()" not in second["context"]
    assert second["metrics"]["duplicate_tokens_avoided"] > 0
    assert second["previous_context"][0]["supplied_in_operation"] == "first"
    forced = engine.execute(
        "expand",
        {
            "target": "src/service.py::run",
            "token_budget": 1000,
            "_history": history,
            "force_refresh": True,
        },
    )
    assert "return base()" in forced["context"]
    engine.files["src/service.py"] = parse_file("src/service.py", "def run():\n    return 2\n")
    changed = engine.execute(
        "expand", {"target": "src/service.py::run", "token_budget": 1000, "_history": history}
    )
    assert "return 2" in changed["context"]


def test_repeated_pack_is_reference_only_and_budgeted():
    engine = runtime()
    first = engine.execute("pack", {"paths": ["src/service.py"], "token_budget": 2000})
    second = engine.execute(
        "pack",
        {
            "paths": ["src/service.py"],
            "token_budget": 2000,
            "_history": [{**u, "trace_id": "prior"} for u in first["deliveries"]],
        },
    )
    assert second["context"] == ""
    assert second["previous_context"]
    assert second["metrics"]["new_context_tokens"] == 0
    assert second["metrics"]["full_selected_tokens"] > 0
    assert (
        second["metrics"]["duplicate_tokens_avoided"]
        == second["metrics"]["previously_supplied_tokens"]
    )


def test_truncated_delivery_never_marks_full_file_known():
    engine = ContextRuntime(
        {"large.py": parse_file("large.py", "\n".join(f"value_{i} = {i}" for i in range(300)))}
    )
    small = engine.execute("pack", {"paths": ["large.py"], "token_budget": 50})
    assert small["truncated_files"]
    assert not small["deliveries"]
    full = engine.execute(
        "pack", {"paths": ["large.py"], "token_budget": 8000, "_history": small["deliveries"]}
    )
    assert "value_299" in full["context"]

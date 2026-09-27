from conceptualize_runtime.index import parse_file
from conceptualize_runtime.runtime import ContextRuntime, token_count


def fixture():
    return ContextRuntime(
        {
            p: parse_file(p, text)
            for p, text in {
                "src/base.py": "def base():\n    return 1\n",
                "src/service.py": "from .base import base\ndef run():\n    return base()\n",
                "src/consumer.py": "from .service import run\ndef use():\n    return run()\n",
                "tests/test_service.py": "from src.service import run\ndef test_run():\n    assert run()==1\n",
            }.items()
        }
    )


def test_inspect_manifest_and_bounded_source():
    r = fixture().execute("inspect", {"target": "src/service.py", "depth": 1, "token_budget": 1000})
    assert r["manifest"]["files"] == 4
    assert "src/base.py" in r["environment"]["dependencies"]
    assert "src/consumer.py" in r["environment"]["consumers"]
    assert "tests/test_service.py" in r["environment"]["tests"]
    assert "def run" in r["context"]
    assert token_count(r["context"]) <= 1000
    structural = {row["path"]: row for row in r["structural_selection"]}
    for unit in r["deliveries"]:
        if unit["level"] == "structure":
            assert structural[unit["path"]]["status"] != "omitted"
            assert structural[unit["path"]]["score_reasons"]
    manifest = fixture().execute(
        "inspect", {"target": "run", "manifest_only": True, "token_budget": 100}
    )
    assert "return base()" not in manifest["context"]
    assert manifest["manifest"]["potential_source_tokens"] > 0


def test_inspect_flags_and_fingerprints_survive_session_reuse():
    engine = fixture()
    inputs = {
        "target": "src/service.py",
        "token_budget": 1000,
        "include_consumers": False,
        "include_tests": False,
    }
    first = engine.execute("inspect", inputs)
    assert first["environment"]["consumers"] == []
    assert first["environment"]["tests"] == []
    assert all(u["context_id"].startswith("ctx_") for u in first["deliveries"])
    history = [{**u, "trace_id": "first"} for u in first["deliveries"]]
    second = engine.execute("inspect", {**inputs, "_history": history})
    assert second["metrics"]["duplicate_tokens_avoided"] > 0
    assert second["previous_context"][0]["context_id"]
    engine.files["src/base.py"] = parse_file("src/base.py", "def base():\n    return 2\n")
    engine.__post_init__()
    changed = engine.execute("inspect", {**inputs, "_history": history})
    assert changed["invalidations"]
    assert "src/base.py" in changed["invalidations"][0]["changed_files"]

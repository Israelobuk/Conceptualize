import pytest
from conceptualize_runtime.index import inspect_repository, parse_file
from conceptualize_runtime.runtime import ContextRuntime, token_count
from conceptualize_shared.contracts import ContextResponse
from pydantic import ValidationError


@pytest.mark.parametrize("budget", [1, 10, 30, 100, 500, 1000])
def test_truncation_and_unicode_never_exceed_budget(budget):
    text = "# 日本語 context\n" + "word🌍 " * 3000
    runtime = ContextRuntime({"large.py": parse_file("large.py", text)})
    result = runtime.execute("pack", {"paths": ["large.py"], "token_budget": budget})
    assert token_count(result["context"]) <= budget
    assert set(result["included_files"] + result["omitted_files"]) == {"large.py"}
    if result["included_files"]:
        assert result["truncated_files"] == ["large.py"]
        assert "TRUNCATED" in result["context"]


def test_deleted_files_are_not_returned_after_incremental_index(tmp_path):
    path = tmp_path / "auth.py"
    path.write_text("def login(): pass")
    initial = inspect_repository(tmp_path)
    path.unlink()
    assert inspect_repository(tmp_path, initial) == {}


def test_ignore_rules_do_not_leak_into_sibling_directory(tmp_path):
    for name in ["a", "b"]:
        (tmp_path / name).mkdir()
        (tmp_path / name / "file.py").write_text("value = 1")
    (tmp_path / "a" / ".gitignore").write_text("file.py")
    assert set(inspect_repository(tmp_path)) == {"b/file.py"}


def test_invalid_protocol_response_fails_validation():
    with pytest.raises(ValidationError):
        ContextResponse.model_validate({"context": "fake", "metrics": {"returned_tokens": "20"}})

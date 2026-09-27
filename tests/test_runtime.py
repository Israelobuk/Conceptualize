from conceptualize_runtime.graph import build_graph
from conceptualize_runtime.index import inspect_repository, parse_file
from conceptualize_runtime.runtime import ContextRuntime, token_count


def fixture_index(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "tokens.py").write_text("def verify(token):\n    return token == 'valid'\n")
    (tmp_path / "src" / "session.py").write_text(
        "from .tokens import verify\n\ndef login(token):\n    return verify(token)\n"
    )
    (tmp_path / "tests" / "test_session.py").write_text(
        "from src.session import login\n\ndef test_login():\n    assert login('valid')\n"
    )
    return inspect_repository(tmp_path)


def test_tree_sitter_finds_symbols_and_imports():
    result = parse_file(
        "session.ts",
        'import {verify} from "./tokens";\nexport interface User { id: string }\nexport function login() { return verify(); }',
    )
    assert {s["name"] for s in result["symbols"]} == {"User", "login"}
    assert result["imports"] == ["./tokens"]
    assert result["symbols"][1]["exported"]


def test_graph_resolves_imports_consumers_and_tests(tmp_path):
    files = fixture_index(tmp_path)
    graph = build_graph(files)
    assert graph.has_edge("src/session.py", "src/tokens.py")
    runtime = ContextRuntime(files)
    response = runtime.execute("dependencies", {"target": "src/session.py", "token_budget": 1000})
    assert "src/tokens.py" in response["context"]
    assert "tests/test_session.py" in response["context"]
    assert response["relationships"]


def test_packing_counts_headers_and_reports_omissions(tmp_path):
    files = fixture_index(tmp_path)
    runtime = ContextRuntime(files)
    full = runtime.execute(
        "pack",
        {
            "paths": ["src/session.py"],
            "include_dependencies": True,
            "include_tests": True,
            "token_budget": 2000,
        },
    )
    assert set(full["included_files"]) == set(files)
    small = runtime.execute("pack", {"paths": ["src"], "token_budget": 30})
    assert token_count(small["context"]) == small["metrics"]["returned_tokens"]
    assert small["metrics"]["returned_tokens"] <= 30
    assert small["omitted_files"]
    assert small["metrics"]["candidate_tokens"] >= small["metrics"]["returned_tokens"]


def test_index_excludes_secrets_and_honors_nested_ignore(tmp_path):
    (tmp_path / "ok.py").write_text("def ok(): pass")
    (tmp_path / ".env").write_text("SECRET=abc")
    (tmp_path / "credentials.json").write_text('{"secret": "abc"}')
    (tmp_path / ".gitignore").write_text("ignored.py\n")
    (tmp_path / "ignored.py").write_text("secret")
    (tmp_path / "sub").mkdir()
    (tmp_path / "sub" / ".gitignore").write_text("private.py\n")
    (tmp_path / "sub" / "private.py").write_text("secret")
    (tmp_path / "sub" / "public.py").write_text("public = True")
    assert set(inspect_repository(tmp_path)) == {"ok.py", "sub/public.py"}


def test_incremental_index_reuses_unchanged_parse(tmp_path):
    original = fixture_index(tmp_path)
    updated = inspect_repository(tmp_path, original)
    assert updated["src/session.py"] is original["src/session.py"]
    (tmp_path / "src" / "session.py").write_text("def logout(): pass")
    updated = inspect_repository(tmp_path, original)
    assert updated["src/session.py"]["hash"] != original["src/session.py"]["hash"]
    assert updated["src/session.py"]["symbols"][0]["name"] == "logout"


def test_search_and_expand_use_lexical_metadata(tmp_path):
    runtime = ContextRuntime(fixture_index(tmp_path))
    search = runtime.execute("search", {"query": "login", "token_budget": 1000})
    assert "src/session.py" in search["included_files"]
    expanded = runtime.execute("expand", {"target": "login", "token_budget": 1000})
    assert "def login(token)" in expanded["context"]
    assert expanded["metrics"]["returned_tokens"] <= 1000


def test_path_prefix_does_not_match_unrelated_directory(tmp_path):
    files = fixture_index(tmp_path)
    files["src-other/a.py"] = {**files["src/tokens.py"], "path": "src-other/a.py"}
    result = ContextRuntime(files).execute("map", {"path": "src", "token_budget": 1000})
    assert "src-other/a.py" not in result["included_files"]

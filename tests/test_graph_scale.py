from conceptualize_runtime import graph
from conceptualize_runtime.index import parse_file


def test_filename_test_relationships_do_not_scan_every_source_pair(monkeypatch):
    files = {f"src/m{n}.py": parse_file(f"src/m{n}.py", "def value():\n    return 1\n")
             for n in range(100)}
    files["tests/test_m42.py"] = parse_file("tests/test_m42.py", "def test_value():\n    pass\n")
    original = graph.is_test
    calls = []

    def counting(path, record):
        calls.append(path)
        return original(path, record)

    monkeypatch.setattr(graph, "is_test", counting)
    result = graph.build_graph(files)
    assert result.has_edge("src/m42.py", "tests/test_m42.py")
    assert len(calls) < len(files) * 5

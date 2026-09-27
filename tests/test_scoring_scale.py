from conceptualize_runtime.graph import build_graph
from conceptualize_runtime.index import parse_file
from conceptualize_runtime.scoring import score_candidates


def test_scoring_indexes_relationships_once_without_changing_reasons():
    files = {"base.py": parse_file("base.py", "def value():\n    return 1\n")}
    files.update({f"c{n}.py": parse_file(f"c{n}.py", "from base import value\n") for n in range(100)})
    graph = build_graph(files)
    accesses = []

    class Counted(dict):
        def __getitem__(self, key):
            accesses.append(key)
            return super().__getitem__(key)

    relationships = [Counted(source=f"c{n}.py", target="base.py", kind="imports") for n in range(100)]
    result, _ = score_candidates(files, graph, {"base.py"}, list(files), relationships, {}, [])
    assert any(r["signal"] == "consumer" and r["weight"] == 65 for r in result["c42.py"]["score_reasons"])
    assert len(accesses) < 5000

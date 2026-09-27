import json

from conceptualize_runtime.index import parse_file
from conceptualize_runtime.runtime import ContextRuntime, token_count


def records(source):
    return {p: parse_file(p, text) for p, text in source.items()}


def test_python_submodule_alias_and_symbol_consumers():
    runtime = ContextRuntime(
        records(
            {
                "pkg/__init__.py": "",
                "pkg/contracts.py": "class Receipt:\n    pass\n",
                "pkg/checkout.py": "from . import contracts\nfrom .contracts import Receipt as OrderReceipt\ndef checkout() -> OrderReceipt:\n    return OrderReceipt()\n",
                "tests/test_checkout.py": "from pkg.checkout import checkout\ndef test_checkout():\n    assert checkout()\n",
            }
        )
    )
    result = runtime.execute(
        "dependencies", {"target": "pkg/contracts.py::Receipt", "token_budget": 2000}
    )
    assert "pkg/checkout.py" in result["included_files"]
    assert any(
        r["kind"] == "references_symbol"
        and r["target"].startswith("pkg/contracts.py::Receipt:")
        and not r.get("heuristic")
        for r in result["relationships"]
    )
    assert runtime.graph.has_edge("pkg/checkout.py", "pkg/contracts.py")


def test_ts_config_alias_types_and_import_based_tests():
    runtime = ContextRuntime(
        records(
            {
                "tsconfig.json": json.dumps(
                    {"compilerOptions": {"baseUrl": ".", "paths": {"@/*": ["src/*"]}}}
                ),
                "src/contracts.ts": "export interface Receipt { id: string }",
                "src/checkout.ts": 'import type { Receipt as OrderReceipt } from "@/contracts"; export function checkout(): OrderReceipt { return {id:"ok"}; }',
                "tests/unusual.spec.ts": 'import {checkout} from "../src/checkout"; export function check() { checkout(); }',
            }
        )
    )
    result = runtime.execute("pack", {"paths": ["src/contracts.ts::Receipt"], "token_budget": 4000})
    assert "src/checkout.ts" in result["included_files"]
    assert "tests/unusual.spec.ts" in result["included_files"]
    assert any(r["kind"] == "references_symbol" for r in result["relationships"])


def test_pack_has_ordered_selection_provenance_git_and_nearby():
    files = records(
        {
            "src/base.py": "def value():\n    return 1\n",
            "src/service.py": "from .base import value\ndef run():\n    return value()\n",
            "src/consumer.py": "from .service import run\ndef call():\n    return run()\n",
            "src/near.py": "near = True\n",
            "tests/odd.py": "from src.service import run\ndef test_run():\n    assert run() == 1\n",
            "other/changed.py": "changed = 1\n",
            "other/cochange.py": "paired = 1\n",
        }
    )
    runtime = ContextRuntime(
        files,
        {
            "changed_files": ["other/changed.py"],
            "cochanges": [{"files": ["src/service.py", "other/cochange.py"], "count": 3}],
        },
    )
    result = runtime.execute("pack", {"paths": ["src/service.py"], "token_budget": 2000})
    rows = result["selection"]
    assert [r["path"] for r in rows][:4] == [
        "src/service.py",
        "src/base.py",
        "src/consumer.py",
        "tests/odd.py",
    ]
    assert {"other/changed.py", "other/cochange.py", "src/near.py"} <= set(
        result["files_considered"]
    )
    assert all(
        {"priority", "reason", "relationship", "token_cost", "status"} <= r.keys() for r in rows
    )
    assert rows[0]["priority"] == 0
    assert all(r["status"] == "selected" for r in rows)
    small = runtime.execute("pack", {"paths": ["src/service.py"], "token_budget": 40})
    assert token_count(small["context"]) <= 40
    assert any(r["status"] == "omitted" for r in small["selection"])


def test_exact_symbol_id_and_ambiguous_imports_are_not_guessed():
    runtime = ContextRuntime(
        records(
            {
                "a.py": "def run():\n    pass\n",
                "b.py": "def run():\n    pass\n",
                "consumer.py": "import external\ndef use():\n    return run()\n",
            }
        )
    )
    assert runtime.resolve("a.py::run:1") == ["a.py"]
    result = runtime.execute("dependencies", {"target": "consumer.py", "token_budget": 1000})
    assert not any(r["kind"] == "references_symbol" for r in result["relationships"])


def test_pack_includes_nearby_root_files():
    runtime = ContextRuntime(
        records({"service.py": "def run():\n    pass\n", "helper.py": "value=1\n"})
    )
    result = runtime.execute("pack", {"paths": ["service.py"], "token_budget": 500})
    assert "helper.py" in result["files_considered"]

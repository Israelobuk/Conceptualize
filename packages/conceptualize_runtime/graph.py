import json
import posixpath
import re
import tomllib
from pathlib import PurePosixPath

import networkx as nx


def configuration(files: dict) -> dict:
    roots = {"", "src"}
    for path in files:
        if path.endswith("/__init__.py"):
            parent = str(PurePosixPath(path).parent)
            while parent + "/__init__.py" in files:
                parent = str(PurePosixPath(parent).parent)
            roots.add("" if parent == "." else parent)
    try:
        project = tomllib.loads(files.get("pyproject.toml", {}).get("content", ""))
        roots.update(
            project.get("tool", {})
            .get("setuptools", {})
            .get("packages", {})
            .get("find", {})
            .get("where", [])
        )
    except (ValueError, TypeError):
        pass
    configs = {}
    for path, record in files.items():
        if PurePosixPath(path).name in {"tsconfig.json", "jsconfig.json"}:
            try:
                options = json.loads(record["content"]).get("compilerOptions", {})
                configs[str(PurePosixPath(path).parent)] = options
            except (ValueError, TypeError):
                continue
    return {"roots": sorted(roots), "configs": configs}


def resolve_import(path: str, module: str, files: dict, config: dict | None = None) -> str | None:
    config = config or configuration(files)
    parent = str(PurePosixPath(path).parent)
    if path.endswith(".py"):
        dots = len(module) - len(module.lstrip("."))
        module_path = module.lstrip(".").replace(".", "/")
        bases = (
            [posixpath.join(parent, "../" * max(0, dots - 1), module_path)]
            if dots
            else [posixpath.join(root, module_path) for root in config["roots"]]
        )
        candidates = [base + suffix for base in bases for suffix in (".py", "/__init__.py")]
    else:
        bases = []
        if module.startswith("."):
            bases.append(posixpath.join(parent, module))
        else:
            scopes = sorted(
                (
                    scope
                    for scope in config["configs"]
                    if scope == "." or path.startswith(scope + "/")
                ),
                key=len,
                reverse=True,
            )
            if scopes:
                scope = scopes[0]
                options = config["configs"][scope]
                base = posixpath.join(scope, options.get("baseUrl", "."))
                for alias, destinations in options.get("paths", {}).items():
                    pattern = "^" + re.escape(alias).replace(r"\*", "(.*)") + "$"
                    match = re.match(pattern, module)
                    if match and isinstance(destinations, list):
                        bases.extend(
                            posixpath.join(
                                base, dest.replace("*", match.group(1) if match.groups() else "")
                            )
                            for dest in destinations
                        )
                if "baseUrl" in options:
                    bases.append(posixpath.join(base, module))
        candidates = []
        for base in bases:
            candidates += [base] + [
                base + ext for ext in (".ts", ".tsx", ".js", ".jsx", ".mts", ".cts")
            ]
            candidates += [base + "/index" + ext for ext in (".ts", ".tsx", ".js", ".jsx")]
            if base.endswith(".js"):
                candidates += [base[:-3] + ".ts", base[:-3] + ".tsx"]
    matches = sorted({posixpath.normpath(p) for p in candidates if posixpath.normpath(p) in files})
    # Ambiguous roots/aliases remain unresolved rather than guessing.
    return matches[0] if len(matches) == 1 else None


def is_test(path: str, record: dict) -> bool:
    parts = PurePosixPath(path).parts
    stem = PurePosixPath(path).stem
    return (
        any(p in {"test", "tests", "__tests__"} for p in parts)
        or stem.startswith("test_")
        or stem.endswith(("_test", ".test", ".spec"))
        or any(s["name"].startswith("test_") for s in record["symbols"])
    )


def build_graph(files: dict, git_info: dict | None = None) -> nx.MultiDiGraph:
    graph = nx.MultiDiGraph()
    names, declarations = {}, {}
    config = configuration(files)
    test_paths = {path for path, record in files.items() if is_test(path, record)}
    tests_by_stem = {}
    for test in sorted(test_paths):
        stem = PurePosixPath(test).stem.replace(".test", "").replace(".spec", "")
        tests_by_stem.setdefault(stem, []).append(test)
    for path, record in files.items():
        graph.add_node(path, kind="file", language=record["language"])
        directory = str(PurePosixPath(path).parent)
        graph.add_node("directory:" + directory, kind="directory", name=directory)
        graph.add_edge("directory:" + directory, path, kind="contains")
        for symbol in record["symbols"]:
            node_id = f"{path}::{symbol['name']}:{symbol['start_line']}"
            graph.add_node(
                node_id, **{**symbol, "declaration_kind": symbol["kind"], "kind": "symbol"}
            )
            graph.add_edge(path, node_id, kind="defines")
            names.setdefault(symbol["name"], []).append((path, node_id))
            declarations.setdefault((path, symbol["name"]), []).append(node_id)
    for path, record in files.items():
        resolved = {}
        for module in record["imports"]:
            target = resolve_import(path, module, files, config)
            if target:
                resolved[module] = target
                graph.add_edge(path, target, kind="imports", module=module)
            else:
                external = "module:" + module
                graph.add_node(external, kind="module", name=module)
                graph.add_edge(path, external, kind="imports_external", unresolved=True)
        for binding in record.get("bindings", []):
            module, name = binding["module"], binding["name"]
            target = resolved.get(module)
            submodule = module + ("" if module.endswith(".") else ".") + name
            subtarget = (
                resolve_import(path, submodule, files, config)
                if path.endswith(".py") and name != "*"
                else None
            )
            if subtarget:
                target = subtarget
                graph.add_edge(path, target, kind="imports", module=submodule)
            if target and name != "*":
                matches = declarations.get((target, name), [])
                if name == "default":
                    matches = [
                        f"{target}::{s['name']}:{s['start_line']}"
                        for s in files[target]["symbols"]
                        if s.get("exported")
                        and re.search(r"export\s+default\s", files[target]["content"])
                    ]
                if len(matches) == 1:
                    graph.add_edge(
                        path,
                        matches[0],
                        kind="references_symbol",
                        imported_name=name,
                        local_name=binding["local"],
                        line=binding["line"],
                        evidence="explicit import binding",
                    )
        bound_names = {b["local"] for b in record.get("bindings", [])}
        for name in record["references"]:
            matches = names.get(name, [])
            if name not in bound_names and len(matches) == 1 and matches[0][0] != path:
                graph.add_edge(
                    path,
                    matches[0][1],
                    kind="references",
                    heuristic=True,
                    evidence="unique declaration name; scope not verified",
                )
        if path in test_paths:
            for _, target, data in list(graph.out_edges(path, data=True)):
                if (
                    data["kind"] == "imports"
                    and target in files
                    and target not in test_paths
                ):
                    graph.add_edge(
                        target, path, kind="related_test", evidence="test imports source module"
                    )
    for path in files:
        stem = PurePosixPath(path).stem
        if path in test_paths:
            continue
        matches = sorted({test for name in {"test_" + stem, stem + "_test", stem}
                          for test in tests_by_stem.get(name, [])})
        for test in matches:
            if (
                not any(
                    d["kind"] == "related_test"
                    for d in graph.get_edge_data(path, test, default={}).values()
                )
            ):
                graph.add_edge(
                    path, test, kind="related_test", heuristic=True, evidence="filename convention"
                )
    for pair in (git_info or {}).get("cochanges", []):
        a, b = pair["files"]
        if pair["count"] >= 2 and a in files and b in files:
            graph.add_edge(
                a,
                b,
                kind="cochanged",
                count=pair["count"],
                evidence="observed shared commits; not causal",
            )
            graph.add_edge(
                b,
                a,
                kind="cochanged",
                count=pair["count"],
                evidence="observed shared commits; not causal",
            )
    return graph


def relationships(graph: nx.MultiDiGraph, paths: set[str]) -> list[dict]:
    return [
        {"source": a, "target": b, **data}
        for a, b, data in graph.edges(data=True)
        if a in paths or b in paths
    ]

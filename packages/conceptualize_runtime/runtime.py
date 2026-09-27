import re
from dataclasses import dataclass, field
from time import perf_counter

import tiktoken

from .graph import build_graph, is_test, relationships

_encoding = tiktoken.get_encoding("cl100k_base")


def token_count(text: str) -> int:
    return len(_encoding.encode(text, disallowed_special=()))


def area(path: str, target: str) -> bool:
    target = target.replace("\\", "/").strip("/")
    return target in {"", "."} or path == target or path.startswith(target + "/")


@dataclass
class Priorities:
    explicit: int = 0
    reference: int = 1
    dependency: int = 2
    consumer: int = 3
    test: int = 4
    changed: int = 5
    git: int = 6
    nearby: int = 7
    supporting: int = 8


@dataclass
class ContextRuntime:
    files: dict
    git_info: dict = field(default_factory=dict)
    priorities: Priorities = field(default_factory=Priorities)

    def __post_init__(self):
        started = perf_counter()
        self.graph = build_graph(self.files, self.git_info)
        self.graph_build_ms = (perf_counter() - started) * 1000

    def resolve(self, target: str) -> list[str]:
        target = target.strip()
        if target in self.graph and self.graph.nodes[target].get("kind") == "symbol":
            return [target.split("::")[0]]
        exact = [
            p
            for p, f in self.files.items()
            if area(p, target)
            or any(s["name"] == target or f"{p}::{s['name']}" == target for s in f["symbols"])
        ]
        return sorted(exact) if exact else self.search_paths(target)

    def search_paths(self, query: str) -> list[str]:
        terms = re.findall(r"[\w]+", query.lower())
        if not terms:
            return []
        scored = []
        for path, record in self.files.items():
            symbols = " ".join(s["name"] for s in record["symbols"]).lower()
            text = record["content"].lower()
            score = sum(
                10 * (term in path.lower()) + 8 * (term in symbols) + min(text.count(term), 5)
                for term in terms
            )
            if query.lower() in text:
                score += 10
            if score:
                scored.append((-score, path))
        return [path for _, path in sorted(scored)]

    def execute_context_units(self, operation: str, inputs: dict, units: list) -> dict:
        """Use the generic runtime for explicitly selected context sources."""
        from .context import ContextUnitRuntime

        if operation == "dependencies":
            raise ValueError("dependency analysis is repository-specific")
        level = inputs.get("level") or {
            "map": "map",
            "search": "structure",
            "expand": "source",
            "inspect": "structure",
            "pack": "pack",
        }[operation]
        if operation == "pack":
            level = "pack"
        if operation == "map":
            level = "map"
        sources = set(inputs.get("source_types") or [])
        aliases = {
            "repository": {"repository_file", "code_symbol"},
            "conversation": {"conversation", "message"},
        }
        sources = set().union(*(aliases.get(source, {source}) for source in sources)) or None
        if operation == "map" and inputs.get("path"):
            scope = inputs["path"].replace("\\", "/").strip("/")
            units = [
                unit
                for unit in units
                if unit.source_id == scope
                or unit.source_id.startswith(scope + "/")
                or unit.id == f"conversation:{scope}"
                or unit.metadata.get("conversation_id") == scope
            ]
        targets = list(inputs.get("paths") or [])
        if inputs.get("target"):
            targets.append(inputs["target"])
        query = inputs.get("query", "")
        if not query and operation == "pack":
            query = " ".join(targets)
        engine = ContextUnitRuntime(units)
        result = engine.pack(
            query,
            inputs.get("token_budget", 4000),
            history=inputs.get("_history", []),
            source_types=sources,
            targets=targets,
            level=level,
            score_weights=inputs.get("score_weights"),
        )
        context_units = [
            {
                "id": row["unit_id"],
                "path": row["unit_id"],
                "source_type": row["source_type"],
                "source_id": row["source_id"],
                "priority": max(0, int(row["score"])),
                "reason": ", ".join(reason["signal"] for reason in row["reasons"])
                or "source map",
                "score": row["score"],
                "reasons": row["reasons"],
                "score_reasons": row["reasons"],
                "graph_distance": None,
                "relationship": next(
                    (
                        reason.get("evidence")
                        for reason in row["reasons"]
                        if isinstance(reason.get("evidence"), dict)
                    ),
                    None,
                ),
                "token_cost": row["token_cost"],
                "already_known": row["already_known"],
                "invalidated": row["invalidated"],
                "status": row["status"],
            }
            for row in result["selection"]
        ]
        metrics = result["metrics"]
        metrics["full_selected_tokens"] = metrics["selected_tokens"]
        metrics["previously_supplied_tokens"] = metrics["unchanged_context_tokens"]
        metrics["candidate_files"] = metrics["candidate_units"]
        metrics["returned_files"] = len(result["included_units"])
        return {
            "operation": operation,
            "level": level,
            "context": result["context"],
            "metrics": metrics,
            "included_files": [],
            "included_context": result["included_units"],
            "omitted_files": [],
            "selection": context_units,
            "previous_context": result["previous_context"],
            "deliveries": result["deliveries"],
            "invalidated_context": result["invalidated_units"],
            "retrieval_notice": result["retrieval_notice"],
            "steps": [
                {"name": "Select context sources", "units": len(units)},
                {"name": "Score lexical and explicit relationships", "candidates": len(context_units)},
                {"name": "Compile bounded context delta", "tokens": metrics["returned_tokens"]},
            ],
            "timings_ms": result["timings_ms"],
            "budget_scope": "Compiled context string; metadata and MCP serialization add tokens.",
        }

    def execute(self, operation: str, inputs: dict) -> dict:
        if operation == "inspect":
            from .protocol import inspect

            return inspect(self, inputs)
        traversal_started = perf_counter()
        budget = inputs.get("token_budget", 4000)
        if not 1 <= budget <= 64000:
            raise ValueError("token_budget must be between 1 and 64000")
        reasons = {}
        ordered = []
        steps = [{"name": "Inspect project index", "files": len(self.files)}]
        if operation == "map":
            ordered = [p for p in sorted(self.files) if area(p, inputs.get("path", ""))]
        elif operation == "search":
            ordered = self.search_paths(inputs.get("query", ""))[: inputs.get("limit", 30)]
        elif operation in {"dependencies", "expand"}:
            ordered = self.resolve(inputs.get("target", ""))
        elif operation == "pack":
            for target in inputs.get("paths", []):
                ordered.extend(self.resolve(target))
            if not ordered and inputs.get("query"):
                ordered = self.search_paths(inputs["query"])
        else:
            raise ValueError("Unknown operation")
        ordered = list(dict.fromkeys(ordered))
        explicit = set(ordered)
        for p in ordered:
            reasons[p] = (self.priorities.explicit, "explicit or lexical match")
        traversed = []
        provenance = {}
        changed = set(self.git_info.get("changed_files", []))

        def consider(path, priority, reason, relation):
            if path not in self.files:
                return
            if path not in reasons or priority < reasons[path][0]:
                reasons[path] = (priority, reason)
                provenance[path] = relation
            ordered.append(path)

        if operation in {"dependencies", "expand", "pack"}:
            for path in list(ordered):
                for a, b, data in self.graph.edges(path, data=True):
                    kind = data["kind"]
                    relation = {"source": a, "target": b, **data}
                    if kind == "imports_external":
                        traversed.append(relation)
                    if kind in {"references_symbol", "references"} and (
                        operation != "pack" or inputs.get("include_dependencies", True)
                    ):
                        referenced_file = b.split("::")[0]
                        traversed.append(relation)
                        consider(
                            referenced_file,
                            self.priorities.reference
                            if not data.get("heuristic")
                            else self.priorities.dependency,
                            kind,
                            relation,
                        )
                    if kind == "imports" and (
                        operation != "pack" or inputs.get("include_dependencies", True)
                    ):
                        traversed.append(relation)
                        consider(b, self.priorities.dependency, kind, relation)
                    if kind == "related_test" and (
                        operation != "pack" or inputs.get("include_tests", True)
                    ):
                        traversed.append(relation)
                        consider(b, self.priorities.test, kind, relation)
                if operation != "pack" or inputs.get("include_consumers", True):
                    targets = [path] + [
                        n
                        for n in self.graph.successors(path)
                        if self.graph.nodes[n].get("kind") == "symbol"
                    ]
                    for target in targets:
                        for a, b, data in self.graph.in_edges(target, data=True):
                            if data["kind"] in {"imports", "references_symbol"} and a in self.files:
                                test = is_test(a, self.files[a])
                                if (
                                    test
                                    and operation == "pack"
                                    and not inputs.get("include_tests", True)
                                ):
                                    continue
                                relation = {"source": a, "target": b, **data}
                                traversed.append(relation)
                                consider(
                                    a,
                                    self.priorities.test if test else self.priorities.consumer,
                                    "related_test" if test else "consumer",
                                    relation,
                                )
            # Tests of directly affected consumers are useful for shared-contract changes.
            if operation != "pack" or inputs.get("include_tests", True):
                for path in list(dict.fromkeys(ordered)):
                    for a, b, data in self.graph.edges(path, data=True):
                        if data["kind"] == "related_test":
                            relation = {"source": a, "target": b, **data}
                            traversed.append(relation)
                            consider(b, self.priorities.test, "related_test", relation)
            if operation == "pack":
                for path in sorted(changed & self.files.keys())[:20]:
                    consider(
                        path,
                        self.priorities.changed,
                        "currently modified file",
                        {
                            "kind": "git_changed",
                            "source": "git:working-tree-or-branch",
                            "target": path,
                        },
                    )
                for path in sorted(explicit):
                    for a, b, data in self.graph.edges(path, data=True):
                        if data["kind"] == "cochanged":
                            relation = {"source": a, "target": b, **data}
                            traversed.append(relation)
                            consider(b, self.priorities.git, "observed Git cochange", relation)
                    nearby = sorted(
                        p
                        for p in self.files
                        if p != path and p.rpartition("/")[0] == path.rpartition("/")[0]
                    )[:8]
                    for neighbor in nearby:
                        consider(
                            neighbor,
                            self.priorities.nearby,
                            "same directory",
                            {
                                "kind": "nearby_path",
                                "source": path,
                                "target": neighbor,
                                "heuristic": True,
                            },
                        )
            steps.append(
                {
                    "name": "Traverse direct symbols, dependencies, consumers, tests and Git relationships",
                    "relationships": len(traversed),
                }
            )
        ordered = sorted(
            set(ordered),
            key=lambda p: (reasons.get(p, (0, ""))[0], p not in changed, ordered.index(p)),
        )
        steps.append(
            {
                "name": "Prioritize requested entities and deterministic relationships",
                "files": len(ordered),
            }
        )
        from .disclosure import compile_context

        traversal_ms = (perf_counter() - traversal_started) * 1000
        result = compile_context(
            self, operation, inputs, ordered, explicit, reasons, provenance, traversed
        )
        visible_relations = (
            traversed
            if operation != "map"
            else relationships(self.graph, set(result["selected_files"]))
        )
        result["relationships"] = visible_relations[:200]
        result["relationships_omitted"] = max(0, len(visible_relations) - 200)
        result["steps"] = steps + [
            {
                "name": "Score, select and compile session delta",
                "returned_tokens": result["metrics"]["returned_tokens"],
            }
        ]
        result["git"] = {
            "head": self.git_info.get("head"),
            "changed_files": sorted(changed & set(ordered)),
        }
        result["timings_ms"]["graph_traversal"] = round(traversal_ms, 3)
        from .protocol import annotate

        return annotate(self, result, inputs.get("_history", []))

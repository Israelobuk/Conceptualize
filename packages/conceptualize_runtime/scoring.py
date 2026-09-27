"""Transparent, configurable structural scores; no probabilistic ranking."""

from collections import deque
from pathlib import PurePosixPath

DEFAULT_WEIGHTS = {
    "explicit": 100,
    "referenced_symbol": 75,
    "direct_import": 70,
    "consumer": 65,
    "related_test": 60,
    "branch_modified": 40,
    "working_modified": 20,
    "cochanged": 30,
    "same_module": 20,
    "path_proximity": 5,
    "recent_access": 5,
    "graph_distance": -10,
    "redundancy": -35,
    "duplicate_content": -18,
    "exact_phrase": 30,
    "lexical_overlap": 10,
    "conversation_membership": 12,
    "message_adjacency": 18,
    "decision_context": 28,
    "final_state": 55,
    "related_unit": 5,
}


def relation_index(relations):
    """Preserve edge order while avoiding a complete edge scan per candidate."""
    by_file = {}
    for relation in relations:
        for path in {relation["source"].split("::")[0], relation["target"].split("::")[0]}:
            by_file.setdefault(path, []).append(relation)
    return by_file


def file_distances(graph, targets, files):
    adjacency = {p: set() for p in files}
    for a, b, data in graph.edges(data=True):
        a, b = a.split("::")[0], b.split("::")[0]
        if (
            a in files
            and b in files
            and data["kind"]
            in {"imports", "references_symbol", "references", "related_test", "cochanged"}
        ):
            adjacency[a].add(b)
            adjacency[b].add(a)
    distances = {p: 0 for p in targets}
    queue = deque(targets)
    while queue:
        path = queue.popleft()
        for neighbor in sorted(adjacency[path]):
            if neighbor not in distances:
                distances[neighbor] = distances[path] + 1
                queue.append(neighbor)
    return distances


def score_candidates(files, graph, targets, paths, relations, git, history, weights=None):
    configured = {**DEFAULT_WEIGHTS, **(weights or {})}
    unknown = set(configured) - set(DEFAULT_WEIGHTS)
    if unknown or any(not isinstance(v, int) or abs(v) > 1000 for v in configured.values()):
        raise ValueError("Invalid score weights")
    distances = file_distances(graph, targets, files)
    by_file = relation_index(relations)
    rows = {}
    seen_hashes = set()
    for path in paths:
        reasons = []

        def add(signal, multiplier=1, evidence=None):
            reasons.append(
                {"signal": signal, "weight": configured[signal] * multiplier, "evidence": evidence}
            )

        if path in targets:
            add("explicit")
        matching = by_file.get(path, [])
        for signal, kinds in [
            ("referenced_symbol", {"references_symbol"}),
            ("direct_import", {"imports"}),
            ("consumer", {"imports", "references_symbol"}),
            ("related_test", {"related_test"}),
            ("cochanged", {"cochanged"}),
        ]:
            eligible = [
                r
                for r in matching
                if r["kind"] in kinds
                and (
                    r["source"] in targets and r["target"].split("::")[0] == path
                    if signal in {"referenced_symbol", "direct_import"}
                    else r["source"] == path and r["target"].split("::")[0] in targets
                    if signal == "consumer"
                    else r["target"] == path
                )
            ]
            if eligible and not (
                signal == "consumer"
                and any(r["kind"] == "related_test" and r["target"] == path for r in matching)
            ):
                add(signal, evidence=eligible[0])
        if path in git.get("branch_changed_files", []):
            add("branch_modified")
        if path in git.get("working_tree_files", git.get("changed_files", [])):
            add("working_modified")
        parent = str(PurePosixPath(path).parent)
        if any(str(PurePosixPath(t).parent) == parent for t in targets):
            add("same_module")
        shared = max(
            (
                len(set(PurePosixPath(path).parts[:-1]) & set(PurePosixPath(t).parts[:-1]))
                for t in targets
            ),
            default=0,
        )
        if shared:
            add("path_proximity", min(3, shared))
        recent = [
            u for u in history if u["path"] == path and u.get("file_hash") == files[path]["hash"]
        ]
        if recent:
            add("recent_access")
        distance = distances.get(path)
        if distance is not None and distance:
            add("graph_distance", distance)
        if files[path]["hash"] in seen_hashes:
            add("duplicate_content")
        seen_hashes.add(files[path]["hash"])
        rows[path] = {
            "score": sum(r["weight"] for r in reasons),
            "score_reasons": reasons,
            "graph_distance": distance,
            "recently_accessed": bool(recent),
        }
    return rows, configured

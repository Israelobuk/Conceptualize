"""Deterministic inspect, manifests and content-addressed delivery identities."""

import hashlib
import json
from time import perf_counter

from .graph import is_test


def fingerprint(value):
    return (
        "ctx_"
        + hashlib.sha256(
            json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )


def annotate(runtime, result, history):
    hashes = {p: f["hash"] for p, f in runtime.files.items()}
    relations = result.get("relationships", [])
    for unit in result.get("deliveries", []):
        related = {unit["path"]}
        if unit["level"] == "structure":
            for edge in relations:
                ends = {edge["source"].split("::")[0], edge["target"].split("::")[0]}
                if unit["path"] in ends:
                    related.update(ends & hashes.keys())
        unit["dependency_hashes"] = {p: hashes[p] for p in sorted(related)}
        unit["context_id"] = fingerprint(
            {k: unit[k] for k in ("path", "entities", "ranges", "fingerprint", "dependency_hashes")}
        )
    for previous in result.get("previous_context", []):
        old = next(
            (
                u
                for u in history
                if u.get("trace_id") == previous.get("supplied_in_operation")
                and u["path"] == previous["path"]
                and u.get("level") == previous.get("level")
            ),
            {},
        )
        previous["context_id"] = old.get("context_id") or fingerprint(old)
        previous["status"] = "already_supplied"
        previous["changed"] = False
    invalid = []
    for unit in history:
        dependencies = unit.get("dependency_hashes", {unit["path"]: unit.get("file_hash")})
        changed = sorted(p for p, digest in dependencies.items() if hashes.get(p) != digest)
        if changed:
            invalid.append(
                {
                    "context_id": unit.get("context_id") or fingerprint(unit),
                    "changed_files": changed,
                    "affected_previous_operation": unit.get("trace_id"),
                    "status": "stale",
                    "potentially_affected_relationships": [
                        r
                        for r in relations
                        if r["source"].split("::")[0] in changed
                        or r["target"].split("::")[0] in changed
                    ],
                }
            )
    result["invalidations"] = invalid
    result["context_id"] = fingerprint(
        {
            "operation": result["operation"],
            "files": {
                p: hashes[p]
                for p in result.get("files_considered", result.get("selected_files", []))
            },
            "relationships": relations,
        }
    )
    selected = [r for r in result.get("selection", []) if r.get("status") != "omitted"]
    result["context_id"] = fingerprint(
        {
            "operation": result["operation"],
            "files": {p: hashes[p] for p in result.get("files_considered", [])},
            "units": [(r["path"], r.get("entities", []), r.get("ranges", [])) for r in selected],
            "relations": sorted(set(json.dumps(r, sort_keys=True) for r in relations)),
        }
    )
    result["context_status"] = (
        "already_supplied"
        if any(u.get("context_id") == result["context_id"] for u in history)
        else "new"
    )
    if result["operation"] in {"pack", "inspect"}:
        result["bundle_delivery"] = {
            "path": "__context__",
            "level": "bundle",
            "entities": [],
            "ranges": [],
            "fingerprint": result["context_id"],
            "file_hash": "",
            "context_id": result["context_id"],
            "dependency_hashes": {p: hashes[p] for p in result.get("files_considered", [])},
        }
    return result


def inspect(runtime, inputs):
    from .disclosure import SEPARATOR, compile_context
    from .runtime import token_count

    started = perf_counter()
    target = inputs.get("target", "")
    depth = inputs.get("depth", 1)
    budget = inputs.get("token_budget", 4000)
    if not target.strip() or not 0 <= depth <= 3 or not 1 <= budget <= 64000:
        raise ValueError("inspect requires target, depth 0..3 and budget 1..64000")
    targets = runtime.resolve(target)[: inputs.get("limit", 30)]
    reasons = {p: (0, "explicit or lexical target") for p in targets}
    provenance, traversed = {}, []
    environment = {k: set() for k in ("dependencies", "consumers", "tests", "git")}
    direct_consumers = set()
    frontier = set(targets)
    for _ in range(depth):
        following = set()
        for a, b, data in sorted(
            runtime.graph.edges(data=True), key=lambda e: (e[0], e[1], e[2]["kind"])
        ):
            source, dest = a.split("::")[0], b.split("::")[0]
            if source == dest or source not in runtime.files or dest not in runtime.files:
                continue
            kind = data["kind"]
            candidates = []
            if (
                source in frontier
                and kind in {"imports", "references_symbol", "references"}
                and inputs.get("include_dependencies", True)
            ):
                candidates.append((dest, "dependencies", 2))
            if (
                dest in frontier
                and kind in {"imports", "references_symbol", "references"}
                and inputs.get("include_consumers", True)
            ):
                candidates.append(
                    (source, "tests" if is_test(source, runtime.files[source]) else "consumers", 3)
                )
            if source in frontier and kind == "related_test" and inputs.get("include_tests", True):
                candidates.append((dest, "tests", 4))
            if source in frontier and kind == "cochanged" and inputs.get("include_git", True):
                candidates.append((dest, "git", 6))
            for path, category, priority in candidates:
                if category == "consumers" and dest in targets:
                    direct_consumers.add(path)
                if category == "tests" and not inputs.get("include_tests", True):
                    continue
                edge = {"source": a, "target": b, **data}
                if edge not in traversed:
                    traversed.append(edge)
                environment[category].add(path)
                if path not in reasons:
                    reasons[path] = (priority, category)
                    provenance[path] = edge
                    following.add(path)
        frontier = following
    ordered = sorted(reasons, key=lambda p: (reasons[p][0], p))
    history = inputs.get("_history", [])
    stale_ids = {
        u["context_id"]
        for u in annotate(runtime, {"operation": "inspect", "relationships": traversed}, history)[
            "invalidations"
        ]
    }
    usable = [u for u in history if u.get("context_id") not in stale_ids]
    graph_ms = (perf_counter() - started) * 1000
    structural = compile_context(
        runtime,
        "inspect",
        {
            **inputs,
            "_history": usable,
            "level": "structure",
            "token_budget": budget if inputs.get("manifest_only") else max(1, budget // 2),
        },
        ordered,
        set(targets),
        reasons,
        provenance,
        traversed,
    )
    structural_tokens = token_count(
        "\n".join(
            f"{p}: " + "; ".join(s.get("signature", s["name"]) for s in runtime.files[p]["symbols"])
            for p in ordered
        )
    )
    source_tokens = token_count(
        SEPARATOR.join(f"FILE {p}\n" + runtime.files[p]["content"] for p in ordered)
    )
    known = {
        u["path"]
        for u in usable
        if runtime.files.get(u["path"], {}).get("hash") == u.get("file_hash")
    }
    manifest = {
        "target": target,
        "files": len(ordered),
        "symbols": sum(len(runtime.files[p]["symbols"]) for p in ordered),
        "tests": len(environment["tests"]),
        "direct_consumers": len(direct_consumers),
        "estimated_full_context_tokens": source_tokens + structural_tokens,
        "recommended_structural_tokens": structural_tokens,
        "potential_source_tokens": source_tokens,
        "already_known_files": len(set(ordered) & known),
        "estimate_scope": "Full file source plus compact signatures; not a relevance probability. Framing may differ.",
    }
    result = structural
    if not inputs.get("manifest_only"):
        overhead = token_count(SEPARATOR) if structural["context"] else 0
        remaining = budget - token_count(structural["context"]) - overhead
        if remaining > 0:
            source = compile_context(
                runtime,
                "inspect",
                {**inputs, "_history": usable, "level": "pack", "token_budget": remaining},
                ordered,
                set(targets),
                reasons,
                provenance,
                traversed,
            )
            combined = SEPARATOR.join(
                text for text in (structural["context"], source["context"]) if text
            )
            while token_count(combined) > budget and remaining > 1:
                remaining -= 1
                source = compile_context(
                    runtime,
                    "inspect",
                    {**inputs, "_history": usable, "level": "pack", "token_budget": remaining},
                    ordered,
                    set(targets),
                    reasons,
                    provenance,
                    traversed,
                )
                combined = SEPARATOR.join(
                    text for text in (structural["context"], source["context"]) if text
                )
            result = source
            result["context"] = combined
            result["deliveries"] = structural["deliveries"] + source["deliveries"]
            result["previous_context"] = structural["previous_context"] + source["previous_context"]
            result["selected_files"] = sorted(
                set(structural["selected_files"] + source["selected_files"])
            )
            result["included_files"] = sorted(
                set(structural["included_files"] + source["included_files"])
            )
            for key in (
                "candidate_tokens",
                "full_selected_tokens",
                "previously_supplied_tokens",
                "duplicate_tokens_avoided",
                "duplicate_tokens_retransmitted",
            ):
                result["metrics"][key] += structural["metrics"][key]
            result["metrics"].update(
                returned_tokens=token_count(combined),
                new_context_tokens=token_count(combined),
                token_budget=budget,
                returned_files=len(result["included_files"]),
            )
            result["timings_ms"]["scoring"] += structural["timings_ms"]["scoring"]
    result.update(
        manifest=manifest,
        structural_selection=structural["selection"],
        environment={k: sorted(v) for k, v in environment.items()},
        targets=targets,
        relationships=traversed,
        steps=[{"name": "Inspect bounded structural neighborhood", "files": len(ordered)}],
    )
    result["timings_ms"]["inspect_total"] = round((perf_counter() - started) * 1000, 3)
    result["timings_ms"]["graph_traversal"] = round(graph_ms, 3)
    result["timings_ms"]["context_compilation"] = round(
        max(0, result["timings_ms"]["inspect_total"] - graph_ms - result["timings_ms"]["scoring"]),
        3,
    )
    return annotate(runtime, result, history)

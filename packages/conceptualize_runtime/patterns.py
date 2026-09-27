"""Descriptive protocol patterns, not a usefulness classifier."""


def detect(calls):
    evidence = []
    seen_dependencies = {}
    source = set()
    expands = []
    for i, call in enumerate(calls):
        op, inputs = call["operation"], call.get("inputs", {})
        metrics = call.get("metrics", {})
        prior = calls[i - 1] if i else None

        def add(pattern, detail):
            evidence.append(
                {
                    "pattern": pattern,
                    "call_index": i,
                    "evidence": detail,
                    "interpretation": "Observed sequence; correctness or usefulness requires task evidence.",
                }
            )

        if (
            op == "search"
            and prior
            and prior["operation"] == "map"
            and not prior.get("inputs", {}).get("path")
        ):
            add("map_then_search", {"query": inputs.get("query"), "broad_map": True})
        if op == "dependencies":
            target = inputs.get("target", "")
            if target in seen_dependencies:
                add(
                    "repeated_dependencies",
                    {"target": target, "previous_call": seen_dependencies[target]},
                )
            seen_dependencies[target] = i
        selected = set(call.get("selected_files", call.get("included_files", [])))
        if op == "pack" and selected and selected <= source:
            add(
                "pack_after_same_source",
                {"files": sorted(selected), "new_tokens": metrics.get("new_context_tokens")},
            )
        full = metrics.get("full_selected_tokens", 0)
        if full and metrics.get("previously_supplied_tokens", 0) / full >= 0.75:
            add(
                "mostly_known_context",
                {
                    "previous_tokens": metrics["previously_supplied_tokens"],
                    "full_selected_tokens": full,
                    "threshold": 0.75,
                },
            )
        if op == "expand":
            expands.append(inputs.get("target"))
            if len(expands) >= 3:
                add(
                    "multiple_expands",
                    {
                        "targets": expands[-3:],
                        "alternative": "Consider one inspect when a shared structural neighborhood suffices; distinct required source ranges may justify expands.",
                    },
                )
        else:
            expands = []
        source.update(
            u["path"] for u in call.get("deliveries", []) if u.get("level") in {"source", "pack"}
        )
    return evidence

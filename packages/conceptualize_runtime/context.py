"""Source-agnostic, deterministic context units and bounded retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from time import perf_counter

_STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "did", "do", "for", "from",
    "how", "in", "is", "it", "of", "on", "or", "the", "to", "was", "were", "what",
    "which", "who", "why", "with", "would", "we", "you", "your",
}


@dataclass
class ContextUnit:
    id: str
    source_type: str
    source_id: str
    content: str
    parent_id: str | None = None
    content_hash: str = ""
    version: str = "1"
    token_count: int = 0
    created_at: str | None = None
    updated_at: str | None = None
    relationships: list[dict] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        import hashlib

        if not self.id or not self.source_type or not self.source_id:
            raise ValueError("ContextUnit id, source_type and source_id are required")
        actual_hash = hashlib.sha256(self.content.encode("utf-8")).hexdigest()
        if self.content_hash and self.content_hash != actual_hash:
            raise ValueError("content_hash does not match content")
        self.content_hash = actual_hash
        if not self.token_count:
            from .runtime import token_count

            self.token_count = token_count(self.content)
        if self.token_count < 0:
            raise ValueError("token_count must be non-negative")
        self.created_at = self.created_at or datetime.now(timezone.utc).isoformat()
        self.updated_at = self.updated_at or self.created_at


class ContextUnitRuntime:
    """Deterministic lexical retrieval and context-delta compilation across sources."""

    def __init__(self, units):
        self.units = list(units)
        if len({unit.id for unit in self.units}) != len(self.units):
            raise ValueError("ContextUnit ids must be unique")

    def search(
        self,
        query: str,
        *,
        source_types: set[str] | None = None,
        limit: int = 30,
        weights: dict | None = None,
    ):
        from .runtime import token_count
        from .scoring import DEFAULT_WEIGHTS

        configured = {**DEFAULT_WEIGHTS, **(weights or {})}
        if set(configured) - set(DEFAULT_WEIGHTS) or any(
            not isinstance(value, int) or abs(value) > 1000 for value in configured.values()
        ):
            raise ValueError("Invalid score weights")
        query = query.strip().lower()
        # The prompt already carries the active request. Returning a transcript
        # copy of that same request adds tokens without adding prior context.
        query_phrase = query.strip() if len(query.split()) > 4 else ""
        terms = [
            term
            for term in dict.fromkeys(re.findall(r"[\w]+", query))
            if term not in _STOPWORDS
        ]
        if not terms:
            return []
        documents = [
            unit
            for unit in self.units
            if source_types is None or unit.source_type in source_types
        ]
        document_frequency = {
            term: sum(term in set(re.findall(r"[\w]+", unit.content.lower())) for unit in documents)
            for term in terms
        }
        results = []
        for unit in documents:
            text = unit.content.lower()
            if query_phrase and query_phrase in text:
                continue
            words = re.findall(r"[\w]+", text)
            if not words:
                continue
            reasons = []
            phrase = query in text
            if phrase:
                reasons.append(
                    {"signal": "exact_phrase", "weight": configured["exact_phrase"]}
                )
            overlap = 0
            for term in terms:
                frequency = words.count(term)
                if frequency:
                    # BM25-style lexical weighting; this is not a semantic score.
                    inverse_frequency = 1 + (len(documents) - document_frequency[term] + 0.5) / (
                        document_frequency[term] + 0.5
                    )
                    raw_weight = min(
                        10.0,
                        inverse_frequency * frequency / (1 + 0.25 * len(words) / 100),
                    )
                    weight = round(configured["lexical_overlap"] * raw_weight / 10, 3)
                    overlap += weight
                    reasons.append({"signal": "lexical_overlap", "term": term, "weight": weight})
            if overlap or phrase:
                results.append(
                    {
                        "unit": unit,
                        "score": round(overlap + (configured["exact_phrase"] if phrase else 0), 3),
                        "reasons": reasons,
                        "token_count": token_count(unit.content),
                        "lexical_only": True,
                    }
                )
        return sorted(results, key=lambda row: (-row["score"], row["unit"].id))[:limit]

    def pack(
        self,
        query: str,
        token_budget: int,
        *,
        history: list[dict] | None = None,
        source_types: set[str] | None = None,
        targets: list[str] | None = None,
        level: str = "pack",
        limit: int = 30,
        score_weights: dict | None = None,
    ) -> dict:
        from .runtime import token_count
        scoring_started = perf_counter()

        if not 1 <= token_budget <= 64000:
            raise ValueError("token_budget must be between 1 and 64000")
        from .scoring import DEFAULT_WEIGHTS

        history = history or []
        configured = {**DEFAULT_WEIGHTS, **(score_weights or {})}
        if set(configured) - set(DEFAULT_WEIGHTS) or any(
            not isinstance(value, int) or abs(value) > 1000 for value in configured.values()
        ):
            raise ValueError("Invalid score weights")
        prior_by_id = {}
        for row in history:
            prior_by_id.setdefault(row.get("unit_id"), []).append(row)
        matches = self.search(query, source_types=source_types, limit=limit, weights=configured)
        query_terms = set(re.findall(r"[\w]+", query.lower()))
        planning_terms = {
            "architecture", "plan", "decision", "decisions", "constraint",
            "constraints", "implementation", "current", "overall", "everything",
        }
        if query_terms & planning_terms:
            by_match_id = {row["unit"].id: row for row in matches}
            decision_pattern = re.compile(
                r"\b(?:must|must not|do not|don't|not adding|exclude\w*|out of scope|"
                r"supersed\w*|final (?:architecture|review|decision)|constraint|"
                r"first release|v1|keep .{0,45} (?:until|out|local)|we are not|"
                r"no\s+web\s?socket|not semantic understanding)\b",
                re.IGNORECASE,
            )
            final_pattern = re.compile(
                r"\b(?:final (?:architecture|review|decision)|current (?:direction|plan|state)|"
                r"use that review as the current)\b",
                re.IGNORECASE,
            )
            for unit in self.units:
                if unit.source_type != "message":
                    continue
                decision_match = decision_pattern.search(unit.content)
                role = unit.metadata.get("role")
                # User statements can define decisions freely. Only admit an
                # assistant message when it states a compact explicit rule.
                if not decision_match or (role != "user" and not re.search(
                    r"\b(?:no\s+web\s?socket|must state that lexical relevance is not semantic understanding)\b",
                    unit.content,
                    re.IGNORECASE,
                )):
                    continue
                row = by_match_id.get(unit.id)
                if row is None:
                    row = {
                        "unit": unit,
                        "score": 0,
                        "reasons": [],
                        "token_count": token_count(unit.content),
                        "lexical_only": False,
                    }
                    matches.append(row)
                    by_match_id[unit.id] = row
                row["score"] += configured["decision_context"]
                row["reasons"].append(
                    {"signal": "decision_context", "weight": configured["decision_context"]}
                )
                if final_pattern.search(unit.content):
                    row["score"] += configured["final_state"]
                    row["reasons"].append(
                        {"signal": "final_state", "weight": configured["final_state"]}
                    )
            matches.sort(key=lambda row: (-row["score"], row["unit"].id))
            matches = matches[:limit]
        if level == "map" and not query.strip():
            matches = [
                {
                    "unit": unit,
                    "score": 0,
                    "reasons": [],
                    "token_count": unit.token_count,
                    "lexical_only": False,
                }
                for unit in self.units
                if source_types is None or unit.source_type in source_types
            ]
        targets = targets or []
        matched_ids = {row["unit"].id for row in matches}
        for unit in self.units:
            if source_types is not None and unit.source_type not in source_types:
                continue
            if any(
                target in {unit.id, unit.source_id, unit.metadata.get("path")}
                for target in targets
            ) and unit.id not in matched_ids:
                matches.append(
                    {
                        "unit": unit,
                        "score": 100,
                        "reasons": [{"signal": "explicit_target", "weight": 100}],
                        "token_count": token_count(unit.content),
                        "lexical_only": False,
                    }
                )
        for row in matches:
            if row["unit"].id in {
                unit.id
                for unit in self.units
                if source_types is None or unit.source_type in source_types
                if any(
                    target in {unit.id, unit.source_id, unit.metadata.get("path")}
                    for target in targets
                )
            } and not any(reason["signal"] == "explicit_target" for reason in row["reasons"]):
                row["score"] += 100
                row["reasons"].append({"signal": "explicit_target", "weight": 100})
        by_id = {unit.id: unit for unit in self.units}
        by_source = {unit.source_id: unit for unit in self.units}

        def resolve_endpoint(value):
            if value in by_id:
                return by_id[value]
            if value in by_source:
                return by_source[value]
            return by_source.get(value.split("::", 1)[0])

        direct_ids = {row["unit"].id for row in matches}
        seed_ids = set(direct_ids)
        relation_signals = {
            "imports": "direct_import",
            "references_symbol": "referenced_symbol",
            "references": "related_unit",
            "related_test": "related_test",
            "cochanged": "cochanged",
        }
        for owner in self.units:
            for relation in owner.relationships:
                source = resolve_endpoint(relation.get("source", owner.id))
                target = resolve_endpoint(relation.get("target", ""))
                if not source or not target or source.id == target.id:
                    continue
                related_id = None
                if source.id in seed_ids:
                    related_id = target.id
                elif target.id in seed_ids:
                    related_id = source.id
                if not related_id or related_id in direct_ids:
                    continue
                related = by_id[related_id]
                if source_types is not None and related.source_type not in source_types:
                    continue
                if not related.content.strip():
                    continue
                kind = relation.get("kind", "related")
                if kind not in relation_signals:
                    continue
                signal = relation_signals.get(kind, "related_unit")
                weight = configured[signal]
                matches.append(
                    {
                        "unit": related,
                        "score": weight,
                        "reasons": [{"signal": signal, "weight": weight, "evidence": relation}],
                        "token_count": token_count(related.content),
                        "lexical_only": False,
                    }
                )
                direct_ids.add(related_id)
        # Do not emit the indexed copy of the active prompt. It is already in
        # the host request and can otherwise crowd out historical decisions.
        active_query = query.strip().casefold()
        if len(active_query.split()) > 4:
            matches = [
                row for row in matches
                if active_query not in row["unit"].content.casefold()
            ]
        matches.sort(key=lambda row: (-row["score"], row["unit"].id))
        candidates = []
        seen_content = set()
        for match in matches:
            unit = match["unit"]
            prior = prior_by_id.get(unit.id, [])
            known_prior = next(
                (
                    row
                    for row in reversed(prior)
                    if row.get("content_hash") == unit.content_hash
                    and row.get("level", "pack") == level
                ),
                None,
            )
            unchanged = known_prior is not None
            invalidated = bool(prior) and not any(
                row.get("content_hash") == unit.content_hash for row in prior
            )
            header = f"[{unit.source_type}:{unit.source_id}]"
            if level == "map":
                display = f"{unit.id} ({unit.token_count} tokens)"
            elif level == "structure":
                if unit.source_type == "repository_file":
                    symbols = unit.metadata.get("symbols", [])[:30]
                    declarations = [
                        f"{symbol.get('signature') or symbol['name']} L{symbol.get('start_line', '?')}"
                        for symbol in symbols
                    ]
                    display = (
                        f"{unit.id}\nlanguage={unit.metadata.get('language', 'text')} "
                        f"chars={len(unit.content)}\n" + "\n".join(declarations)
                    )
                else:
                    terms = [
                        term
                        for term in re.findall(r"[\w]+", query.lower())
                        if term not in _STOPWORDS
                    ]
                    if unit.source_type in {"message", "conversation", "document_section", "arbitrary_text"}:
                        lines = re.split(r"(?<=[.!?])\s+", unit.content)
                    else:
                        lines = unit.content.splitlines() or [unit.content]
                    relevant = []
                    for line in lines:
                        lowered = line.lower()
                        for term in terms:
                            offset = lowered.find(term)
                            if offset >= 0:
                                excerpt = line.strip()[:240]
                                if excerpt and excerpt not in relevant:
                                    relevant.append(excerpt)
                        if len(relevant) >= 3:
                            break
                    display = (
                        f"{unit.id}\nrole={unit.metadata.get('role', 'n/a')} "
                        f"timestamp={unit.metadata.get('timestamp', 'n/a')} "
                        f"parent={unit.parent_id or 'n/a'} chars={len(unit.content)}"
                        + ("\n" + "\n".join(relevant) if relevant else "")
                    )
            else:
                display = unit.content
            block = header + "\n" + display
            reasons = list(match["reasons"])
            score = match["score"]
            prior = prior_by_id.get(unit.id, [])
            known_prior = next(
                (
                    row
                    for row in reversed(prior)
                    if row.get("content_hash") == unit.content_hash
                    and row.get("level", "pack") == level
                ),
                None,
            )
            if known_prior:
                reasons.append(
                    {
                        "signal": "redundancy",
                        "weight": configured["redundancy"],
                        "evidence": known_prior.get("trace_id"),
                    }
                )
                score += configured["redundancy"]
            if unit.content_hash in seen_content:
                reasons.append(
                    {"signal": "duplicate_content", "weight": configured["duplicate_content"]}
                )
                score += configured["duplicate_content"]
            seen_content.add(unit.content_hash)
            candidates.append(
                {
                    **match,
                    "score": score,
                    "reasons": reasons,
                    "block": block,
                    "block_tokens": token_count(block),
                    "already_known": unchanged,
                    "invalidated": invalidated,
                    "previous": known_prior or (prior[-1] if prior else None),
                }
            )
        candidate_tokens = sum(row["block_tokens"] for row in candidates)
        scoring_ms = (perf_counter() - scoring_started) * 1000
        compilation_started = perf_counter()
        context = ""
        selected = []
        omitted = []
        previous_context = []
        deliveries = []
        for row in candidates:
            unit = row["unit"]
            if row["already_known"]:
                previous_context.append(
                    {
                        "unit_id": unit.id,
                        "source_type": unit.source_type,
                        "source_id": unit.source_id,
                        "supplied_in_operation": row["previous"].get(
                            "operation_id", row["previous"].get("trace_id")
                        ),
                        "unchanged": True,
                    }
                )
                row["status"] = "referenced"
                selected.append(row)
                continue
            separator = "\n\n---\n\n" if context else ""
            proposed = context + separator + row["block"]
            if token_count(proposed) <= token_budget:
                context = proposed
                row["status"] = "selected"
                selected.append(row)
                deliveries.append(
                    {
                        "unit_id": unit.id,
                        "path": unit.source_id,
                        "content_hash": unit.content_hash,
                        "level": level,
                        "token_count": token_count(row["block"]),
                    }
                )
            else:
                row["status"] = "omitted"
                row["omission_reason"] = "does not fit remaining token budget"
                omitted.append(unit.id)
        selected_tokens = sum(row["block_tokens"] for row in selected)
        previously_supplied = sum(
            row["block_tokens"] for row in selected if row["already_known"]
        )
        public_candidates = [
            {
                "unit_id": row["unit"].id,
                "source_type": row["unit"].source_type,
                "source_id": row["unit"].source_id,
                "score": row["score"],
                "reasons": row["reasons"],
                "token_cost": row["block_tokens"],
                "already_known": row["already_known"],
                "invalidated": row["invalidated"],
                "status": row["status"],
                **({"omission_reason": row["omission_reason"]} if "omission_reason" in row else {}),
            }
            for row in candidates
        ]
        invalidated = [row["unit"].id for row in candidates if row["invalidated"]]
        return {
            "context": context,
            "selection": public_candidates,
            "included_units": [row["unit"].id for row in selected if not row["already_known"]],
            "omitted_units": omitted,
            "previous_context": previous_context,
            "deliveries": deliveries,
            "invalidated_units": invalidated,
            "metrics": {
                "available_context_tokens": sum(unit.token_count for unit in self.units),
                "candidate_tokens": candidate_tokens,
                "selected_tokens": selected_tokens,
                "previously_supplied_tokens": previously_supplied,
                "unchanged_context_tokens": previously_supplied,
                "invalidated_context_tokens": sum(
                    row["block_tokens"] for row in candidates if row["invalidated"]
                ),
                "new_context_tokens": token_count(context),
                "duplicate_tokens_avoided": previously_supplied,
                "returned_tokens": token_count(context),
                "token_budget": token_budget,
                "candidate_units": len(candidates),
                "selected_units": len(selected),
                "omitted_units": len(omitted),
            },
            "timings_ms": {
                "scoring": round(scoring_ms, 3),
                "context_compilation": round(
                    (perf_counter() - compilation_started) * 1000, 3
                ),
            },
            "score_weights": configured,
            "retrieval_notice": "Lexical ranking is deterministic and does not represent semantic understanding.",
        }

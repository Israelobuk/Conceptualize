"""Deterministic, provenance-preserving labels for compiled working context."""

from __future__ import annotations

import re

_CATEGORIES = {
    "decision": "CURRENT DECISIONS",
    "current_decision": "CURRENT DECISIONS",
    "constraint": "CONSTRAINTS",
    "current_constraint": "CONSTRAINTS",
    "implementation_state": "CURRENT IMPLEMENTATION STATE",
    "current_state": "CURRENT IMPLEMENTATION STATE",
}
_CONSTRAINT = re.compile(
    r"\b(?:must(?: not)?|never|do not|don't|should not|out of scope|not adding)\b",
    re.IGNORECASE,
)
_IMPLEMENTATION_STATE = re.compile(
    r"\b(?:implemented|integrated|shipped|complete|completed|unfinished|incomplete|"
    r"not complete|still open|next step|next we should)\b",
    re.IGNORECASE,
)
_DECISION = re.compile(
    r"\b(?:we chose|we decided|new direction|we are switching|supersede|superseded|"
    r"current architecture|use [\w.-]+ for|the agreed)\b",
    re.IGNORECASE,
)


def classify_working_context(unit) -> tuple[str, str]:
    """Return a stable display category and the rule provenance for one unit."""
    metadata = unit.metadata or {}
    explicit = metadata.get("context_category") or metadata.get("context_type")
    if isinstance(explicit, str) and explicit.casefold() in _CATEGORIES:
        return _CATEGORIES[explicit.casefold()], "explicit_metadata"

    relationship_kinds = {item.get("kind") for item in unit.relationships}
    if relationship_kinds & {"updates", "supersedes", "decision_for"}:
        return "CURRENT DECISIONS", "explicit_relationship"
    if "constraint_for" in relationship_kinds:
        return "CONSTRAINTS", "explicit_relationship"

    if _CONSTRAINT.search(unit.content):
        return "CONSTRAINTS", "deterministic_rule"
    if _IMPLEMENTATION_STATE.search(unit.content):
        return "CURRENT IMPLEMENTATION STATE", "deterministic_rule"
    if _DECISION.search(unit.content):
        return "CURRENT DECISIONS", "deterministic_rule"
    if unit.source_type == "repository_file":
        return "RELEVANT SOURCE CONTEXT", "source_type"
    return "RELEVANT CONTEXT", "source_default"


def render_working_context(groups: dict[str, list[str]]) -> str:
    """Render nonempty evidence groups without synthesizing or paraphrasing content."""
    sections = [
        f"{category}\n" + "\n\n---\n\n".join(blocks)
        for category, blocks in groups.items()
        if blocks
    ]
    return "CONCEPTUALIZE WORKING CONTEXT\n\n" + "\n\n".join(sections) if sections else ""

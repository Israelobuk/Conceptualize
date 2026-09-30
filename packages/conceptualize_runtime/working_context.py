"""Deterministic priorities and provenance-preserving Working Context labels."""

from __future__ import annotations

import re

_CATEGORIES = {
    "decision": "CURRENT DECISIONS",
    "current_decision": "CURRENT DECISIONS",
    "constraint": "CRITICAL CURRENT CONSTRAINTS",
    "current_constraint": "CRITICAL CURRENT CONSTRAINTS",
    "implementation_state": "CURRENT IMPLEMENTATION STATE",
    "current_state": "CURRENT IMPLEMENTATION STATE",
    "prior_work": "RELEVANT PRIOR WORK",
    "supporting": "SUPPORTING CONTEXT",
    "informational": "SUPPORTING CONTEXT",
}
_PRIORITY_RANK = {"critical": 0, "required": 1, "supporting": 2, "informational": 3}
_SECTION_ORDER = (
    "CRITICAL CURRENT CONSTRAINTS",
    "CURRENT DECISIONS",
    "CURRENT IMPLEMENTATION STATE",
    "RELEVANT PRIOR WORK",
    "RELEVANT SOURCE CONTEXT",
    "SUPPORTING CONTEXT",
    "RELEVANT CONTEXT",
    "SUPERSEDED / DO NOT USE",
    "CONTEXT DELTA",
)
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
_PERSISTENCE = re.compile(r"\b(?:local\s+)?persistence\b|\blocalstore\b", re.IGNORECASE)
_SYNCHRONIZATION = re.compile(
    r"\b(?:sync(?:hroniz\w*)?|syncengine|transfer\s+boundary)\b", re.IGNORECASE
)
_REPLACEABILITY = re.compile(
    r"\b(?:independent(?:ly)?\s+(?:replaceable|swappable)|"
    r"replace(?:able|ability)?\s+(?:either|each|both|independent\w*)|"
    r"change\s+either\s+(?:implementation|layer|boundary)|"
    r"separate\s+replaceable\s+(?:layers|boundaries))\b",
    re.IGNORECASE,
)
_REQUIRED = re.compile(
    r"\b(?:must(?:\s+not)?|do\s+not|don't|never|non[- ]negotiable|"
    r"required|constraint|should\s+not|out\s+of\s+scope)\b",
    re.IGNORECASE,
)
_SUPERSEDED_STATE = {"superseded", "stale", "invalidated", "obsolete"}


def _is_independently_replaceable_boundary(content: str) -> bool:
    return bool(
        _PERSISTENCE.search(content)
        and _SYNCHRONIZATION.search(content)
        and _REPLACEABILITY.search(content)
    )


def context_priority(unit, units=()) -> dict:
    """Derive conservative action priority from explicit metadata and text rules."""
    metadata = unit.metadata or {}
    explicit_metadata = metadata.get("explicit_metadata") or {}
    declared = str(
        metadata.get("priority") or metadata.get("importance")
        or explicit_metadata.get("priority") or explicit_metadata.get("importance") or ""
    ).casefold()
    state = str(metadata.get("state") or metadata.get("status")
                or explicit_metadata.get("state") or explicit_metadata.get("status") or "").casefold()
    relationships = {item.get("kind") for item in unit.relationships}
    corroborating = [
        other.id for other in units
        if other.id != unit.id
        and _is_independently_replaceable_boundary(other.content)
        and _is_independently_replaceable_boundary(unit.content)
    ]
    if (state in _SUPERSEDED_STATE or metadata.get("superseded") is True
            or explicit_metadata.get("superseded") is True):
        return {"level": "informational", "reasons": ["explicit_superseded_state"],
                "corroborating_units": []}
    if declared in _PRIORITY_RANK:
        return {"level": declared, "reasons": ["explicit_priority_metadata"],
                "corroborating_units": corroborating}
    if metadata.get("critical") is True or explicit_metadata.get("critical") is True:
        return {"level": "critical", "reasons": ["explicit_critical_metadata"],
                "corroborating_units": corroborating}
    if _is_independently_replaceable_boundary(unit.content):
        reasons = ["explicit_independent_layer_replaceability"]
        if corroborating:
            reasons.append("repeated_architecture_confirmation")
        return {"level": "critical", "reasons": reasons,
                "corroborating_units": corroborating}
    if "constraint_for" in relationships or _REQUIRED.search(unit.content):
        return {"level": "required", "reasons": [
            "explicit_constraint_relationship" if "constraint_for" in relationships
            else "deterministic_mandatory_language"
        ], "corroborating_units": corroborating}
    if "decision_for" in relationships or declared in {"decision", "current_decision"}:
        return {"level": "supporting", "reasons": ["explicit_decision_context"],
                "corroborating_units": corroborating}
    return {"level": "supporting", "reasons": ["default_supporting_context"],
            "corroborating_units": corroborating}


def classify_working_context(unit, priority: dict | None = None) -> tuple[str, str]:
    """Return a stable display category and the rule provenance for one unit."""
    metadata = unit.metadata or {}
    explicit_metadata = metadata.get("explicit_metadata") or {}
    state = str(metadata.get("state") or metadata.get("status")
                or explicit_metadata.get("state") or explicit_metadata.get("status") or "").casefold()
    if (state in _SUPERSEDED_STATE or metadata.get("superseded") is True
            or explicit_metadata.get("superseded") is True):
        return "SUPERSEDED / DO NOT USE", "explicit_metadata"
    priority = priority or context_priority(unit)
    if priority["level"] == "critical":
        return "CRITICAL CURRENT CONSTRAINTS", "deterministic_priority"
    if priority["level"] == "required":
        return "CRITICAL CURRENT CONSTRAINTS", "deterministic_priority"
    explicit = (metadata.get("context_category") or metadata.get("context_type")
                or explicit_metadata.get("context_category") or explicit_metadata.get("context_type"))
    if isinstance(explicit, str) and explicit.casefold() in _CATEGORIES:
        return _CATEGORIES[explicit.casefold()], "explicit_metadata"

    relationship_kinds = {item.get("kind") for item in unit.relationships}
    if relationship_kinds & {"updates", "supersedes", "decision_for"}:
        return "CURRENT DECISIONS", "explicit_relationship"
    if "constraint_for" in relationship_kinds:
        return "CRITICAL CURRENT CONSTRAINTS", "explicit_relationship"

    if _CONSTRAINT.search(unit.content):
        return "CRITICAL CURRENT CONSTRAINTS", "deterministic_rule"
    if _IMPLEMENTATION_STATE.search(unit.content):
        return "CURRENT IMPLEMENTATION STATE", "deterministic_rule"
    if _DECISION.search(unit.content):
        return "CURRENT DECISIONS", "deterministic_rule"
    if unit.source_type == "repository_file":
        return "RELEVANT SOURCE CONTEXT", "source_type"
    return "RELEVANT CONTEXT", "source_default"


def render_working_context(groups: dict[str, list[str]]) -> str:
    """Render current actionable context first without rewriting source evidence."""
    sections = [
        f"{category}\n" + "\n\n---\n\n".join(blocks)
        for category in _SECTION_ORDER
        if (blocks := groups.get(category))
    ]
    if not sections:
        return ""
    directive = (
        "Treat current decisions and critical constraints below as binding; "
        "do not omit or contradict relevant items."
    )
    return "CONCEPTUALIZE WORKING CONTEXT\n\n" + directive + "\n\n" + "\n\n".join(sections)

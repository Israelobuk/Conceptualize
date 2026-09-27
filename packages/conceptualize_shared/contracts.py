from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Metrics(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    candidate_tokens: int = Field(ge=0)
    returned_tokens: int = Field(ge=0)
    token_budget: int = Field(ge=1, le=64000)
    latency_ms: int = Field(default=0, ge=0)
    cache_hit: bool = False


class Selection(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    path: str
    priority: int = Field(ge=0)
    reason: str
    relationship: dict[str, Any] | None = None
    token_cost: int = Field(ge=0)
    status: Literal["selected", "omitted", "truncated", "referenced"]
    omission_reason: str | None = None


class CompiledContext(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)
    operation: Literal["map", "search", "dependencies", "expand", "pack", "inspect"]
    context: str
    metrics: Metrics
    included_files: list[str]
    omitted_files: list[str]
    truncated_files: list[str] = Field(default_factory=list)
    sources: list[dict[str, Any]] = Field(default_factory=list)
    selection: list[Selection] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    steps: list[dict[str, Any]] = Field(default_factory=list)


class ContextResponse(CompiledContext):
    trace_id: str
    otel_trace_id: str

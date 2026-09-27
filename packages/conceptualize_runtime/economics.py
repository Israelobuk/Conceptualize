"""Estimated model-input economics from an explicit, versioned pricing snapshot."""

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class ModelPricing:
    model: str
    version: str
    input_per_million: float
    cached_input_per_million: float
    output_per_million: float
    currency: str = "USD"

    def __post_init__(self):
        if not self.model.strip() or not self.version.strip():
            raise ValueError("model and pricing version are required")
        if any(
            value < 0
            for value in (
                self.input_per_million,
                self.cached_input_per_million,
                self.output_per_million,
            )
        ):
            raise ValueError("pricing rates must be non-negative")


def load_pricing(path: str | Path) -> dict[str, ModelPricing]:
    """Load user-supplied per-model snapshots; this package ships no live price table."""
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or not isinstance(payload.get("models"), list):
        raise ValueError("pricing file must contain a models list")
    result = {}
    for row in payload["models"]:
        pricing = ModelPricing(**row)
        if pricing.model in result:
            raise ValueError(f"duplicate model pricing entry: {pricing.model}")
        result[pricing.model] = pricing
    return result


def estimate_cost(
    pricing: ModelPricing,
    *,
    input_tokens: int | None,
    cached_input_tokens: int | None,
    output_tokens: int | None,
) -> dict:
    """Return a cost only when all telemetry is present; cached tokens are a subset of input."""
    values = (input_tokens, cached_input_tokens, output_tokens)
    if any(value is None for value in values):
        return {
            "model": pricing.model,
            "pricing_version": pricing.version,
            "pricing": asdict(pricing),
            "input_tokens": input_tokens,
            "cached_input_tokens": cached_input_tokens,
            "output_tokens": output_tokens,
            "estimated_cost": None,
            "unavailable_reason": "one or more token telemetry fields are unavailable",
        }
    if any(not isinstance(value, int) or value < 0 for value in values):
        raise ValueError("token counts must be non-negative integers or unavailable")
    if cached_input_tokens > input_tokens:
        raise ValueError("cached_input_tokens cannot exceed input_tokens")
    uncached = input_tokens - cached_input_tokens
    estimated = (
        uncached * pricing.input_per_million
        + cached_input_tokens * pricing.cached_input_per_million
        + output_tokens * pricing.output_per_million
    ) / 1_000_000
    return {
        "model": pricing.model,
        "pricing_version": pricing.version,
        "pricing": asdict(pricing),
        "input_tokens": input_tokens,
        "cached_input_tokens": cached_input_tokens,
        "output_tokens": output_tokens,
        "estimated_cost": estimated,
        "currency": pricing.currency,
    }

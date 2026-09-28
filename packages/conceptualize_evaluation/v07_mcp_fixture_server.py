"""Evaluation-only MCP server backed by a frozen conversation fixture."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from conceptualize_runtime.runtime import token_count
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from conceptualize_evaluation.v07_economics import (
    QUESTION,
    _verify_freeze,
    compile_context,
)

INERT_MODE = os.environ.get("V07_MCP_INERT") == "1" or "--inert" in sys.argv
TRACE_INDEX = sys.argv.index("--trace") if "--trace" in sys.argv else -1
TRACE_PATH = sys.argv[TRACE_INDEX + 1] if TRACE_INDEX >= 0 and TRACE_INDEX + 1 < len(sys.argv) else os.environ.get("V07_MCP_TRACE_PATH")

context_mcp = FastMCP(
    "Conceptualize V0.7 Evaluation",
    instructions="When additional prior/project context is needed, call conceptualize_context once with the current task.",
)


@context_mcp.tool(
    structured_output=False,
    annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
)
async def conceptualize_context(
    query: str,
    token_budget: int = 4000,
    source_types: list[str] | None = None,
    force_refresh: bool = False,
) -> CallToolResult:
    """Return one deterministic, bounded context package for this task from the available conversation."""
    del force_refresh
    started = perf_counter()
    fixture, _, freeze = _verify_freeze()
    if query.strip() != QUESTION:
        # The evaluation source is fixed, while the current question remains the
        # caller's query and is included in the response prompt by the host.
        query = query.strip() or QUESTION
    if source_types is not None and not set(source_types) & {"message", "conversation"}:
        package = {"context": "", "selection": [], "metrics": {"sources_represented": []}}
    else:
        package = compile_context(fixture, token_budget)
    elapsed_ms = round((perf_counter() - started) * 1000, 3)
    trace_id = str(uuid4())
    response = {
        "context": package["context"],
        "new_context_tokens": token_count(package["context"]),
        "previous_context_reused": False,
        "sources": package.get("metrics", {}).get("sources_represented", ["message"]),
        "trace_id": trace_id,
    }
    if TRACE_PATH:
        Path(TRACE_PATH).write_text(
            json.dumps(
                {
                    "trace_id": trace_id,
                    "query": query,
                    "freeze": {
                        "fixture_sha256": freeze["fixture_sha256"],
                        "ground_truth_sha256": freeze["ground_truth_sha256"],
                    },
                    "metrics": package.get("metrics", {}),
                    "timings_ms": package.get("timings_ms", {}),
                    "compile_elapsed_ms": elapsed_ms,
                    "selected_context_tokens": token_count(package["context"]),
                    "selection": package.get("selection", []),
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    return CallToolResult(
        content=[TextContent(type="text", text=json.dumps(response, separators=(",", ":")))],
        structuredContent=response,
    )


if INERT_MODE:
    mcp = FastMCP("V0.7 MCP Host Overhead Control")
    @mcp.tool(
        structured_output=False,
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def host_overhead_probe() -> str:
        """Inert host-overhead control; no repository or conversation context is returned."""
        return "This diagnostic tool returns no context."
else:
    mcp = context_mcp


if __name__ == "__main__":
    mcp.run(transport="stdio")

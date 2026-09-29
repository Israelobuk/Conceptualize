"""Fixture-backed MCP context capability for V0.8 benchmark v4."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from time import perf_counter
from uuid import uuid4

from conceptualize_mcp.server import CAPABILITY_INSTRUCTIONS, CONTEXT_TOOL_DESCRIPTION
from conceptualize_runtime.runtime import token_count
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations

from conceptualize_evaluation.v08_benchmark_v4 import compile_context, verify_freeze

TRACE_PATH = os.environ.get("V08_V4_MCP_TRACE")
if "--trace" in sys.argv:
    index = sys.argv.index("--trace")
    if index + 1 < len(sys.argv):
        TRACE_PATH = sys.argv[index + 1]

mcp = FastMCP("Conceptualize", instructions=CAPABILITY_INSTRUCTIONS)


@mcp.tool(structured_output=False, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def conceptualize_context(task: str) -> CallToolResult:
    """Augment the user's task with relevant prior context, then continue using normal tools."""
    started = perf_counter()
    fixture, _, freeze = verify_freeze()
    if task.strip() != fixture["question"].strip():
        raise ValueError("The fixture MCP accepts only the identical frozen benchmark task")
    package = compile_context(fixture)
    trace_id = str(uuid4())
    response = {"context": package["context"], "new_context_tokens": token_count(package["context"]),
                "previous_context_reused": False,
                "sources": package["metrics"].get("sources_represented", ["message"]),
                "trace_id": trace_id}
    if TRACE_PATH:
        Path(TRACE_PATH).write_text(json.dumps({
            "trace_id": trace_id, "fixture_sha256": freeze["fixture_sha256"],
            "ground_truth_sha256": freeze["ground_truth_sha256"], "task": task,
            "selected_context_tokens": response["new_context_tokens"],
            "metrics": package["metrics"], "timings_ms": package["timings_ms"],
            "elapsed_ms": round((perf_counter() - started) * 1000, 3),
            "selection": package["selection"], "working_context": package.get("working_context", []),
            "context": package["context"],
        }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return CallToolResult(content=[TextContent(type="text", text=json.dumps(response, separators=(",", ":")))],
                          structuredContent=response)


conceptualize_context.__doc__ = CONTEXT_TOOL_DESCRIPTION


if __name__ == "__main__":
    mcp.run(transport="stdio")

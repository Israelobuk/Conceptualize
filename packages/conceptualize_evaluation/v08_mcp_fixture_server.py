"""Fixture-backed MCP process for the isolated V0.8 activation evaluation."""

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

from conceptualize_evaluation.v08_economics import compile_context, verify_freeze

INERT_MODE = "--inert" in sys.argv
TRACE_PATH = os.environ.get("V08_MCP_TRACE_PATH")
if "--trace" in sys.argv:
    index = sys.argv.index("--trace")
    if index + 1 < len(sys.argv):
        TRACE_PATH = sys.argv[index + 1]

mcp = FastMCP(
    "V0.8 inert host control" if INERT_MODE else "Conceptualize",
    instructions=(
        "Read-only inert host-overhead probe; it does not supply context."
        if INERT_MODE else CAPABILITY_INSTRUCTIONS
    ),
)


if INERT_MODE:
    @mcp.tool(
        structured_output=False,
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def host_overhead_probe() -> str:
        """Inert host diagnostic; no project or conversation context is returned."""
        return "This diagnostic capability returns no context."
else:
    @mcp.tool(
        structured_output=False,
        annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False),
    )
    async def conceptualize_context(task: str) -> CallToolResult:
        """Context capability activated for a user's task. Pass the task itself to augment it with relevant prior decisions, constraints, relationships, changes, and work. Conceptualize returns a compact context delta; continue the task with normal reasoning and normal tools."""
        started = perf_counter()
        fixture, _, freeze = verify_freeze()
        if task.strip() != fixture["question"].strip():
            raise ValueError("The fixture server only accepts the frozen current task")
        package = compile_context(fixture)
        trace_id = str(uuid4())
        response = {
            "context": package["context"],
            "new_context_tokens": token_count(package["context"]),
            "previous_context_reused": False,
            "sources": package["metrics"].get("sources_represented", ["message"]),
            "trace_id": trace_id,
        }
        if TRACE_PATH:
            Path(TRACE_PATH).write_text(
                json.dumps({
                    "trace_id": trace_id,
                    "fixture_sha256": freeze["fixture_sha256"],
                    "ground_truth_sha256": freeze["ground_truth_sha256"],
                    "task": task,
                    "selected_context_tokens": response["new_context_tokens"],
                    "metrics": package["metrics"],
                    "timings_ms": package["timings_ms"],
                    "elapsed_ms": round((perf_counter() - started) * 1000, 3),
                    "selection": package["selection"],
                    "working_context": package.get("working_context", []),
                    "context": package["context"],
                }, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        return CallToolResult(
            content=[TextContent(type="text", text=json.dumps(response, separators=(",", ":")))],
            structuredContent=response,
        )

    conceptualize_context.__doc__ = CONTEXT_TOOL_DESCRIPTION


if __name__ == "__main__":
    mcp.run(transport="stdio")

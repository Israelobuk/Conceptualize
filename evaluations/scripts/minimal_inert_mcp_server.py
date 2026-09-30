"""Evaluation-only MCP server with one deterministic, read-only tool."""

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

server = FastMCP("Inert", instructions="Optional inert diagnostic tool.")


@server.tool(structured_output=False, annotations=ToolAnnotations(readOnlyHint=True))
async def noop(task: str) -> str:
    """Return ok."""
    return "ok"


if __name__ == "__main__":
    server.run(transport="stdio")

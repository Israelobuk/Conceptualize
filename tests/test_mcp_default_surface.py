"""Default stdio MCP registration exposes only the minimal context capability."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


def test_default_stdio_surface_has_one_task_only_tool() -> None:
    root = Path(__file__).resolve().parents[1]
    env = {
        **os.environ,
        "CONCEPTUALIZE_MCP_ADVANCED": "",
        "PYTHONPATH": os.pathsep.join(str(root / path) for path in ("apps/api", "apps/mcp", "packages")),
    }

    async def inspect_surface() -> None:
        params = StdioServerParameters(command=sys.executable, args=["-m", "conceptualize_mcp.server"], env=env)
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                listing = await session.list_tools()
                assert [tool.name for tool in listing.tools] == ["conceptualize_context"]
                tool = listing.tools[0]
                assert tool.inputSchema["required"] == ["task"]
                assert list(tool.inputSchema["properties"]) == ["task"]
                assert "normal tools" in tool.description
                assert (await session.list_resources()).resources == []
                assert (await session.list_prompts()).prompts == []

    asyncio.run(inspect_surface())

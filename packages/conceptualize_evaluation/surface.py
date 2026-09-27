"""Capture the real MCP surface; SDK reachability does not prove host visibility."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from time import perf_counter

from .runner import ROOT, write


def encoded(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()


def profile_surface(surface):
    tools = surface["tools"]
    return {"tools": len(tools), "description_characters": sum(len(t.get("description", "")) for t in tools),
            "schema_bytes": sum(len(encoded({"input": t.get("inputSchema"), "output": t.get("outputSchema")})) for t in tools),
            "tool_listing_bytes": len(encoded(tools)), "initialization_bytes": len(encoded(surface["initialization"])),
            "model_visible_tokens": None,
            "scope": "JSON serialization measurements; host prompt packing/token causality unavailable."}


async def capture(environment):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    parameters = StdioServerParameters(command=sys.executable, args=["-m", "conceptualize_mcp.server"],
                                       cwd=str(ROOT), env={**os.environ, **environment})
    started = perf_counter()
    async with stdio_client(parameters) as (read, output):
        async with ClientSession(read, output) as session:
            initialization = await session.initialize()
            initialized_ms = (perf_counter() - started) * 1000
            listing = await session.list_tools()
            resources = await session.list_resources()
            templates = await session.list_resource_templates()
            surface = {"registration_name": "conceptualize", "connected": True,
                       "connection_scope": "SDK stdio handshake; separate host reachability required",
                       "initialization": initialization.model_dump(mode="json", exclude_none=True),
                       "tools": [t.model_dump(mode="json", exclude_none=True) for t in listing.tools],
                       "resources": resources.model_dump(mode="json", exclude_none=True),
                       "resource_templates": templates.model_dump(mode="json", exclude_none=True),
                       "startup_and_initialize_ms": initialized_ms,
                       "discovery_complete_ms": (perf_counter() - started) * 1000,
                       "registration": {"command": sys.executable, "args": parameters.args,
                                        "api_url": environment.get("CONCEPTUALIZE_API_URL"),
                                        "credential": "environment variable; value not recorded"}}
            surface["profile"] = profile_surface(surface)
            return surface


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--environment-file", type=Path)
    args = parser.parse_args()
    environment = json.loads(args.environment_file.read_text()) if args.environment_file else {}
    result = asyncio.run(capture(environment))
    write(args.output, result)
    print(json.dumps(result["profile"]))


if __name__ == "__main__":
    main()

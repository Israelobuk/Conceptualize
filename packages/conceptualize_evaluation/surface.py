"""Capture the real MCP surface; SDK reachability does not prove host visibility."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from time import perf_counter

from conceptualize_runtime.runtime import token_count

from .runner import ROOT, write


def encoded(value):
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False).encode()


def profile_surface(surface):
    tools = surface["tools"]
    instructions = surface["initialization"].get("instructions") or ""
    schema = encoded(tools)
    init = encoded(surface["initialization"])
    resources = encoded({
        "resources": surface.get("resources", {}),
        "templates": surface.get("resource_templates", {}),
    })
    return {"tools": len(tools), "description_characters": sum(len(t.get("description", "")) for t in tools),
            "schema_bytes": sum(len(encoded({"input": t.get("inputSchema"), "output": t.get("outputSchema")})) for t in tools),
            "tool_listing_bytes": len(schema), "tool_listing_tokens_cl100k_estimate": token_count(schema.decode()),
            "initialization_bytes": len(init), "initialization_tokens_cl100k_estimate": token_count(init.decode()),
            "server_instruction_bytes": len(instructions.encode()),
            "server_instruction_tokens_cl100k_estimate": token_count(instructions),
            "capability_resource_bytes": len(resources),
            "capability_resource_tokens_cl100k_estimate": token_count(resources.decode()),
            "combined_serialized_bytes": len(schema) + len(init) + len(resources),
            "combined_token_estimate": token_count(schema.decode()) + token_count(init.decode()) + token_count(resources.decode()),
            "model_visible_tokens": None,
            "scope": "Local MCP handshake/listing/resource serialization tokenized with cl100k_base; host prompt packing and provider token accounting unavailable."}


async def capture(environment, python=sys.executable, advanced=False):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    server_environment = {**os.environ, **environment}
    if advanced:
        server_environment["CONCEPTUALIZE_MCP_ADVANCED"] = "true"
    else:
        server_environment.pop("CONCEPTUALIZE_MCP_ADVANCED", None)
    parameters = StdioServerParameters(command=python, args=["-m", "conceptualize_mcp.server"],
                                       cwd=str(ROOT), env=server_environment)
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
                       "registration": {"command": python, "args": parameters.args,
                                        "api_url": environment.get("CONCEPTUALIZE_API_URL"),
                                        "advanced": advanced,
                                        "credential": "environment variable; value not recorded"}}
            surface["profile"] = profile_surface(surface)
            return surface


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--environment-file", type=Path)
    parser.add_argument("--python", default=sys.executable)
    parser.add_argument("--advanced", action="store_true")
    args = parser.parse_args()
    environment = json.loads(args.environment_file.read_text()) if args.environment_file else {}
    result = asyncio.run(capture(environment, args.python, args.advanced))
    write(args.output, result)
    print(json.dumps(result["profile"]))


if __name__ == "__main__":
    main()

"""Profile actual stdio -> HTTP -> runtime calls; no agent/model involved."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path
from time import perf_counter

from conceptualize_runtime.git import metadata
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .runner import ROOT, new_project, write


async def profile(args):
    git_started = perf_counter()
    git_info = metadata(ROOT / "evaluations/fixture")
    git_analysis_ms = (perf_counter() - git_started) * 1000
    started = perf_counter()
    project, key = new_project(ROOT / "evaluations/fixture", "Runtime overhead profile")
    indexing_ms = (perf_counter() - started) * 1000
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "conceptualize_mcp.server"],
        env={**os.environ, "CONCEPTUALIZE_API_KEY": key, "CONCEPTUALIZE_API_URL": args.api_url},
    )
    rows = []
    startup = perf_counter()
    async with stdio_client(params) as (read, send):
        async with ClientSession(read, send) as client:
            await client.initialize()
            startup_ms = (perf_counter() - startup) * 1000
            operations = [
                ("conceptualize_map", {"token_budget": 2000}),
                ("conceptualize_expand", {"target": "shop/contracts.py", "level": "structure"}),
                ("conceptualize_dependencies", {"target": "shop/contracts.py"}),
                ("conceptualize_expand", {"target": "shop/contracts.py"}),
                (
                    "conceptualize_pack",
                    {
                        "task": "change shared receipt interface",
                        "paths": ["shop/contracts.py"],
                        "token_budget": 2000,
                    },
                ),
                (
                    "conceptualize_pack",
                    {
                        "task": "change shared receipt interface",
                        "paths": ["shop/contracts.py"],
                        "token_budget": 2000,
                    },
                ),
            ]
            for name, inputs in operations:
                start = perf_counter()
                result = await client.call_tool(name, inputs)
                elapsed = (perf_counter() - start) * 1000
                payload = result.structuredContent or {}
                rows.append(
                    {
                        "tool": name,
                        "wall_ms": round(elapsed, 3),
                        "error": result.isError,
                        "response_json_bytes": len(json.dumps(payload).encode()),
                        "timings_ms": payload.get("timings_ms"),
                        "metrics": payload.get("metrics"),
                    }
                )
    write(
        args.output,
        {
            "project_id": project,
            "indexing_ms": indexing_ms,
            "git_analysis_ms": git_analysis_ms,
            "git_available": git_info["available"],
            "stdio_startup_ms": startup_ms,
            "calls": rows,
            "scope": "Local fixture, SQLite QA database. Redis availability comes from environment. HTTP round-trip includes server stages and client construction. Graph build is part of snapshot_and_graph; stages overlap. Git analysis happens during indexing, not per MCP operation. No model involved.",
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-url", default="http://127.0.0.1:8039")
    parser.add_argument("--output", type=Path, required=True)
    asyncio.run(profile(parser.parse_args()))


if __name__ == "__main__":
    main()

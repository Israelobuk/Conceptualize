import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def verify(command: str, url: str) -> dict:
    params = StdioServerParameters(
        command=command,
        args=["-m", "conceptualize_mcp.server"],
        env={**os.environ, "CONCEPTUALIZE_API_URL": url},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            expected = {
                "conceptualize_" + op for op in ("map", "search", "dependencies", "expand", "pack")
            }
            if {t.name for t in tools} != expected:
                raise ValueError("Server did not expose the five expected tools")
            response = await session.call_tool("conceptualize_map", {"token_budget": 1000})
            if response.isError:
                raise ValueError("Map failed; verify API, key and indexed project")
            data = response.structuredContent
            return {
                "tools": sorted(expected),
                "map_trace_id": data["trace_id"],
                "indexed_files_returned": data["included_files"],
                "index": data.get("index"),
                "budget_respected": data["metrics"]["returned_tokens"] <= 1000,
            }


def main():
    parser = argparse.ArgumentParser(
        description="Print MCP client configuration or verify the real stdio connection. Key is read from the environment, never printed."
    )
    parser.add_argument("action", choices=["config", "doctor"])
    parser.add_argument("--format", choices=["json", "codex"], default="json")
    parser.add_argument(
        "--api-url", default=os.environ.get("CONCEPTUALIZE_API_URL", "http://127.0.0.1:8000")
    )
    args = parser.parse_args()
    command = str(Path(sys.executable).resolve())
    if args.action == "doctor":
        try:
            print(json.dumps(asyncio.run(verify(command, args.api_url)), indent=2))
        except Exception as exc:
            parser.exit(1, f"MCP verification failed: {exc}\n")
    elif args.format == "json":
        print(
            json.dumps(
                {
                    "mcpServers": {
                        "conceptualize": {
                            "command": command,
                            "args": ["-m", "conceptualize_mcp.server"],
                            "env": {
                                "CONCEPTUALIZE_API_URL": args.api_url,
                                "CONCEPTUALIZE_API_KEY": "REPLACE_WITH_PROJECT_KEY",
                            },
                        }
                    }
                },
                indent=2,
            )
        )
    else:
        print(
            "[mcp_servers.conceptualize]\ncommand = "
            + json.dumps(command)
            + '\nargs = ["-m", "conceptualize_mcp.server"]\nenv_vars = ["CONCEPTUALIZE_API_KEY"]\n\n[mcp_servers.conceptualize.env]\nCONCEPTUALIZE_API_URL = '
            + json.dumps(args.api_url)
        )


if __name__ == "__main__":
    main()

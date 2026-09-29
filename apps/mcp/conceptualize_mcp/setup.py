import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

PRIMARY_TOOLS = frozenset({"conceptualize_context"})
ADVANCED_TOOLS = frozenset(
    {
        "conceptualize_map",
        "conceptualize_search",
        "conceptualize_dependencies",
        "conceptualize_expand",
        "conceptualize_pack",
        "conceptualize_inspect",
    }
)


async def verify(command: str, url: str, advanced: bool = False) -> dict:
    env = {**os.environ, "CONCEPTUALIZE_API_URL": url}
    if advanced:
        env["CONCEPTUALIZE_MCP_ADVANCED"] = "true"
    params = StdioServerParameters(
        command=command,
        args=["-m", "conceptualize_mcp.server"],
        env=env,
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            tools = (await session.list_tools()).tools
            expected = PRIMARY_TOOLS | ADVANCED_TOOLS if advanced else PRIMARY_TOOLS
            if {t.name for t in tools} != expected:
                raise ValueError("Server tool surface differs from the requested profile")
            response = await session.call_tool(
                "conceptualize_context", {"task": "current project context"}
            )
            if response.isError:
                raise ValueError("Context retrieval failed; verify API, key and indexed project")
            data = response.structuredContent
            return {
                "tools": sorted(expected),
                "context_trace_id": data["trace_id"],
                "sources_returned": data.get("sources", []),
                "new_context_tokens": data["new_context_tokens"],
            }


def main():
    parser = argparse.ArgumentParser(
        description="Print MCP client configuration or verify the real stdio connection. Key is read from the environment, never printed."
    )
    parser.add_argument("action", choices=["config", "doctor"])
    parser.add_argument("--format", choices=["json", "codex"], default="json")
    parser.add_argument("--advanced", action="store_true", help="Expose legacy retrieval/debug tools too")
    parser.add_argument(
        "--api-url", default=os.environ.get("CONCEPTUALIZE_API_URL", "http://127.0.0.1:8000")
    )
    args = parser.parse_args()
    command = str(Path(sys.executable).resolve())
    if args.action == "doctor":
        try:
            print(json.dumps(asyncio.run(verify(command, args.api_url, args.advanced)), indent=2))
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
                                **({"CONCEPTUALIZE_MCP_ADVANCED": "true"} if args.advanced else {}),
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
            + ('\nCONCEPTUALIZE_MCP_ADVANCED = "true"' if args.advanced else '')
        )


if __name__ == "__main__":
    main()

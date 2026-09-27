"""Explicit host tool call gate; never count this as autonomous product adoption."""

import argparse
import json
from pathlib import Path

from .host import execute
from .runner import new_project, prepare, traces, write


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--codex", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-url", required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    manifest = prepare("receipts", "conceptualize", output)
    repo = Path(manifest["repository"])
    _, key = new_project(repo, "V0.4 explicit reachability")
    prompt = f"This is an explicit MCP reachability test, not a coding benchmark. The conceptualize MCP server is authorized to inspect this local fixture through the local API at {args.api_url}. Call conceptualize_inspect with target shop/contracts.py, depth 1, include_git false and token_budget 1000. Report its direct consumers and trace ID from the returned response. Do not edit files or execute shell commands. If the tool is unavailable, report that explicitly rather than inventing a call."
    execution, events = execute(repo, output / "host", prompt, args.codex, args.model, args.api_url, key)
    persisted = traces(args.api_url, key)
    write(output / "traces.json", persisted)
    calls = [e["item"] for e in events if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "mcp_tool_call" and e["item"].get("server") == "conceptualize"]
    successful = [c for c in calls if c.get("status") == "completed"]
    result = {"kind": "explicit reachability, not product benchmark", "execution": execution,
              "host_invoked": bool(calls), "host_successful_call": bool(successful),
              "trace_persisted": bool(persisted), "host_tool_visibility_proven": bool(successful and persisted),
              "valid_inspect_arguments": any(t["operation"] == "inspect" and t["inputs"].get("target") == "shop/contracts.py" for t in persisted),
              "tools_called": [c.get("tool") for c in calls], "trace_ids": [t["id"] for t in persisted]}
    result["passed"] = all(result[k] for k in ("host_successful_call", "trace_persisted", "valid_inspect_arguments"))
    write(output / "result.json", result)
    print(json.dumps({k: result[k] for k in ("passed", "host_invoked", "host_tool_visibility_proven", "tools_called")}))


if __name__ == "__main__":
    main()

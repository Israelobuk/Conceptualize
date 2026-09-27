"""Unused-connection experiment, separate from repository task benchmarks."""
import argparse
import json
from pathlib import Path

from .host import execute
from .runner import new_project, prepare, write


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--codex", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--repetitions", type=int, default=4)
    args = parser.parse_args()
    output = args.output.resolve()
    manifest = prepare("receipts", "control", output)
    repo = Path(manifest["repository"])
    _, key = new_project(repo, "Unused connection baseline")
    rows = []
    prompt = "What is 17 + 25? Answer with the integer only."
    for repetition in range(args.repetitions):
        order = ["control", "connected"] if repetition % 2 == 0 else ["connected", "control"]
        for mode in order:
            result, events = execute(repo, output / f"{repetition}-{mode}", prompt,
                                     args.codex, args.model, args.api_url,
                                     key if mode == "connected" else None, timeout=180)
            calls = [e for e in events if e.get("item", {}).get("type") == "mcp_tool_call"]
            messages = [e["item"].get("text", "").strip() for e in events
                        if e.get("type") == "item.completed" and e.get("item", {}).get("type") == "agent_message"]
            rows.append({"repetition": repetition, "mode": mode, "order": order,
                         "execution": result, "answer_correct": bool(messages and messages[-1] == "42"),
                         "mcp_calls": len(calls), "unused_connection": mode == "connected" and not calls,
                         "causal_overhead_attribution": None})
            write(output / "results.json", rows)
            print(json.dumps({"repetition": repetition, "mode": mode, "elapsed_seconds": result["elapsed_seconds"], "mcp_calls": len(calls)}), flush=True)


if __name__ == "__main__":
    main()

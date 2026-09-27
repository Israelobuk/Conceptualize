"""Scripted protocol measurements, explicitly separate from agent evaluations."""

import argparse
import asyncio
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

from .runner import ROOT, new_project, write

STAGES = ("transport_ms", "index_lookup_ms", "graph_ms", "git_ms", "scoring_ms",
          "packing_ms", "cache_ms", "trace_write_ms", "total_runtime_ms")


def stage_statistics(rows):
    result = {}
    for stage in STAGES:
        values = sorted(row.get("overhead", {}).get(stage) for row in rows
                        if isinstance(row.get("overhead", {}).get(stage), (int, float)))
        result[stage] = {"count": len(values), "missing": len(rows) - len(values),
                         "p50": values[math.ceil(len(values) * .5) - 1] if values else None,
                         "p95": values[math.ceil(len(values) * .95) - 1] if values else None}
    return result


def make_scale(root, size):
    if root.exists():
        raise ValueError("Preserve existing evidence; destination must be new")
    shutil.copytree(ROOT / "evaluations/fixture", root,
                    ignore=shutil.ignore_patterns("__pycache__", ".pytest_cache"))
    original = len(list(root.rglob("*.py")))
    if size <= original:
        raise ValueError("Requested size must exceed the baseline fixture")
    (root / "consumers").mkdir()
    for number in range(size - original):
        (root / "consumers" / f"c{number:04}.py").write_text(
            "from shop.contracts import Receipt\n\n\n"
            "def amount(receipt: Receipt) -> float:\n    return receipt.total\n",
            encoding="utf-8")


async def session_calls(repo, key, url, targets):
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    env = {**os.environ, "CONCEPTUALIZE_API_KEY": key, "CONCEPTUALIZE_API_URL": url}
    env.pop("CONCEPTUALIZE_SESSION_ID", None)
    params = StdioServerParameters(command=sys.executable,
                                  args=["-m", "conceptualize_mcp.server"],
                                  env=env, cwd=str(ROOT))
    started = time.perf_counter()
    rows = []
    async with stdio_client(params) as (read, output):
        async with ClientSession(read, output) as session:
            await session.initialize()
            startup_ms = (time.perf_counter() - started) * 1000
            for target, modify in targets:
                if modify:
                    path = repo / "shop/contracts.py"
                    path.write_text(path.read_text(encoding="utf-8") + "\n# Change freshness probe\n", encoding="utf-8")
                begun = time.perf_counter()
                response = await session.call_tool("conceptualize_inspect", {
                    "target": target, "depth": 1, "token_budget": 4000,
                    "include_git": False})
                payload = response.structuredContent or {}
                rows.append({"target": target, "modified_before_call": modify,
                             "error": response.isError, "response": payload,
                             "error_content": [c.model_dump() for c in response.content] if response.isError else None,
                             "overhead": payload.get("overhead", {}),
                             "roundtrip_ms": (time.perf_counter() - begun) * 1000,
                             "response_bytes": len(json.dumps(payload).encode()),
                             "startup_ms": startup_ms if len(rows) == 0 else None})
    return rows


async def benchmark(output, url, sizes):
    if output.exists():
        raise ValueError("Preserve existing evidence; output must be new")
    output.mkdir(parents=True)
    records = []
    targets = [("shop/contracts.py", False), ("shop/checkout.py", False),
               ("shop/contracts.py", False), ("shop/contracts.py", True)]
    for size in sizes:
        for mode in ("cold", "warm"):
            repo = output / f"{size}-{mode}"
            make_scale(repo, size)
            _, key = new_project(repo, f"protocol-v03-{size}-{mode}")
            rows = []
            if mode == "warm":
                rows = await session_calls(repo, key, url, targets)
            else:
                for target in targets:
                    rows.extend(await session_calls(repo, key, url, [target]))
            record = {"size_python_files": size, "mode": mode, "rows": rows,
                      "stages": stage_statistics(rows), "subject": "scripted MCP client; no agent"}
            write(output / f"{size}-{mode}.json", record)
            records.append(record)
    write(output / "summary.json", {"records": records,
        "limitations": ["Scripted calls do not measure agent task success or exploration.",
                        "Transport is an HTTP client residual, not pure wire latency.",
                        "Stage timers are approximate; roundtrip includes serialization.",
                        "Sequential order and shared host activity can affect latency."]})


def render_report(directory, destination):
    summary = json.loads((directory / "summary.json").read_text(encoding="utf-8"))
    records = []
    for record in summary["records"]:
        rows = []
        for row in record["rows"]:
            response = row["response"]
            rows.append({k: row.get(k) for k in ("target", "modified_before_call", "error", "error_content", "roundtrip_ms", "response_bytes", "startup_ms", "overhead")}
                        | {"metrics": response.get("metrics", {}), "manifest": response.get("manifest"),
                           "invalidated_ids": len(response.get("invalidations", []))})
        records.append({"size": record["size_python_files"], "mode": record["mode"], "rows": rows, "stages": record["stages"]})
    stages = stage_statistics([row for record in records for row in record["rows"]])
    write(destination.with_suffix(".json"), {"records": records, "stages": stages, "limitations": summary["limitations"]})
    lines = ["# Protocol scale profile", "", "Scripted real MCP client; no agent/model. Four calls per condition. Budgets apply to compiled context, not full response metadata. Separate profiles do not demonstrate agent speed improvement.", "",
             "| Python files | Session | Errors | Roundtrip ms | JSON bytes | Duplicate tokens avoided |",
             "|---:|---|---:|---|---|---|"]
    for record in records:
        rows = record["rows"]
        lines.append(f"| {record['size']} | {record['mode']} | {sum(r['error'] for r in rows)} | "
                     + ", ".join(str(round(r["roundtrip_ms"])) for r in rows) + " | "
                     + ", ".join(str(r["response_bytes"]) for r in rows) + " | "
                     + ", ".join(str(r["metrics"].get("duplicate_tokens_avoided")) for r in rows) + " |")
    lines += ["", "## Stage percentiles", "", "Nearest-rank P50/P95 across these calls; per-condition distributions and missing counts remain in JSON.", "",
              "| Stage | Count | Missing | P50 ms | P95 ms |", "|---|---:|---:|---:|---:|"]
    lines += [f"| {key} | {value['count']} | {value['missing']} | {value['p50']} | {value['p95']} |" for key, value in stages.items()]
    lines += ["", *summary["limitations"], "", "Raw response directory: " + str(directory)]
    destination.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--sizes", type=int, nargs="+", default=[60, 400, 2000])
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    asyncio.run(benchmark(args.output.resolve(), args.api_url, args.sizes))
    if args.report:
        render_report(args.output.resolve(), args.report)


if __name__ == "__main__":
    main()

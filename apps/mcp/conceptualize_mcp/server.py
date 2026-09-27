import json
import os
from contextlib import asynccontextmanager
from time import perf_counter
from uuid import uuid4

import httpx
from conceptualize_shared.contracts import ContextResponse
from dotenv import load_dotenv
from mcp.server.fastmcp import Context, FastMCP
from mcp.types import CallToolResult, TextContent, ToolAnnotations
from pydantic import ValidationError

load_dotenv()


@asynccontextmanager
async def lifespan(server):
    async with httpx.AsyncClient(timeout=60) as http:
        yield {"http": http}


def compact_response(payload):
    """Only next-decision context crosses MCP; the API trace retains all evidence."""
    metrics = payload["metrics"]
    result = {"operation": payload.get("operation"), "context": payload.get("context", ""),
              "included_files": payload.get("included_files", []), "trace_id": payload["trace_id"],
              "metrics": {k: metrics[k] for k in ("returned_tokens", "token_budget", "new_context_tokens", "previously_supplied_tokens") if k in metrics}}
    if payload.get("context_id"):
        result["context_id"] = payload["context_id"]
    if payload.get("manifest"):
        result["manifest"] = payload["manifest"]
    if payload.get("environment"):
        result["environment"] = {k: paths[:16] for k, paths in payload["environment"].items()}
        result["environment_more"] = {k: len(paths) - 16 for k, paths in payload["environment"].items() if len(paths) > 16}
    elif payload.get("relationships"):
        result["relationships"] = [{k: edge[k] for k in ("source", "target", "kind", "heuristic") if k in edge}
                                   for edge in payload["relationships"][:16]]
        if len(payload["relationships"]) > 16:
            result["relationships_more"] = len(payload["relationships"]) - 16
    previous = payload.get("previous_context", [])
    if previous:
        result["previous_context"] = [{k: unit[k] for k in ("path", "level", "ranges", "context_id", "supplied_in_operation", "unchanged") if k in unit} for unit in previous[:32]]
        if len(previous) > 32:
            result["previous_context_more"] = len(previous) - 32
    if payload.get("invalidations"):
        result["invalidations"] = [{k: unit[k] for k in ("context_id", "changed_files") if k in unit} for unit in payload["invalidations"]]
    result["trace"] = "/v1/traces/" + payload["trace_id"]
    return result


mcp = FastMCP(
    "Conceptualize",
    lifespan=lifespan,
    instructions="Read-only indexed repository context. Known cross-file target: inspect; unknown location: map/search; precise impact question: dependencies; deepen a result: expand; known source set still needed: pack. Inspect shared types, APIs, configuration, auth or persistence to find hidden consumers/tests before editing. Skip isolated edits and already loaded source. No mandatory tool chain. Unchanged context is referenced; force_refresh resends it if your host lost context. Full diagnostics stay in traces. Compact index counts are available at conceptualize://capabilities.",
)
SESSION_ID = os.getenv("CONCEPTUALIZE_SESSION_ID") or str(uuid4())


async def call(operation: str, inputs: dict, ctx: Context | None = None) -> CallToolResult:
    key = os.getenv("CONCEPTUALIZE_API_KEY", "")
    if not key.startswith("cx_"):
        raise ValueError("Configure CONCEPTUALIZE_API_KEY with your project key")
    client = "mcp"
    if ctx:
        try:
            params = ctx.session.client_params
            if params and params.clientInfo:
                client = params.clientInfo.name
        except AttributeError:
            pass
    headers = {
        "Authorization": f"Bearer {key}",
        "X-MCP-Client": client[:200],
        "X-MCP-Session": SESSION_ID,
    }
    started = perf_counter()
    try:

        async def post(http):
            return await http.post(
                os.getenv("CONCEPTUALIZE_API_URL", "http://127.0.0.1:8000").rstrip("/")
                + "/v1/runtime",
                headers=headers,
                json={"operation": operation, **inputs},
            )

        if ctx:
            response = await post(ctx.request_context.lifespan_context["http"])
        else:
            async with httpx.AsyncClient(timeout=60) as http:
                response = await post(http)
        if response.status_code == 401:
            raise ValueError("Conceptualize API key is invalid or revoked")
        if response.status_code >= 400:
            raise ValueError(
                f"Conceptualize API returned HTTP {response.status_code}; inspect API logs"
            )
        try:
            payload = response.json()
            payload.setdefault("timings_ms", {})["mcp_http_round_trip"] = round(
                (perf_counter() - started) * 1000, 3
            )
            overhead = payload.setdefault("overhead", {})
            overhead["transport_ms"] = round(
                max(0, (perf_counter() - started) * 1000 - overhead.get("total_runtime_ms", 0)), 3
            )
            overhead["transport_scope"] = (
                "HTTP/client residual; includes serialization, not pure network or stdio startup"
            )
            ContextResponse.model_validate(payload)
            agent_response = compact_response(payload)
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(agent_response, separators=(",", ":")))], structuredContent=agent_response)
        except (ValueError, ValidationError) as exc:
            raise ValueError("Conceptualize API returned an invalid context response") from exc
    except httpx.HTTPError as exc:
        raise ValueError(
            "Cannot reach Conceptualize API; verify it is running and the URL is correct"
        ) from exc


@mcp.tool(structured_output=False, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def conceptualize_map(
    path: str = "", token_budget: int = 2000, force_refresh: bool = False, ctx: Context = None
) -> CallToolResult:
    """Orient in an unfamiliar or large repository when the relevant subsystem is unknown. Scope to a directory when possible. Do not call automatically for a known target; use inspect instead."""
    return await call(
        "map", {"path": path, "token_budget": token_budget, "force_refresh": force_refresh}, ctx
    )


@mcp.tool(structured_output=False, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def conceptualize_search(
    query: str,
    token_budget: int = 3000,
    limit: int = 30,
    force_refresh: bool = False,
    ctx: Context = None,
) -> CallToolResult:
    """Locate an unknown file or symbol using an exact identifier or text. Lexical lookup, not semantic search. For surroundings of a known target use inspect; for a trivial grep, normal text search may suffice."""
    return await call(
        "search",
        {
            "query": query,
            "token_budget": token_budget,
            "limit": limit,
            "force_refresh": force_refresh,
        },
        ctx,
    )


@mcp.tool(structured_output=False, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def conceptualize_dependencies(
    target: str, token_budget: int = 3000, force_refresh: bool = False, ctx: Context = None
) -> CallToolResult:
    """Answer a specific change-impact question: imports, reverse consumers, referenced symbols and tests around a file or symbol. Use inspect for a broader starting context; avoid repeating relationships already supplied."""
    return await call(
        "dependencies",
        {"target": target, "token_budget": token_budget, "force_refresh": force_refresh},
        ctx,
    )


@mcp.tool(structured_output=False, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def conceptualize_expand(
    target: str,
    token_budget: int = 4000,
    level: str = "source",
    force_refresh: bool = False,
    ctx: Context = None,
) -> CallToolResult:
    """Read a precise file or symbol identified by an earlier result. Choose structure for signatures/relations or source for implementation. Unchanged ranges return references; force_refresh resends when host context was lost."""
    return await call(
        "expand",
        {
            "target": target,
            "token_budget": token_budget,
            "level": level,
            "force_refresh": force_refresh,
        },
        ctx,
    )


@mcp.tool(structured_output=False, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def conceptualize_pack(
    paths: list[str],
    token_budget: int = 8000,
    include_dependencies: bool = True,
    include_tests: bool = True,
    include_consumers: bool = True,
    force_refresh: bool = False,
    score_weights: dict[str, int] | None = None,
    ctx: Context = None,
) -> CallToolResult:
    """Assemble bounded implementation source after relevant entities are known. Include consumers/tests by default. Skip if sufficient source is already loaded; do not run a mandatory map/search/dependencies/pack sequence. Full selection evidence stays in the trace."""
    return await call(
        "pack",
        {
            "paths": paths,
            "token_budget": token_budget,
            "include_dependencies": include_dependencies,
            "include_tests": include_tests,
            "include_consumers": include_consumers,
            "force_refresh": force_refresh,
            "score_weights": score_weights or {},
        },
        ctx,
    )


@mcp.tool(structured_output=False, annotations=ToolAnnotations(readOnlyHint=True, destructiveHint=False))
async def conceptualize_inspect(
    target: str,
    depth: int = 1,
    include_dependencies: bool = True,
    include_consumers: bool = True,
    include_tests: bool = True,
    include_git: bool = True,
    token_budget: int = 4000,
    manifest_only: bool = False,
    force_refresh: bool = False,
    ctx: Context = None,
) -> CallToolResult:
    """Preferred entry for a known file, symbol, shared type, interface, configuration, authentication or persistence target whose change may affect other files. Finds dependencies, hidden consumers and tests plus bounded source before editing. Skip isolated one-file edits, exact source already loaded or simple textual lookups. manifest_only shows costs/structure first; depth controls scope."""
    return await call(
        "inspect",
        {
            "target": target,
            "depth": depth,
            "include_dependencies": include_dependencies,
            "include_consumers": include_consumers,
            "include_tests": include_tests,
            "include_git": include_git,
            "token_budget": token_budget,
            "manifest_only": manifest_only,
            "force_refresh": force_refresh,
        },
        ctx,
    )


@mcp.resource("conceptualize://capabilities", description="Compact indexed file/symbol counts and repository context capabilities; no source or map is injected.")
async def repository_capabilities() -> dict:
    key = os.getenv("CONCEPTUALIZE_API_KEY", "")
    async with httpx.AsyncClient(timeout=3) as http:
        response = await http.get(os.getenv("CONCEPTUALIZE_API_URL", "http://127.0.0.1:8000").rstrip("/") + "/v1/overview",
                                  headers={"Authorization": "Bearer " + key})
    response.raise_for_status()
    data = response.json()
    return {"indexed_files": data["indexed_files"], "indexed_symbols": data["indexed_symbols"],
            "available": ["structure", "consumers", "tests", "git", "bounded source", "session deltas"],
            "use": "Inspect shared or cross-file targets before modification; skip isolated edits."}


def main():
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

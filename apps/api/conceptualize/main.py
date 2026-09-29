import hashlib
import json
import logging
import re
import time
from pathlib import Path
from typing import Literal

from conceptualize_shared.contracts import CompiledContext, ContextResponse
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from opentelemetry.trace import Status, StatusCode
from pydantic import BaseModel, Field, ValidationError, model_validator
from sqlalchemy import Integer, func, select, text
from sqlalchemy.exc import SQLAlchemyError

from .auth import authenticate
from .cache import cache
from .config import settings
from .db import get_db
from .models import (
    ContextRequest,
    ContextResult,
    ContextUnitRecord,
    McpSession,
    Project,
    Repository,
    now,
)
from .service import index_project, project_runtime, source_freshness
from .telemetry import tracer

log = logging.getLogger(__name__)
logging.basicConfig(level=getattr(logging, settings.log_level))
app = FastAPI(
    title="Conceptualize",
    version="0.8.0",
    docs_url="/docs" if settings.app_env == "development" else None,
    redoc_url="/redoc" if settings.app_env == "development" else None,
    openapi_url="/openapi.json" if settings.app_env == "development" else None,
)


class OperationInput(BaseModel):
    operation: Literal["context", "map", "search", "dependencies", "expand", "pack", "inspect"]
    path: str = Field(default="", max_length=1000)
    target: str = Field(default="", max_length=1000)
    query: str = Field(default="", max_length=4000)
    paths: list[str] = Field(default_factory=list, max_length=50)
    token_budget: int = Field(default=4000, ge=1, le=64000)
    depth: int = Field(default=1, ge=0, le=3)
    include_git: bool = True
    manifest_only: bool = False
    include_dependencies: bool = True
    include_tests: bool = True
    include_consumers: bool = True
    limit: int = Field(default=30, ge=1, le=100)
    level: Literal["map", "structure", "source", "pack"] | None = None
    force_refresh: bool = False
    score_weights: dict[str, int] = Field(default_factory=dict, max_length=30)
    source_types: list[str] | None = Field(default=None, max_length=5)

    @model_validator(mode="after")
    def validate_operation(self):
        if self.operation == "search" and not self.query.strip():
            raise ValueError("search requires a query")
        if self.operation in {"expand", "dependencies", "inspect"} and not self.target.strip():
            raise ValueError("target is required")
        if self.operation == "pack" and not self.paths and not self.query.strip():
            raise ValueError("pack requires paths or query")
        if any(len(p) > 1000 for p in self.paths):
            raise ValueError("path too long")
        allowed_sources = {"repository", "repository_file", "code_symbol", "conversation", "message"}
        if self.source_types is not None and (
            not self.source_types or set(self.source_types) - allowed_sources
        ):
            raise ValueError("source_types must name repository or conversation sources")
        from conceptualize_runtime.scoring import DEFAULT_WEIGHTS

        if set(self.score_weights) - set(DEFAULT_WEIGHTS) or any(
            abs(v) > 1000 for v in self.score_weights.values()
        ):
            raise ValueError("Invalid score weights")
        return self


class IndexInput(BaseModel):
    path: str = Field(min_length=1, max_length=4096)
    base: str | None = Field(default=None, max_length=200)


@app.exception_handler(SQLAlchemyError)
async def database_error(request, exc):
    log.exception("Database operation failed", exc_info=exc)
    return JSONResponse(
        status_code=503, content={"detail": "Database unavailable; check service and migrations"}
    )


@app.get("/health")
def health(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"status": "ok"}


@app.post("/v1/runtime", response_model=ContextResponse)
def operate(
    body: OperationInput,
    project: Project = Depends(authenticate),
    db=Depends(get_db),
    x_mcp_client: str = Header(default="api", max_length=200),
    x_mcp_session: str | None = Header(default=None, max_length=200),
):
    started = time.perf_counter()
    inputs = body.model_dump()
    # Serialize index updates and context snapshots for one project. Also avoids session insert races.
    project = db.scalar(
        select(Project)
        .where(Project.id == project.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    registered = db.scalar(select(Repository).where(Repository.project_id == project.id))
    requested_sources = set(body.source_types or [])
    if body.operation == "context" and body.source_types is None:
        aliases = re.compile(
            r"\b(previous|earlier|history|conversation|we(?:'ve| have)? decided|"
            r"prior decision|last time|superseded)\b",
            re.I,
        )
        conversation_available = db.scalar(
            select(func.count()).select_from(ContextUnitRecord).where(
                ContextUnitRecord.project_id == project.id,
                ContextUnitRecord.source_type.in_(["conversation", "message"]),
            )
        ) > 0
        if aliases.search(body.query) and conversation_available:
            requested_sources = {"conversation"}
            if registered and re.search(r"(?:[\w.-]+/)+[\w.-]+|\b(?:file|module|symbol|implementation|code|tests?)\b", body.query, re.I):
                requested_sources.add("repository")
        elif registered:
            requested_sources = {"repository"}
        elif conversation_available:
            requested_sources = {"conversation"}
    elif body.source_types is None:
        requested_sources = {"repository"}
    repository_requested = bool(requested_sources & {"repository", "repository_file", "code_symbol"})
    refresh_started = time.perf_counter()
    refresh = source_freshness.refresh(
        db,
        project,
        requested_sources,
        force_refresh=body.force_refresh,
        source_snapshots={"repository": registered} if registered else {},
    )
    refresh_ms = (time.perf_counter() - refresh_started) * 1000
    session = None
    history = []
    if x_mcp_session:
        session = db.scalar(
            select(McpSession)
            .where(McpSession.project_id == project.id, McpSession.session_id == x_mcp_session)
            .with_for_update()
        )
        if session:
            history = (session.context_state or {}).get("deliveries", [])
    with tracer.start_as_current_span(f"context.{body.operation}") as span:
        span.set_attribute("project.id", project.id)
        span.set_attribute("context.operation", body.operation)
        span.set_attribute("context.token_budget", body.token_budget)
        span.set_attribute("mcp.client", x_mcp_client)
        if x_mcp_session:
            span.set_attribute("mcp.session", x_mcp_session)
        repository = db.scalar(select(Repository).where(Repository.project_id == project.id))
        state = repository.state_hash if repository else "empty"
        fingerprint = hashlib.sha256(
            json.dumps({"inputs": inputs, "session_history": history}, sort_keys=True).encode()
        ).hexdigest()
        key = f"cx:v4:{project.id}:{project.revision}:{state}:{fingerprint}"
        cache_started = time.perf_counter()
        result = cache.get(key)
        cache_ms = (time.perf_counter() - cache_started) * 1000
        hit = False
        if result is not None:
            try:
                result = CompiledContext.model_validate(result).model_dump()
                hit = result["metrics"]["returned_tokens"] <= body.token_budget
            except ValidationError:
                log.warning("Invalid cached context schema; recomputing")
        status = "success"
        try:
            if not hit:
                snapshot_started = time.perf_counter()
                if repository_requested:
                    runtime, _ = project_runtime(db, project.id)
                else:
                    from conceptualize_runtime.runtime import ContextRuntime

                    runtime = ContextRuntime({})
                snapshot_ms = (time.perf_counter() - snapshot_started) * 1000
                repository_only = requested_sources in ({"repository"}, {"repository_file"})
                if body.operation == "context" or (body.source_types is not None and not repository_only and body.operation != "dependencies"):
                    source_load_started = time.perf_counter()
                    from conceptualize_runtime.adapters import RepositoryAdapter
                    from conceptualize_runtime.context import ContextUnit

                    aliases = {
                        "repository": {"repository_file", "code_symbol"},
                        "conversation": {"conversation", "message"},
                    }
                    source_types = set().union(
                        *(aliases.get(source, {source}) for source in requested_sources)
                    )
                    units = []
                    if repository_requested and source_types.intersection({"repository_file", "code_symbol"}):
                        units.extend(RepositoryAdapter().adapt(runtime.files, runtime.graph))
                    rows = db.scalars(
                        select(ContextUnitRecord).where(
                            ContextUnitRecord.project_id == project.id,
                            ContextUnitRecord.source_type.in_(source_types),
                        )
                    )
                    units.extend(
                        ContextUnit(
                            id=row.unit_id,
                            source_type=row.source_type,
                            source_id=row.source_id,
                            parent_id=row.parent_id,
                            content=row.content,
                            content_hash=row.content_hash,
                            version=row.version,
                            token_count=row.token_count,
                            created_at=row.created_at,
                            updated_at=row.updated_at,
                            relationships=row.relationships,
                            metadata=row.metadata_json,
                        )
                        for row in rows
                    )
                    source_load_ms = (time.perf_counter() - source_load_started) * 1000
                    raw_result = runtime.execute_context_units(body.operation, {**inputs, "_history": history}, units)
                    raw_result.setdefault("timings_ms", {})["context_source_load"] = round(
                        source_load_ms, 3
                    )
                else:
                    raw_result = runtime.execute(body.operation, {**inputs, "_history": history})
                result = CompiledContext.model_validate(
                    raw_result
                ).model_dump()
                result.setdefault("timings_ms", {})["snapshot_and_graph"] = round(snapshot_ms, 3)
                result["timings_ms"]["graph_build"] = round(runtime.graph_build_ms, 3)
                write_started = time.perf_counter()
                cache.set(key, result)
                cache_ms += (time.perf_counter() - write_started) * 1000
            result = {**result, "metrics": dict(result["metrics"])}
        except Exception:
            log.exception("Runtime failed for project %s operation %s", project.id, body.operation)
            span.set_status(Status(StatusCode.ERROR, "Runtime failure"))
            status = "error"
            result = {
                "operation": body.operation,
                "context": "",
                "error": "Context operation failed",
                "metrics": {
                    "candidate_tokens": 0,
                    "returned_tokens": 0,
                    "token_budget": body.token_budget,
                },
                "included_files": [],
                "omitted_files": [],
                "steps": [],
            }
        result["metrics"].update(
            {"latency_ms": round((time.perf_counter() - started) * 1000), "cache_hit": hit}
        )
        result["index"] = {
            "revision": project.revision,
            "indexed_at": repository.indexed_at.isoformat() if repository else None,
            "freshness": "Changed text records refreshed incrementally; metadata stat checks are bypassed with force_refresh.",
        }
        span.set_attribute("context.returned_tokens", result["metrics"]["returned_tokens"])
        span.set_attribute("context.cache_hit", hit)
        otel_id = f"{span.get_span_context().trace_id:032x}"
        trace = ContextRequest(
            project_id=project.id,
            operation=body.operation,
            inputs=inputs,
            client=x_mcp_client,
            session_id=x_mcp_session,
            otel_trace_id=otel_id,
            token_budget=body.token_budget,
            candidate_tokens=result["metrics"]["candidate_tokens"],
            returned_tokens=result["metrics"]["returned_tokens"],
            latency_ms=result["metrics"]["latency_ms"],
            cache_hit=hit,
            status=status,
            revision=project.revision,
        )
        tracing_started = time.perf_counter()
        db.add(trace)
        db.flush()
        result.update({"trace_id": trace.id, "otel_trace_id": otel_id})
        db.add(ContextResult(request_id=trace.id, payload=result))
        from conceptualize_runtime.patterns import detect

        previous_operations = (session.context_state or {}).get("operations", []) if session else []
        operation_record = {
            "operation": body.operation,
            "inputs": inputs,
            "metrics": result["metrics"],
            "selected_files": result.get("selected_files", []),
            "deliveries": result.get("deliveries", []),
        }
        result["pattern_evidence"] = detect(previous_operations + [operation_record])
        if x_mcp_session:
            if not session:
                session = McpSession(
                    project_id=project.id, session_id=x_mcp_session, client=x_mcp_client
                )
                db.add(session)
            session.last_seen = now()
            if status == "success":
                units = result.get("deliveries", []) + (
                    [result["bundle_delivery"]] if result.get("bundle_delivery") else []
                )
                selected_by_id = {
                    item.get("path") or item.get("id"): item
                    for item in result.get("selection", [])
                }
                delivered_at = now().isoformat()
                additions = [
                    {
                        **unit,
                        "trace_id": trace.id,
                        "operation_id": trace.id,
                        "query": body.query or " ".join(body.paths) or body.target or body.path,
                        "delivered_at": delivered_at,
                        "source_version": unit.get("source_version") or unit.get("content_hash"),
                        "relationships": unit.get("relationships")
                        or selected_by_id.get(unit.get("path") or unit.get("unit_id"), {}).get("relationship"),
                        "invalidation_state": "current",
                    }
                    for unit in units
                ]
                # Bound state conservatively: evicted evidence is re-sent, never treated as known.
                session.context_state = {
                    "deliveries": (history + additions)[-1000:],
                    "operations": (previous_operations + [operation_record])[-20:],
                }
        result.setdefault("timings_ms", {})["cache"] = round(cache_ms, 3)
        result["timings_ms"]["database_trace_before_commit"] = round(
            (time.perf_counter() - tracing_started) * 1000, 3
        )
        if hit:
            result["timings_ms"] = {
                "cache": round(cache_ms, 3),
                "database_trace_before_commit": result["timings_ms"][
                    "database_trace_before_commit"
                ],
                "cache_hit": True,
            }
        stage = result.get("timings_ms", {})
        result["overhead"] = {
            "transport_ms": None,
            "index_lookup_ms": round(
                max(0, refresh_ms - refresh["git_ms"])
                + max(0, stage.get("snapshot_and_graph", 0) - stage.get("graph_build", 0)),
                3,
            ),
            "graph_ms": round(stage.get("graph_build", 0) + stage.get("graph_traversal", 0), 3),
            "context_source_load_ms": stage.get("context_source_load", 0),
            "git_ms": round(refresh["git_ms"], 3),
            "scoring_ms": stage.get("scoring", 0),
            "packing_ms": stage.get("context_compilation", 0),
            "cache_ms": stage.get("cache", 0),
            "trace_write_ms": stage.get("database_trace_before_commit", 0),
            "total_runtime_ms": round((time.perf_counter() - started) * 1000, 3),
        }
        commit_started = time.perf_counter()
        db.commit()
        result["timings_ms"]["database_commit"] = round(
            (time.perf_counter() - commit_started) * 1000, 3
        )
        result["overhead"]["total_runtime_ms"] = round((time.perf_counter() - started) * 1000, 3)
        result["overhead"]["trace_write_ms"] += result["timings_ms"]["database_commit"]
        # Commit timing is response-only; persisted timing stops immediately before commit.
        if status == "error":
            return JSONResponse(status_code=500, content=result)
        return result


@app.get("/v1/overview")
def overview(project: Project = Depends(authenticate), db=Depends(get_db)):
    stmt = select(
        func.count(),
        func.coalesce(func.sum(ContextRequest.returned_tokens), 0),
        func.coalesce(func.avg(ContextRequest.returned_tokens), 0),
        func.coalesce(func.avg(ContextRequest.latency_ms), 0),
        func.coalesce(func.sum(ContextRequest.cache_hit.cast(Integer)), 0),
    ).where(ContextRequest.project_id == project.id)
    total, delivered, average, latency, hits = db.execute(stmt).one()
    context_unit_count = db.scalar(
        select(func.count()).select_from(ContextUnitRecord).where(
            ContextUnitRecord.project_id == project.id
        )
    )
    indexed_sources = set(
        db.scalars(
            select(ContextUnitRecord.source_type)
            .where(ContextUnitRecord.project_id == project.id)
            .distinct()
        )
    )
    runtime, repo = project_runtime(db, project.id)
    context_sources = set()
    if repo:
        context_sources.add("repository")
    if indexed_sources.intersection({"conversation", "message"}):
        context_sources.add("conversation")
    return {
        "project": {"id": project.id, "name": project.name, "revision": project.revision},
        "total_operations": total,
        "tokens_delivered": delivered,
        "average_context_size": round(average),
        "average_latency_ms": round(latency),
        "indexed_files": len(runtime.files),
        "indexed_symbols": sum(len(f["symbols"]) for f in runtime.files.values()),
        "cache_hit_rate": hits / total if total else 0,
        "indexed_at": repo.indexed_at.isoformat() if repo else None,
        "context_units": context_unit_count,
        "context_sources": sorted(context_sources),
    }


@app.post("/v1/index")
def index_repository(body: IndexInput, project: Project = Depends(authenticate), db=Depends(get_db)):
    """Index the local repository selected in the loopback dashboard."""
    root = Path(body.path).expanduser()
    try:
        if not root.is_dir():
            raise ValueError("Choose an existing local repository directory")
        return index_project(db, project, root, body.base)
    except (OSError, ValueError) as exc:
        db.rollback()
        raise HTTPException(400, str(exc)) from exc


class ConversationInput(BaseModel):
    conversations: list[dict] = Field(min_length=1, max_length=100)


@app.post("/v1/context/conversations")
def ingest_conversations(
    body: ConversationInput,
    project: Project = Depends(authenticate),
    db=Depends(get_db),
):
    """Ingest explicit structured conversation data without summaries or model processing."""
    from conceptualize_runtime.adapters import ConversationAdapter
    from conceptualize_runtime.runtime import token_count

    project = db.scalar(
        select(Project)
        .where(Project.id == project.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    try:
        units = ConversationAdapter().ingest(body.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    message_count = sum(unit.source_type == "message" for unit in units)
    if message_count > 10000:
        raise HTTPException(413, "Conversation batch exceeds 10000 messages")
    conversation_ids = {unit.metadata["conversation_id"] for unit in units}
    existing = list(
        db.scalars(
            select(ContextUnitRecord).where(
                ContextUnitRecord.project_id == project.id,
                ContextUnitRecord.source_type.in_(["conversation", "message"]),
                ContextUnitRecord.metadata_json["conversation_id"].as_string().in_(
                    conversation_ids
                ),
            )
        )
    )
    current = {
        row.unit_id: row
        for row in existing
        if row.metadata_json.get("conversation_id") in conversation_ids
    }
    incoming = {unit.id: unit for unit in units}
    def same_unit(unit_id, unit):
        old = current.get(unit_id)
        return bool(
            old
            and old.content_hash == unit.content_hash
            and old.parent_id == unit.parent_id
            and old.relationships == unit.relationships
            and old.metadata_json == unit.metadata
        )

    unchanged = len(current) == len(incoming) and all(
        same_unit(unit_id, unit) for unit_id, unit in incoming.items()
    )
    if unchanged:
        return {"units": len(units), "changed": 0, "deleted": 0, "unchanged": True}
    for row in current.values():
        db.delete(row)
    db.flush()
    for unit in units:
        db.add(
            ContextUnitRecord(
                project_id=project.id,
                unit_id=unit.id,
                source_type=unit.source_type,
                source_id=unit.source_id,
                parent_id=unit.parent_id,
                content=unit.content,
                content_hash=unit.content_hash,
                version=unit.version,
                token_count=unit.token_count or token_count(unit.content),
                created_at=unit.created_at,
                updated_at=unit.updated_at,
                relationships=unit.relationships,
                metadata_json=unit.metadata,
            )
        )
    project.revision += 1
    db.commit()
    return {
        "units": len(units),
        "changed": sum(1 for unit_id, unit in incoming.items() if not same_unit(unit_id, unit)),
        "deleted": len(set(current) - set(incoming)),
        "unchanged": False,
    }


def trace_summary(row: ContextRequest) -> dict:
    return {
        "id": row.id,
        "operation": row.operation,
        "inputs": row.inputs,
        "client": row.client,
        "session_id": row.session_id,
        "timestamp": row.timestamp.isoformat(),
        "token_budget": row.token_budget,
        "candidate_tokens": row.candidate_tokens,
        "returned_tokens": row.returned_tokens,
        "latency_ms": row.latency_ms,
        "cache_hit": row.cache_hit,
        "status": row.status,
        "revision": row.revision,
        "otel_trace_id": row.otel_trace_id,
    }


@app.get("/v1/traces")
def traces(
    project: Project = Depends(authenticate),
    db=Depends(get_db),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    rows = db.scalars(
        select(ContextRequest)
        .where(ContextRequest.project_id == project.id)
        .order_by(ContextRequest.timestamp.desc())
        .limit(limit)
        .offset(offset)
    )
    return {"items": [trace_summary(row) for row in rows]}


@app.get("/v1/traces/{trace_id}")
def trace_detail(trace_id: str, project: Project = Depends(authenticate), db=Depends(get_db)):
    row = db.scalar(
        select(ContextRequest).where(
            ContextRequest.id == trace_id, ContextRequest.project_id == project.id
        )
    )
    if not row:
        raise HTTPException(404, "Trace not found")
    result = db.get(ContextResult, trace_id)
    return {**trace_summary(row), "result": result.payload if result else None}


@app.get("/v1/graph")
def graph(project: Project = Depends(authenticate), db=Depends(get_db)):
    runtime, _ = project_runtime(db, project.id)
    nodes = list(runtime.graph.nodes(data=True))[:200]
    visible = {p for p, _ in nodes}
    edges = [
        {"source": a, "target": b, **data}
        for a, b, data in runtime.graph.edges(data=True)
        if a in visible and b in visible
    ][:400]
    return {
        "nodes": [{"id": p, **data} for p, data in nodes],
        "edges": edges,
        "truncated": len(runtime.graph) > 200,
        "total_nodes": len(runtime.graph),
    }


@app.get("/v1/git")
def git_info(path: str = "", project: Project = Depends(authenticate), db=Depends(get_db)):
    runtime, _ = project_runtime(db, project.id)
    info = dict(runtime.git_info)
    if path:
        paths = set(runtime.resolve(path))
        info["commits"] = [c for c in info.get("commits", []) if paths.intersection(c["files"])]
        info["cochanges"] = [c for c in info.get("cochanges", []) if paths.intersection(c["files"])]
    return info

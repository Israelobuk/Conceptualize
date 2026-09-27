import asyncio
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx
from conceptualize.auth import create_key
from conceptualize.models import Base, Project, User
from conceptualize.service import index_project
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from test_runtime import fixture_index


def test_real_mcp_protocol_calls_api_and_persists_traces(tmp_path):
    """Actual stdio MCP transport -> HTTP API -> runtime -> database, no transport mocks."""
    root = Path(__file__).resolve().parents[1]
    db_url = "sqlite:///" + (tmp_path / "integration.db").as_posix()
    engine = create_engine(db_url)
    Base.metadata.create_all(engine)
    repo = tmp_path / "repo"
    repo.mkdir()
    fixture_index(repo)
    with sessionmaker(engine, expire_on_commit=False)() as db:
        user = User(email="mcp@localhost")
        db.add(user)
        db.flush()
        project = Project(user_id=user.id, name="MCP integration")
        db.add(project)
        db.flush()
        key = create_key(db, project.id)
        db.commit()
        index_project(db, project, repo)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    env = {
        **os.environ,
        "DATABASE_URL": db_url,
        "CONCEPTUALIZE_API_KEY": key,
        "CONCEPTUALIZE_API_URL": f"http://127.0.0.1:{port}",
        "REDIS_URL": "redis://127.0.0.1:1/0",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "",
        "PYTHONPATH": os.pathsep.join(str(root / p) for p in ("apps/api", "apps/mcp", "packages")),
    }
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "conceptualize.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=root,
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(100):
            try:
                if (
                    httpx.get(env["CONCEPTUALIZE_API_URL"] + "/health", timeout=0.5).status_code
                    == 200
                ):
                    break
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        else:
            raise AssertionError("API did not start")

        ingested = httpx.post(
            env["CONCEPTUALIZE_API_URL"] + "/v1/context/conversations",
            headers={"Authorization": "Bearer " + key},
            json={
                "conversations": [
                    {
                        "id": "mcp-conversation",
                        "messages": [
                            {
                                "id": "m1",
                                "role": "assistant",
                                "content": "We chose PostgreSQL because JSONB stores context metadata.",
                            }
                        ],
                    }
                ]
            },
        )
        assert ingested.status_code == 200, ingested.text

        async def exercise():
            params = StdioServerParameters(
                command=sys.executable,
                args=["-m", "conceptualize_mcp.server"],
                env=env,
                cwd=str(root),
            )
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listing = await session.list_tools()
                    capability = await session.read_resource("conceptualize://capabilities")
                    assert json.loads(capability.contents[0].text)["indexed_files"] == 3
                    assert "conversation" in json.loads(capability.contents[0].text)["context_sources"]
                    assert {t.name for t in listing.tools} == {
                        "conceptualize_" + op
                        for op in ("map", "search", "dependencies", "expand", "pack", "inspect")
                    }
                    assert all(t.description and len(t.description) > 80 for t in listing.tools)
                    operations = [
                        ("map", {"path": "src"}),
                        ("search", {"query": "login"}),
                        (
                            "search",
                            {
                                "query": "PostgreSQL JSONB context metadata",
                                "source_types": ["conversation"],
                                "level": "source",
                            },
                        ),
                        ("dependencies", {"target": "src/session.py"}),
                        ("expand", {"target": "login"}),
                        ("pack", {"paths": ["src/session.py"], "token_budget": 1000}),
                        ("inspect", {"target": "src/session.py", "token_budget": 1000}),
                    ]
                    trace_ids = []
                    for op, inputs in operations:
                        response = await session.call_tool("conceptualize_" + op, inputs)
                        assert not response.isError, response.content
                        payload = response.structuredContent
                        if op == "search" and inputs.get("source_types"):
                            assert "PostgreSQL" in payload["context"]
                            assert payload["included_context"]
                            assert payload["selection"][0]["source_type"] == "message"
                        if op == "inspect":
                            assert payload["manifest"]["files"] == 3
                            assert payload["context_id"].startswith("ctx_")
                        assert payload and (payload["context"] or payload.get("previous_context"))
                        assert (
                            payload["metrics"]["returned_tokens"]
                            <= payload["metrics"]["token_budget"]
                        )
                        trace_ids.append(payload["trace_id"])
                    return trace_ids

        ids = asyncio.run(exercise())
        with httpx.Client(
            base_url=env["CONCEPTUALIZE_API_URL"], headers={"Authorization": "Bearer " + key}
        ) as client:
            activity = client.get("/v1/traces").json()["items"]
            assert {t["id"] for t in activity} == set(ids)
            assert len({t["session_id"] for t in activity}) == 1
            detail = client.get("/v1/traces/" + ids[-1]).json()
            assert "src/tokens.py" in detail["result"].get(
                "selected_files", detail["result"]["included_files"]
            )
            assert detail["result"]["selection"]
            assert all(
                "priority" in row and "token_cost" in row for row in detail["result"]["selection"]
            )
            assert client.get("/v1/overview").json()["total_operations"] == 7
    finally:
        process.terminate()
        process.wait(timeout=10)
        engine.dispose()

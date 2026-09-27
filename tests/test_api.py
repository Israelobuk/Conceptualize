import pytest
from conceptualize.auth import create_key
from conceptualize.db import get_db
from conceptualize.main import app
from conceptualize.models import ApiKey, Base, Project, User
from conceptualize.service import index_project
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from test_runtime import fixture_index


@pytest.fixture
def api(tmp_path, monkeypatch):
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(engine, expire_on_commit=False)
    with session() as db:
        user = User(email="test@localhost")
        db.add(user)
        db.flush()
        project = Project(user_id=user.id, name="Test project")
        other = Project(user_id=user.id, name="Other project")
        db.add_all([project, other])
        db.flush()
        key = create_key(db, project.id)
        other_key = create_key(db, other.id)
        db.commit()
        fixture_index(tmp_path)
        index_project(db, project, tmp_path)

    def dependency():
        with session() as db:
            yield db

    app.dependency_overrides[get_db] = dependency
    memory = {}
    from conceptualize.main import cache

    monkeypatch.setattr(cache, "get", lambda k: memory.get(k))
    monkeypatch.setattr(cache, "set", lambda k, v, ttl=300: memory.__setitem__(k, v))
    with TestClient(app) as client:
        yield (
            client,
            {"Authorization": "Bearer " + key},
            {"Authorization": "Bearer " + other_key},
            session,
            project.id,
        )
    app.dependency_overrides.clear()


def test_authentication_and_project_trace_isolation(api):
    client, headers, other, session, _ = api
    assert client.post("/v1/runtime", json={"operation": "map"}).status_code == 401
    assert client.get("/v1/overview", headers={"Authorization": "Bearer cx_bad"}).status_code == 401
    response = client.post("/v1/runtime", headers=headers, json={"operation": "map"})
    assert response.status_code == 200
    trace = response.json()["trace_id"]
    assert client.get(f"/v1/traces/{trace}", headers=other).status_code == 404
    assert client.get("/v1/traces", headers=other).json()["items"] == []
    with session() as db:
        assert all(not k.key_hash.startswith("cx_") for k in db.scalars(select(ApiKey)))


def test_cache_hit_still_records_trace_and_reindex_invalidates(api, tmp_path):
    client, headers, _, session, project_id = api
    body = {"operation": "pack", "paths": ["src/session.py"], "token_budget": 1000}
    first = client.post("/v1/runtime", headers=headers, json=body).json()
    second = client.post("/v1/runtime", headers=headers, json=body).json()
    assert not first["metrics"]["cache_hit"]
    assert second["metrics"]["cache_hit"]
    assert first["trace_id"] != second["trace_id"]
    (tmp_path / "src" / "session.py").write_text("def refreshed(): pass")
    with session() as db:
        index_project(db, db.get(Project, project_id), tmp_path)
    third = client.post("/v1/runtime", headers=headers, json=body).json()
    assert not third["metrics"]["cache_hit"]
    assert "refreshed" in third["context"]
    assert client.get("/v1/overview", headers=headers).json()["total_operations"] == 3
    assert (
        client.get(f"/v1/traces/{third['trace_id']}", headers=headers).json()["result"]["context"]
        == third["context"]
    )


def test_invalid_requests_and_revocation(api):
    client, headers, _, session, _ = api
    assert (
        client.post(
            "/v1/runtime",
            headers=headers,
            json={"operation": "pack", "paths": ["src"], "token_budget": 0},
        ).status_code
        == 422
    )
    assert (
        client.post("/v1/runtime", headers=headers, json={"operation": "search"}).status_code == 422
    )
    with session() as db:
        key = db.scalars(select(ApiKey)).first()
        key.revoked = True
        db.commit()
    assert client.get("/v1/overview", headers=headers).status_code == 401


def test_cache_hit_does_not_rebuild_repository_graph(api, monkeypatch):
    import conceptualize.main as main

    client, headers, _, _, _ = api
    original = main.project_runtime
    calls = []

    def tracked(*args):
        calls.append(True)
        return original(*args)

    monkeypatch.setattr(main, "project_runtime", tracked)
    for _ in range(2):
        assert (
            client.post("/v1/runtime", headers=headers, json={"operation": "map"}).status_code
            == 200
        )
    assert len(calls) == 1


def test_runtime_failure_is_clean_and_persists_an_error_trace(api, monkeypatch):
    from conceptualize_runtime.runtime import ContextRuntime

    client, headers, _, _, _ = api

    def fail(*args):
        raise RuntimeError("internal diagnostic")

    monkeypatch.setattr(ContextRuntime, "execute", fail)
    response = client.post("/v1/runtime", headers=headers, json={"operation": "map"})
    assert response.status_code == 500
    assert "internal diagnostic" not in response.text
    trace_id = response.json()["trace_id"]
    trace = client.get(f"/v1/traces/{trace_id}", headers=headers).json()
    assert trace["status"] == "error"


def test_session_delta_is_durable_scoped_and_refreshable(api):
    client, headers, other, session, project_id = api
    scoped = {**headers, "X-MCP-Session": "session-one"}
    body = {"operation": "pack", "paths": ["src/session.py"], "token_budget": 2000}
    first = client.post("/v1/runtime", headers=scoped, json=body).json()
    second = client.post("/v1/runtime", headers=scoped, json=body).json()
    assert second["context"] == ""
    assert second["previous_context"]
    assert second["metrics"]["duplicate_tokens_avoided"] > 0
    distinct = client.post(
        "/v1/runtime", headers={**headers, "X-MCP-Session": "session-two"}, json=body
    ).json()
    assert distinct["context"]
    forced = client.post("/v1/runtime", headers=scoped, json={**body, "force_refresh": True}).json()
    assert forced["context"]
    from conceptualize.models import McpSession

    with session() as db:
        state = db.scalar(
            select(McpSession).where(McpSession.session_id == "session-one")
        ).context_state
        assert state["deliveries"]
    assert client.get("/v1/traces/" + first["trace_id"], headers=other).status_code == 404


def test_inspect_refreshes_changed_files_without_full_reparse(api, monkeypatch):
    from pathlib import Path

    import conceptualize_runtime.index as index
    from conceptualize.models import Repository

    client, headers, _, sessions, project_id = api
    scoped = {**headers, "X-MCP-Session": "live"}
    body = {"operation": "inspect", "target": "src/session.py", "token_budget": 2000}
    first = client.post("/v1/runtime", headers=scoped, json=body)
    assert first.status_code == 200
    with sessions() as db:
        repo = db.scalar(select(Repository).where(Repository.project_id == project_id))
        path = Path(repo.root) / "src/session.py"
    parsed = []
    original = index.parse_file
    monkeypatch.setattr(
        index, "parse_file", lambda p, text: (parsed.append(p), original(p, text))[1]
    )
    path.write_text(path.read_text() + "\ndef new_session():\n    return 42\n")
    changed = client.post("/v1/runtime", headers=scoped, json=body).json()
    assert changed["invalidations"]
    assert "new_session" in changed["context"]
    assert parsed == ["src/session.py"]
    assert (
        set(
            (
                "transport_ms",
                "index_lookup_ms",
                "graph_ms",
                "git_ms",
                "scoring_ms",
                "packing_ms",
                "cache_ms",
                "trace_write_ms",
                "total_runtime_ms",
            )
        )
        <= changed["overhead"].keys()
    )

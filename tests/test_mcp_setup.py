import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


def test_config_generator_uses_absolute_python_and_never_prints_key():
    result = subprocess.run(
        [sys.executable, "-m", "conceptualize_mcp.setup", "config"],
        capture_output=True,
        text=True,
        check=True,
    )
    server = json.loads(result.stdout)["mcpServers"]["conceptualize"]
    assert server["command"] == sys.executable
    assert server["env"]["CONCEPTUALIZE_API_KEY"] == "REPLACE_WITH_PROJECT_KEY"
    assert "CONCEPTUALIZE_MCP_ADVANCED" not in server["env"]


def test_advanced_config_is_explicit_opt_in():
    result = subprocess.run(
        [sys.executable, "-m", "conceptualize_mcp.setup", "config", "--advanced"],
        capture_output=True,
        text=True,
        check=True,
    )
    server = json.loads(result.stdout)["mcpServers"]["conceptualize"]
    assert server["env"]["CONCEPTUALIZE_MCP_ADVANCED"] == "true"


def test_codex_direct_activation_snippet_names_only_existing_context_tool():
    from conceptualize_mcp.setup import CODEX_DIRECT_ACTIVATION

    result = subprocess.run(
        [sys.executable, "-m", "conceptualize_mcp.setup", "config", "--format", "codex",
         "--direct-activation"], capture_output=True, text=True, check=True)
    assert "developer_instructions = " + json.dumps(CODEX_DIRECT_ACTIVATION) in result.stdout
    assert "mcp__conceptualize__conceptualize_context directly once" in result.stdout
    assert "[mcp_servers.conceptualize]" in result.stdout
    assert "CONCEPTUALIZE_MCP_ADVANCED" not in result.stdout


def test_doctor_accepts_the_primary_one_tool_surface(monkeypatch):
    from conceptualize_mcp import setup

    names = {"conceptualize_context"}

    class Stdio:
        async def __aenter__(self):
            return None, None

        async def __aexit__(self, *_):
            return None

    class Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_):
            return None

        async def initialize(self):
            return None

        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name=name) for name in names])

        async def call_tool(self, name, arguments):
            assert name == "conceptualize_context"
            assert arguments == {"task": "current project context"}
            return SimpleNamespace(
                isError=False,
                structuredContent={
                    "trace_id": "fresh-trace",
                    "sources": ["repository_file"],
                    "new_context_tokens": 12,
                },
            )

    monkeypatch.setattr(setup, "stdio_client", lambda _params: Stdio())
    monkeypatch.setattr(setup, "ClientSession", lambda _read, _write: Session())
    result = asyncio.run(setup.verify(sys.executable, "http://127.0.0.1:8000"))
    assert result["tools"] == sorted(names)
    assert result["context_trace_id"] == "fresh-trace"


def test_server_default_surface_has_one_tool_and_advanced_surface_has_seven():
    root = Path(__file__).resolve().parents[1]
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(str(root / path) for path in ("apps/api", "apps/mcp", "packages"))
    script = "import json; from conceptualize_mcp.server import mcp; print(json.dumps(sorted(t.name for t in mcp._tool_manager.list_tools())))"
    default = subprocess.run([sys.executable, "-c", script], cwd=root, env=env, capture_output=True, text=True, check=True)
    advanced_env = {**env, "CONCEPTUALIZE_MCP_ADVANCED": "true"}
    advanced = subprocess.run([sys.executable, "-c", script], cwd=root, env=advanced_env, capture_output=True, text=True, check=True)
    assert json.loads(default.stdout) == ["conceptualize_context"]
    assert len(json.loads(advanced.stdout)) == 7


def test_default_capability_schema_only_requires_the_normal_task():
    from conceptualize_mcp.server import mcp

    tool = next(t for t in mcp._tool_manager.list_tools() if t.name == "conceptualize_context")

    assert tool.parameters["properties"].keys() == {"task"}
    assert tool.parameters["required"] == ["task"]
    assert "context capability" in tool.description.casefold()
    assert "normal tools" in tool.description.casefold()
    assert "search" not in tool.description.casefold()


def test_capability_passes_the_task_through_unchanged(monkeypatch):
    from conceptualize_mcp import server

    observed = {}

    async def capture(operation, inputs, _ctx):
        observed.update(operation=operation, inputs=inputs)
        return "ok"

    monkeypatch.setattr(server, "call", capture)
    task = "Continue auth work; preserve offline support and run the existing tests."
    result = asyncio.run(server.conceptualize_context(task))

    assert result == "ok"
    assert observed == {"operation": "context", "inputs": {"query": task}}

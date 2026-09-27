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
            assert arguments["query"] == "current project context"
            assert arguments["token_budget"] == 1000
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

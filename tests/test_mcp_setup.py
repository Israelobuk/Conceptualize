import asyncio
import json
import subprocess
import sys
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


def test_doctor_accepts_the_complete_six_tool_surface(monkeypatch):
    from conceptualize_mcp import setup

    names = {
        "conceptualize_map",
        "conceptualize_search",
        "conceptualize_dependencies",
        "conceptualize_expand",
        "conceptualize_pack",
        "conceptualize_inspect",
    }

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
            assert name == "conceptualize_map"
            assert arguments["token_budget"] == 1000
            return SimpleNamespace(
                isError=False,
                structuredContent={
                    "trace_id": "fresh-trace",
                    "included_files": ["src/main.py"],
                    "index": {"revision": 1},
                    "metrics": {"returned_tokens": 12},
                },
            )

    monkeypatch.setattr(setup, "stdio_client", lambda _params: Stdio())
    monkeypatch.setattr(setup, "ClientSession", lambda _read, _write: Session())
    result = asyncio.run(setup.verify(sys.executable, "http://127.0.0.1:8000"))
    assert result["tools"] == sorted(names)
    assert result["map_trace_id"] == "fresh-trace"

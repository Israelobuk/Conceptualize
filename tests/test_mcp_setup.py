import json
import subprocess
import sys


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

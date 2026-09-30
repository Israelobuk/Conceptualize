"""Same-version frozen V0.9 comparison of default and direct Codex activation."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess

from conceptualize_evaluation import v09_capability_benchmark as benchmark
from conceptualize_mcp.setup import CODEX_DIRECT_ACTIVATION

from evaluations.scripts import run_provider_real_workflow as workflow
from evaluations.scripts.run_provider_input_matched import canonical_hash

ROOT = workflow.ROOT
RUN_ROOT = workflow.RUN_ROOT / "discovery-routing-v1"
RESULTS = workflow.RESULTS / "provider-input-overhead-discovery-routing-v1.json"
DIRECT_INSTRUCTION = CODEX_DIRECT_ACTIVATION
BASE_FLAGS = tuple(workflow.BASE_FLAGS)


def catalog_requests(run: dict) -> list[dict]:
    """Provider requests that inspect the catalog without invoking Conceptualize."""
    found = []
    for request in run["requests"]:
        actions = request["model_actions"]
        inputs = "\n".join(str(action.get("input", "")) for action in actions)
        if "ALL_TOOLS" in inputs and "tools.mcp__conceptualize__conceptualize_context(" not in inputs:
            found.append({"request_index": request["request_index"],
                          "input_tokens": request["input_tokens"],
                          "action": actions})
    return found


def effective_environment() -> dict[str, str]:
    env = {**os.environ, "CODEX_HOME": str(workflow.CODEX_HOME),
           "PYTHONPATH": os.pathsep.join(str(ROOT / path)
                                         for path in ("apps/api", "apps/mcp", "packages"))}
    env.pop("V09_MCP_TRACE", None)
    return env


def run_phase(phase: str, repetitions: int) -> list[dict]:
    workflow.RUN_ROOT_REAL = RUN_ROOT / phase
    workflow.CWD = RUN_ROOT / "empty-workspace"
    workflow.CWD.mkdir(parents=True, exist_ok=True)
    if any(workflow.CWD.iterdir()):
        raise RuntimeError("Matched working directory must be empty")
    workflow.BASE_FLAGS = list(BASE_FLAGS)
    if phase == "after":
        workflow.BASE_FLAGS += ["-c", "developer_instructions=" + json.dumps(DIRECT_INSTRUCTION)]
    fixture, _, freeze = benchmark.verify_freeze()
    _, history = benchmark.conversation(fixture)
    prompt = workflow.prompts(fixture, history, "proven")["f1"]
    env = effective_environment()
    base = {"commit_sha": subprocess.check_output(["git", "rev-parse", "HEAD"],
            cwd=ROOT, text=True).strip(),
            "codex_cli_version": subprocess.check_output(["codex", "--version"],
            text=True).strip(), "model": workflow.MODEL, "reasoning": workflow.REASONING,
            "cwd": str(workflow.CWD.resolve()), "base_flags": workflow.BASE_FLAGS,
            "fixture_sha256": freeze["fixture_sha256"],
            "history_sha256": hashlib.sha256(history.encode()).hexdigest(),
            "task_sha256": hashlib.sha256(fixture["question"].encode()).hexdigest(),
            "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
            "environment_sha256": canonical_hash({key: env.get(key) for key in
                ("CODEX_HOME", "PYTHONPATH", "PATH", "USERPROFILE", "TEMP", "TMP",
                 "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY")}),
            "permissions": {"approval_policy": "on-request", "sandbox": "read-only"}}
    if base["commit_sha"] != "e437f491d6f884a317ca42c1fb4a402d9a818f13":
        raise RuntimeError("Unexpected Git commit")
    runs = []
    for repetition in range(1, repetitions + 1):
        run = workflow.run_one("f1", repetition, repetition, prompt, base, env)
        run["phase"] = phase
        run["catalog_discovery_requests"] = catalog_requests(run)
        run["catalog_discovery_input"] = sum(
            request["input_tokens"] for request in run["catalog_discovery_requests"])
        runs.append(run)
        print(json.dumps({"phase": phase, "repetition": repetition,
                          "status": run["status"], "requests": run["request_count"],
                          "input": run["aggregate_usage"]["input_tokens"],
                          "catalog_requests": len(run["catalog_discovery_requests"]),
                          "conceptualize_calls": len(run["model_emitted_conceptualize_calls"])}),
              flush=True)
    phase_file = RUN_ROOT / f"{phase}.json"
    with phase_file.open("x", encoding="utf-8") as file:
        json.dump({"configuration": base, "configuration_sha256": canonical_hash(base),
                   "runs": runs}, file, ensure_ascii=False, indent=2)
    return runs


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("phase", choices=("before", "after"))
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    if args.repetitions < 1:
        raise SystemExit("repetitions must be positive")
    RUN_ROOT.mkdir(parents=True, exist_ok=True)
    runs = run_phase(args.phase, args.repetitions)
    if args.phase == "after":
        before = json.loads((RUN_ROOT / "before.json").read_text(encoding="utf-8"))
        after = json.loads((RUN_ROOT / "after.json").read_text(encoding="utf-8"))
        if before["configuration"]["codex_cli_version"] != after["configuration"]["codex_cli_version"]:
            raise RuntimeError("CLI version changed between phases")
        with RESULTS.open("x", encoding="utf-8") as file:
            json.dump({"before": before, "after": after,
                       "direct_instruction": DIRECT_INSTRUCTION}, file, ensure_ascii=False, indent=2)
    print(json.dumps({"phase": args.phase, "runs": len(runs)}), flush=True)


if __name__ == "__main__":
    main()

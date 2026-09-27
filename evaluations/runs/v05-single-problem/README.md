# V0.5 single-problem raw evidence

The tracked summary and frozen rubric are in `evaluations/results/v05-model-matrix.json` and `evaluations/v05-conversation-problem.json`. Full Codex `agent-events.jsonl`, model answers, invocation stderr, and per-run manifests are retained locally in this directory. These raw logs are excluded from Git because autonomous MCP responses repeat the full 39-message history and each record can be large. Trace snapshots needed to assess runtime selection are tracked beside the summary.

To rerun, create an isolated Codex home with `auth.json` and a minimal `config.toml`, start the API against a separate database containing this fixture, then run:

```powershell
$env:PYTHONPATH = 'apps/api;apps/mcp;packages'
python -m conceptualize_evaluation.conversation_agent_benchmark `
  --models gpt-6-sol gpt-5.6-sol --repetitions 2 `
  --codex-home evaluations/runs/v05-benchmark-codex-home `
  --api-url http://127.0.0.1:8000 --api-key $env:CONCEPTUALIZE_API_KEY `
  --output-root evaluations/runs/v05-single-problem
```

The result file contains prompt hashes, exact model IDs, per-run deterministic checks, Codex input/cached/output telemetry, elapsed time, and whether Conceptualize was autonomously invoked. Pricing, selected context and duplicate delivery remain null when the measurement source is unavailable. This raw evidence is exploratory and does not support a general performance claim.

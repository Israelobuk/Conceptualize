# Reproducible context evaluation

V0.5 also includes a short runtime-only conversation check: `python -m conceptualize_evaluation.conversation_benchmark`. It compares full fixture histories with bounded Conceptualize retrieval using exact fact-coverage checks. It does not invoke a model; see [V05.md](V05.md) and [raw results](results/v05-conversations.json). The separate 18-cell autonomous agent matrix is recorded as unrun in [v05-model-matrix.json](results/v05-model-matrix.json) because the installed Codex CLI fails to start due to its missing Windows optional dependency.

The instructions below describe the historical V0.4 coding-agent paired evaluation.

Conceptualize does not call a model. This harness runs an **external Codex coding agent**, once with normal repository tools and once with all six Conceptualize MCP tools available. Both runs receive identical prompts and start from identical committed source. Separate repositories preserve all edits and evidence; reruns must use new output directories.

## Tasks

`tasks.json` contains three tasks over the small `fixture/shop` repository:

- `receipts`: migrate a shared payment receipt to integer cents while preserving a separately maintained audit consumer's dollar amounts.
- `auth`: replace a role field with explicit permissions while preserving refund authorization.
- `retry`: connect notification delivery to an existing retry service while preserving non-transient error handling.

Each task has independent behavior checks under `checks/`, outside the agent's repository. These checks are combined with the repository's own tests. Agent claims of success are not used as the completion judgment.

## Run a pair (PowerShell)

Use the project's editable Python installation. Start the existing API with a migrated database. `DATABASE_URL` must refer to **the same database as that API**; enabled runs create a separate project/key and index their isolated fixture. Normal setup uses PostgreSQL. Integration tests and the local captured demonstration use SQLite only as a QA fixture.

```powershell
$python = (Resolve-Path .venv/Scripts/python.exe).Path
# Use a functioning Codex CLI, verified with `codex --version`.
$agent = (Get-Command codex).Source
# Use the same model for both modes; choose one available to your account.
$model = 'YOUR_MODEL'
$api = 'http://127.0.0.1:8000'

& $python -m conceptualize_evaluation.runner run --task receipts --mode control `
  --output evaluations/runs/receipts-control --codex $agent --model $model --api-url $api
& $python -m conceptualize_evaluation.runner run --task receipts --mode conceptualize `
  --output evaluations/runs/receipts-conceptualize --codex $agent --model $model --api-url $api
& $python -m conceptualize_evaluation.runner compare `
  evaluations/runs/receipts-control/result.json evaluations/runs/receipts-conceptualize/result.json `
  --output evaluations/runs/receipts-comparison.json
```

The runner disables unrelated configured MCP servers for both modes and explicitly enables the required Conceptualize transport for the enabled mode. It preserves the user's remaining Codex settings. Use the same settings/version/model across the pair. The task prompt does **not** ask for Conceptualize; its tool descriptions guide autonomous discovery. A run with zero MCP calls is valid evidence of non-adoption, not proof of usefulness. Check agent errors and `traces.json` before interpreting results. The timeout defaults to 600 seconds; change it with `--timeout`.

`prepare` creates the same baseline and prompt without running an agent, useful for other MCP-compatible clients. The automated `run` adapter currently targets Codex's JSON event format; other clients need an adapter rather than invented equivalent metrics.

## Evidence files

- `manifest.json`: task, mode, baseline commit, identical-prompt hash.
- `agent-events.jsonl`: raw agent events, including MCP calls and shell actions.
- `agent-stderr.txt`: startup, MCP, and execution diagnostics.
- `changes.diff`: actual code modifications; `result.json` also lists modified/untracked paths.
- `tests.txt`: actual independent/repository test output.
- `traces.json`: persisted API trace details, including candidate selection and traversed graph relationships.
- `result.json`: measured elapsed time, exit codes, test judgment, exposed agent usage, operations, returned context tokens, and trace IDs.
- Comparison JSON: paired values after validating matching task, prompt, baseline, model and agent version.

Files inspected, corrective iterations, and unnecessary reads remain **null**: shell commands are recorded, but parsing them cannot reliably measure all reads. Agent input-token usage may include repeated cached input; it is not equivalent to unique repository context. Compiled context tokens are measured separately by Conceptualize, and structured MCP metadata adds overhead.

One pair is anecdotal. Repeat all tasks in both orders, preserve failures and zero-call runs, and compare correctness before time or token usage. Do not present lower tokens or faster time alone as evidence of better understanding.

## Dashboard inspection

Each enabled result records its project ID and trace IDs. Use a key for that evaluation project to point the existing dashboard at the same API. The trace detail shows the consumer relationship, selected/omitted candidates, deterministic priority, token cost and source context. No dashboard redesign is involved. The source index remains the pre-change snapshot so the discovery trace is reproducible; reindex only after exporting the run's evidence.

## Captured demonstration

See `DEMO.md` for the actual paired run and its limits. Raw local evidence stays under ignored `runs/` so repository indexing does not absorb benchmark transcripts or generated nested repositories.

# Conceptualize

**Context superpowers for AI agents.** Conceptualize is a deterministic, model-independent context capability that gives an agent relevant prior decisions, constraints, relationships, changes, and work behind the task at hand.

Activate Conceptualize for a task, then keep working normally. In a host that supports mentions, the intended user experience is `@Conceptualize` followed by the user's ordinary task. Host integrations may activate the capability through their native plugin, MCP, skill, or configuration mechanism; the Context Runtime does not parse mention syntax.

Without Conceptualize, an agent works from the context already in its current session. With Conceptualize, the agent can receive relevant context from prior project work and continue with its normal reasoning and tools. There is no separate retrieval workflow, manual source selection, or additional AI model inside Conceptualize. Embeddings and vector databases are not used.

## Architecture

```text
USER
  ↓ @Conceptualize + normal task
HOST AGENT
  ↓ context capability
CONTEXT RUNTIME
  ↓ ContextUnits, relationships, source state and session ledger
WORKING CONTEXT / CONTEXT DELTA
  ↓
HOST AGENT CONTINUES ITS NORMAL WORKFLOW
```

The user-facing capability, minimal agent API, and internal runtime are separate layers. Repository and conversation adapters feed source-agnostic ContextUnits. The deterministic compiler assembles source evidence into a coherent Working Context, preserves provenance, and uses the session ledger to return only useful new or changed context. Complete selection and relationship evidence stays in traces; the agent receives a compact augmentation. Conceptualize complements the host and does not replace it.

## V0.8 capability and evaluation status

The default MCP capability accepts one required field: the user's task. Source selection, context budget, and retrieval strategy are internal. `@Conceptualize` describes the user experience; host integrations may activate it with their native MCP, plugin, skill, or mention mechanism. V0.8 adds deterministic Working Context sections with source-unit provenance. The six legacy tools remain advanced/debug only.

The V0.8 primary comparison has **not reached a valid baseline**. Benchmark v1 scored 0/3; v2 scored 0/3; v3 scored 1/3 after section placement caused false negatives; and v4 scored 0/3 because its deterministic whole-answer grader still missed equivalent wording. No `@Conceptualize` model runs were made. These are inconclusive benchmark-methodology results, not evidence that activation helped or hurt. See the [V0.8 evaluation details](evaluations/V08.md).

## V0.6 evaluation status

V0.6 separates context-engine quality from integration cost using three modes: full context to model (A), precompiled Conceptualize context without MCP tools (B), and autonomous MCP (C). Current evidence is exploratory and does **not** establish an end-to-end token or speed saving. A real one-repetition `gpt-6-sol` comparison recorded 15,781 input tokens in A, 14,823 in B, and 94,943 in C. B delivered 693 context tokens; C invoked the one primary tool and returned 743 context tokens. All three answers failed the strict frozen rubric. The large C input increase remains unexplained by the measured local MCP surface (277 estimated serialized tokens), so it is not attributed to context selection or presented as an efficiency gain. Runtime traces showed 261 ms total on the local unavailable-Redis setup, including about 221 ms of cache timeout; this is environment-specific. A second C probe used 45,976 input tokens despite not invoking the tool.

Reports and frozen fixtures: [V0.6 evaluation](evaluations/V06.md), [three-mode model results](evaluations/results/v06-three-mode.json), [context-engine results](evaluations/results/v06-context-engine.json), and [MCP surface profile](evaluations/results/v06-mcp-surface.json). Raw model events and responses are retained in ignored local `evaluations/runs/v06-three-mode*` directories. Historical negative/inconclusive V0.5 and V0.4 results remain linked from the evaluation docs. No model runs inside Conceptualize.

## V0.7 benchmark status

The frozen V0.7 task used the same 8,223-token conversation for full-context and precompiled-context runs. Full context passed 2/3; Conceptualize precompiled context passed 0/3. Provider-reported input averaged 22,803 versus 18,140 tokens, a 20.4% reduction—below the predeclared 25% threshold, and without preserved task correctness. V0.7 therefore does **not** demonstrate that Conceptualize preserves model capability while materially reducing model input. The context package was 3,477 local cl100k tokens. The budget sweep was skipped because precompiled correctness was not established. In three autonomous Mode C runs, the default tool was available but unused (0/3); no context was delivered and all answers failed. A separate guided-use check successfully called the tool 3/3 times and returned 3,477 context tokens per run, but also passed 0/3 and used 68,088 average provider input tokens. Neither establishes an efficiency gain. The inert-MCP host control used 28,404 provider input tokens in one full-history run; the conditions differ and telemetry cannot isolate the host contribution. See the [V0.7 report](evaluations/V07.md) and [guided-use results](evaluations/results/v07-mode-c-guided-summary.json).

See the [detailed V0.7 evaluation](evaluations/V07.md), [full-context results](evaluations/results/v07-mode-a-na.json), [precompiled-context results](evaluations/results/v07-mode-b-4000.json), [context-engine diagnostics](evaluations/results/v07-context-engine.json), [session delta](evaluations/results/v07-session-continuation.json), and [MCP integration diagnostics](evaluations/results/v07-mcp-integration.json). Earlier rubric-calibration runs are preserved in `evaluations/v07/attempts/` and are excluded from the final A/B counts. No model runs inside Conceptualize.

The `0.8.0` Python package and API versions track the product milestone; benchmark-fixture revisions have their own `fixture_version` fields and are not package versions.
## Local setup (PowerShell)

Prerequisites: Python 3.11+, Node.js 22+, Docker Desktop with its Linux engine running, and Git. Run commands from this repository root. `uv` is optional but convenient when the system Python is unavailable.

```powershell
Copy-Item .env.example .env
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e '.[dev]'
# Alternative: uv venv --python 3.12; uv pip install -e '.[dev]'
npm install
docker compose up -d --wait
alembic upgrade head
conceptualize seed --name "My application" --email "developer@localhost"
```

The example config uses local-only development services. Set `DATABASE_URL`, `REDIS_URL`, `CONCEPTUALIZE_API_URL`, and the one-time project key for the services you run. `APP_ENV=production` disables interactive API documentation; `LOG_LEVEL` configures backend logs. Compose database/cache host ports are configurable with `POSTGRES_HOST_PORT` and `REDIS_HOST_PORT`; keep their connection URLs in sync. Repository content is stored in the configured database after the indexer's exclusions are applied.

The database and dashboard start with no projects, repositories, traces, activity, or sample data. `seed` is an explicit one-time setup command that creates an empty project and prints a random `cx_…` API key **once**; it does not add a demo repository or traces. Copy the key into `CONCEPTUALIZE_API_KEY` in `.env`, then restart the dashboard. The database stores only SHA-256 of the credential plus its recognizable prefix. Re-running seed creates another empty project/key; it does not reset existing data.

Index a repository:

```powershell
conceptualize index 'C:\path\to\repository' --project 'PROJECT_ID'
# Optional Git branch comparison:
conceptualize index 'C:\path\to\repository' --project 'PROJECT_ID' --base main
```

One repository per project keeps source paths unambiguous in V1. Indexing reads file hashes, reparses only changed files, removes deleted/excluded files, and commits an atomic snapshot. A no-change index preserves the revision. Reindex after edits; a response always identifies its snapshot revision and indexing timestamp. There is no background watcher yet.

Start the API in one terminal:

```powershell
.\.venv\Scripts\Activate.ps1
uvicorn conceptualize.main:app --host 127.0.0.1 --port 8000
```

Start the dashboard in another terminal:

```powershell
npm run dev:web
```

Open http://127.0.0.1:3000. Dashboard scripts load the root `.env`; restart the server after key changes. The API key stays server-side and is never placed in `NEXT_PUBLIC_*`. This MVP dashboard is a **local-only control plane**, bound to loopback; it has no browser login and must not be exposed remotely. API docs: http://127.0.0.1:8000/docs.

On a new project, the dashboard shows an empty repository state. Enter the absolute path to your local repository and choose **Index repository**. The dashboard calls the same authenticated indexing service as the CLI and then displays actual file/symbol counts, graph structure, and any recorded traces. Indexing errors remain visible; no example statistics or fixture content are substituted.

Start MCP directly, or let the coding client launch it:

```powershell
.\.venv\Scripts\python.exe -m conceptualize_mcp.server
```

stdio is a machine protocol, so a quiet server waiting for input is expected.

## Connect an MCP-compatible client

Adapt the configuration to the client's MCP settings format. Use absolute paths, and configure the working directory when supported. The server also discovers `.env` at the project root.

```json
{
  "mcpServers": {
    "conceptualize": {
      "command": "C:/path/to/Conceptualize/.venv/Scripts/python.exe",
      "args": ["-m", "conceptualize_mcp.server"],
      "env": {
        "CONCEPTUALIZE_API_URL": "http://127.0.0.1:8000",
        "CONCEPTUALIZE_API_KEY": "YOUR_CX_KEY"
      }
    }
  }
}
```

For Codex, the corresponding TOML shape is:

```toml
[mcp_servers.conceptualize]
command = "C:/path/to/Conceptualize/.venv/Scripts/python.exe"
args = ["-m", "conceptualize_mcp.server"]

[mcp_servers.conceptualize.env]
CONCEPTUALIZE_API_URL = "http://127.0.0.1:8000"
CONCEPTUALIZE_API_KEY = "YOUR_CX_KEY"
```

Connect the MCP capability to a supported host and activate Conceptualize for an ordinary task. The host-facing default surface remains one minimal primitive, `conceptualize_context`, whose only model-supplied field is the user's task. Source choice, bounded context compilation, and session-aware deltas stay inside Conceptualize. The six legacy retrieval tools and capability resource are opt-in through `CONCEPTUALIZE_MCP_ADVANCED=true` for developer diagnostics and compatibility; they are not the normal user workflow.

Generate an absolute-path configuration and verify the real connection:

```powershell
python -m conceptualize_mcp.setup config --format codex
# Copy the generated block into Codex config; the key is inherited from your environment.
$env:CONCEPTUALIZE_API_KEY = 'YOUR_CX_KEY'
python -m conceptualize_mcp.setup doctor --api-url http://127.0.0.1:8000
# Other MCP clients: python -m conceptualize_mcp.setup config --format json
```

Doctor initializes a real stdio MCP session, discovers the default unified tool, calls it once, and reports its persisted trace ID. Use `python -m conceptualize_mcp.setup config --format codex --advanced` only when you need the optional debugging tools. Configuration generation never prints your key. Pass project credentials explicitly when a client does not inherit environment variables.

## HTTP operations

```powershell
$headers = @{ Authorization = "Bearer YOUR_CX_KEY" }
$body = @{ operation = "pack"; paths = @("src/auth"); token_budget = 8000;
           include_dependencies = $true; include_tests = $true } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/v1/runtime -Method Post -Headers $headers `
  -ContentType 'application/json' -Body $body
```

`POST /v1/runtime` accepts the primary `context` operation plus the advanced operations; OpenAPI documents request validation. A context request can select `repository`, `conversation`, or both with `source_types`; inferred sources are checked before freshness work so conversation-only requests skip repository refresh/indexing. Repository context follows graph relationships; conversation context uses deterministic lexical ranking and explicit metadata. Traces retain candidate scores, provenance, session state, timings, and token diagnostics. `GET /v1/overview`, `/v1/traces`, `/v1/traces/{id}`, `/v1/graph`, and `/v1/git?path=src/auth` expose project-scoped observations.

### Conversation context

Ingest explicit structured conversations. Re-ingesting an unchanged conversation does not create a new project revision; changed messages invalidate cached results and session fingerprints.

```powershell
$body = @{
  conversations = @(@{
    id = 'product-decisions'; title = 'Product decisions'
    messages = @(
      @{ id = 'm1'; role = 'user'; timestamp = '2026-01-08T13:00:00Z'; content = 'Use PostgreSQL for JSONB metadata.' },
      @{ id = 'm2'; role = 'assistant'; content = 'Recorded.'; parent_id = 'm1' }
    )
  })
} | ConvertTo-Json -Depth 8
Invoke-RestMethod http://127.0.0.1:8000/v1/context/conversations -Method Post -Headers $headers `
  -ContentType 'application/json' -Body $body
```

Conversation ingestion preserves explicit `supersedes`, `updates`, and other declared relationships with provenance. Session history references unchanged deliveries and returns changed/new context; deterministic duplicate suppression only changes selection, never stored source data. No conversation summaries or model-generated topics are created.

Provider pricing is supplied as a versioned JSON snapshot and loaded with `conceptualize_runtime.economics.load_pricing`, then passed to `estimate_cost`. Conceptualize ships no live price table. Costs remain unavailable if any input, cached-input, or output token telemetry is missing; context-string token counts are not substituted for model telemetry.

## Deterministic behavior and limits

- Tree-sitter parses Python, JavaScript/JSX, TypeScript/TSX. Markdown and common configuration/text files are indexed as text. Parse errors are visible; Tree-sitter still extracts recoverable declarations.
- Import resolution supports Python relative/absolute modules, package submodules and identifiable source roots, JS/TS relative paths and aliases from the nearest strict-JSON tsconfig/jsconfig. Explicit named imports and aliases link to unambiguous declarations, including imported types. Reverse imports reveal consumers; tests importing a source module are linked regardless of filename. Filename-only associations and unique-name references remain **heuristic**. Ambiguous roots stay unresolved. Dynamic imports, CommonJS require, config inheritance/JSONC, namespace-member and re-export chains, overload resolution and runtime scope resolution are not claimed as complete.
- Indexing excludes `.git`, dependencies, common build/cache directories, symlinks, binaries, lockfiles, `.env`, credential/secret filenames, private-key blocks, and obvious generated markers. Files over 1 MB are skipped. Root and nested `.gitignore` rules are respected where practical. This is not a comprehensive secret scanner: inspect what you choose to index.
- Pack priorities are deterministic: requested entities, imported symbol files, direct dependencies, consumers, related tests, current modifications, observed Git cochanges, and nearby paths. Consumers are enabled by default; explicit flags still allow narrowing the disclosure. Tests of direct consumers are included for shared-contract changes. Supporting selection is bounded to 20 modified files and eight nearby files per explicit target; this is a policy limit, not exhaustive repository coverage. Cochanges require at least two observations among the last 20 commits and are not causal claims. Git-modified files break ties within a priority tier. Lexical search weights are never presented as confidence or machine-learned ranking.
- Every candidate has a `selection` entry with path, priority, reason, responsible relationship, compiled block token cost, selected/omitted/truncated status, and omission reason. Trace details expose this evidence in a collapsible table; the main dashboard design is unchanged. Index format v2 requires reindexing to populate import-binding metadata. Cache namespace v2 avoids serving old ranking results.
- Each returned **compiled context string** fits the cl100k_base token budget, including file headers/separators. This is an approximate host-model measure. Structured metadata and MCP serialization add tokens beyond that string; the response states this budget scope. Whole files are preferred; if none fit, a clearly marked prefix may be returned. Included, omitted, and truncated files are explicit.
- Redis cache keys include project ID, index revision, snapshot hash and canonical operation inputs. New index state invalidates cached responses. TTL is five minutes. Redis failures degrade to uncached execution. Every cache hit still produces a new persistent request trace.
- PostgreSQL stores source snapshots and structural JSON. NetworkX rebuilds a graph per request in this small MVP. Large repositories will benefit from a persisted in-memory graph and optimized lexical indexes later.
- OpenTelemetry spans cover runtime operations and indexing. `otel_trace_id` links persistent trace records. Set `OTEL_EXPORTER_OTLP_ENDPOINT` to an HTTP collector base URL to export spans; no collector is required for the dashboard.
- Session identity is generated per MCP process, and the host client's name is recorded when provided. MCP reconnection starts a new session.

## Verification

```powershell
pytest
ruff check apps packages tests
npm run typecheck
npm run build
docker compose config
```

Tests cover Tree-sitter structures, exclusions, incremental indexing, graph relationships, budgeting/truncation, key isolation/revocation, caching/reindexing, Git history, failure traces, and the **real MCP stdio → HTTP API → runtime → trace** path. Isolated tests use SQLite solely as a test fixture; normal setup uses PostgreSQL. Redis interactions use a deterministic test cache, while failures fall back to execution. To verify live infrastructure, start Compose, apply migrations, index a repository, and make the same MCP request twice: the second response should report `cache_hit: true`, and both requests should appear in the dashboard.

Revoke a key locally with `conceptualize revoke-key --prefix cx_PREFIX`. Keep `.env` out of Git. Stop infrastructure with `docker compose stop` (keeps indexed data); `docker compose down` also keeps the named volume. This foundation intentionally excludes billing, OAuth, teams, integrations, autonomous agents, and distributed infrastructure.

## Evaluation

Run the deterministic V0.6 fixtures with `.venv/Scripts/python.exe -m conceptualize_evaluation.v06_context_benchmark`; results are written to `evaluations/results/v06-context-engine.json`. They cover conversation continuity, a hidden cross-file consumer, session continuation, topic shift, explicit supersession, and a negative control. This is a retrieval diagnostic, not a model-quality test.

The real-model runner supports Mode A full context, Mode B precompiled context without MCP, and Mode C autonomous MCP. Its output retains raw Codex events, answers, prompts, tool calls, and per-run result JSON. MCP serialized surface measurements compare the default one-tool registration to the seven-tool advanced surface. Host-side token telemetry remains separate because its prompt packing and hidden integration costs cannot be derived from local JSON sizes. See [evaluations/V06.md](evaluations/V06.md) for the measured result and limits. V0.5 and earlier historical evidence is organized under [evaluations](evaluations/README.md), including [V0.4 adoption](evaluations/v04/ADOPTION.md), [the V0.4 report](evaluations/v04/V04.md), and [its runbook](evaluations/v04/ADOPTION-RUNBOOK.md).

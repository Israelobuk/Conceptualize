# Conceptualize

**Conceptualize is model-independent context infrastructure for AI systems.** It connects AI agents and applications to structured context sources, tracks what context has already been supplied or changed, and compiles bounded context for each interaction. Repositories are one supported source; conversation history is another. The host AI performs reasoning. Conceptualize manages context.

**The context engine uses no AI models, model API calls, embeddings, vectors, or model credentials.** The evaluation harness invokes an external coding agent for comparison; it is separate from the runtime.

## Architecture

```text
AI system → MCP (stdio) → FastAPI → generic context runtime
                                     ├─ ContextUnit + source adapters
                                     ├─ conversation lexical retrieval
                                     ├─ RepositoryAdapter (Tree-sitter + graph + Git)
                                     ├─ fingerprints, session deltas + bounded packs
                                     ├─ Redis ephemeral cache
                                     └─ PostgreSQL context + metadata + traces
Next.js dashboard → local server proxy → FastAPI
```

`packages/conceptualize_runtime` contains the source-agnostic `ContextUnit`, deterministic retrieval and pack compiler. `RepositoryAdapter` maps existing indexed files and symbols into that boundary while retaining repository-only dependency analysis. `ConversationAdapter` preserves conversation membership, message order, roles, timestamps, explicit references, attachments, and parent/child links. The API stores each project's units; the MCP server exposes the existing six operations over an explicitly selected source set. Full selection provenance remains in API traces.

Context retrieval is deterministic and lexical; lexical matching is not semantic understanding. There are no embeddings, vector database, reranker, summarizer, hidden model calls, or model credentials in Conceptualize. Context savings are not treated as success unless required task information remains available.

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

Available tools:

| Tool | Purpose |
| --- | --- |
| `conceptualize_map(path?, token_budget?)` | Compact paths, declarations, and line boundaries |
| `conceptualize_search(query, token_budget?, limit?, source_types?, level?)` | Lexical content discovery in repositories or conversations |
| `conceptualize_dependencies(target, token_budget?)` | Direct dependencies, consumers, and related tests |
| `conceptualize_expand(target, token_budget?, source_types?, level?)` | Progressively reveal a repository or conversation result |
| `conceptualize_pack(paths, query?, token_budget?, source_types?, include_dependencies?, include_tests?, include_consumers?)` | Compile bounded context from selected sources |
| `conceptualize_inspect(target, depth?, token_budget?, manifest_only?)` | Preferred entry for a known cross-file target: structure, consumers, tests and bounded source |

Give your connected agent an ordinary repository task, for example: “Replace the Identity role field with explicit permissions while preserving refund authorization.” Use inspect for a known target whose change may affect other files; use map/search for an unknown location, dependencies for a precise relationship question, expand for more detail, and pack for a known bounded source set. Skip isolated edits or already-loaded context. The descriptions do not prescribe a tool chain; the prompt need not mention Conceptualize. Tool adoption still depends on the host agent.

Generate an absolute-path configuration and verify the real connection:

```powershell
python -m conceptualize_mcp.setup config --format codex
# Copy the generated block into Codex config; the key is inherited from your environment.
$env:CONCEPTUALIZE_API_KEY = 'YOUR_CX_KEY'
python -m conceptualize_mcp.setup doctor --api-url http://127.0.0.1:8000
# Other MCP clients: python -m conceptualize_mcp.setup config --format json
```

Doctor initializes a real stdio MCP session, discovers all six tools, calls map and reports its persisted trace ID. Configuration generation never prints your key. Pass project credentials explicitly when a client does not inherit environment variables. The server remains a thin HTTP adapter.

## HTTP operations

```powershell
$headers = @{ Authorization = "Bearer YOUR_CX_KEY" }
$body = @{ operation = "pack"; paths = @("src/auth"); token_budget = 8000;
           include_dependencies = $true; include_tests = $true } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/v1/runtime -Method Post -Headers $headers `
  -ContentType 'application/json' -Body $body
```

`POST /v1/runtime` accepts one of the six operations; OpenAPI documents request validation. `source_types` optionally selects `repository`, `conversation`, `message`, or `repository_file` for generic search/map/expand/inspect/pack. Repository-only requests keep their graph-aware implementation; mixed-source packs use transparent lexical scores and explicit source relationships. `GET /v1/overview`, `/v1/traces`, `/v1/traces/{id}`, `/v1/graph`, and `/v1/git?path=src/auth` expose project-scoped observations. Trace listing supports `limit` and `offset`. Git history and cochanges are based on the last 20 indexed commits. Indexing chooses an available main/master base automatically for other branches; `--base` overrides it. Working-tree and committed branch changes, merge base and diff statistics are recorded separately.

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

Use the existing `conceptualize_search` or `conceptualize_pack` operation with `source_types: ["conversation"]`; select `["repository", "conversation"]` to compile from both. Search uses exact phrase and lexical term overlap, then may include directly related messages. The trace lists scores, signal reasons, source IDs, token cost, status, and whether each unit was already known. MCP session history references unchanged deliveries and returns new content when fingerprints change. No conversation summaries or model-generated topics are created.

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

See [evaluations/V05.md](evaluations/V05.md) for the generic-context architecture, conversation retrieval diagnostic and the limits on model-level evidence. Run the short deterministic context-selection benchmark with `python -m conceptualize_evaluation.conversation_benchmark`; it writes raw paired results to `evaluations/results/v05-conversations.json`. This diagnostic checks selected-text fact coverage and does not invoke or stand in for an AI agent. Fixtures and historical runs are development evidence only; they are not loaded by normal startup or shown in the dashboard.

V0.4 evidence is in [evaluations/V04.md](evaluations/V04.md), [ADOPTION.md](ADOPTION.md), [ADOPTION-SUITE.json](ADOPTION-SUITE.json), [MCP-SURFACE.md](MCP-SURFACE.md), [MCP_SURFACE_PROFILE.json](MCP_SURFACE_PROFILE.json), and five machine-readable cohort/surface reports under `evaluations/results/v04-*.json`. The [runbook](evaluations/ADOPTION-RUNBOOK.md) reproduces six cross-file adoption tasks, three paired receipt repetitions, three paired local negative controls, and a separate connected-but-unused baseline. Reports preserve unavailable measurements explicitly; autonomous invocation is not proof of speed or exploration improvement.

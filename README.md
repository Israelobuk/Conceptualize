# Conceptualize

Deterministic context infrastructure for existing AI coding agents. Conceptualize indexes local repositories, exposes navigable structural context through MCP, packs source into caller budgets, and records every operation for inspection. The host agent reasons and writes code. Conceptualize does neither.

**The context engine uses no AI models, model API calls, embeddings, vectors, or model credentials.** The evaluation harness invokes an external coding agent for comparison; it is separate from the runtime.

## Architecture

```text
AI coding client → MCP (stdio) → FastAPI → context runtime
                                         ├─ Tree-sitter index
                                         ├─ NetworkX relationships
                                         ├─ lexical search + Git metadata
                                         ├─ tiktoken context compiler
                                         ├─ Redis ephemeral cache
                                         └─ PostgreSQL metadata + traces
Next.js dashboard → local server proxy → FastAPI
```

`packages/conceptualize_runtime` is the product: parsing/indexing, graph, Git intelligence, and context operations. It has no API or database dependency. `apps/api` handles auth, persistence, caching, and traces. `apps/mcp` only forwards the five tools. `apps/web` displays observations; it does not select context.

The compact Python package groups these modules instead of publishing five mostly empty packages. LangGraph and LlamaIndex are intentionally deferred: these V1 workflows are direct deterministic functions and neither framework would add meaningful behavior. No LLM/embedding configuration is installed.

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

Seed prints a project ID and a random `cx_…` API key **once**. Copy the key into `CONCEPTUALIZE_API_KEY` in `.env`. The database stores only SHA-256 of a 256-bit random credential plus its recognizable prefix. Each key resolves to one project and its owning user. Re-running seed creates a new project/key; it does not reset existing data.

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
| `conceptualize_search(query, token_budget?, limit?)` | Lexical content, symbol, and path discovery |
| `conceptualize_dependencies(target, token_budget?)` | Direct dependencies, consumers, and related tests |
| `conceptualize_expand(target, token_budget?)` | Deeper inspection of a path, symbol, or lexical query |
| `conceptualize_pack(paths, token_budget?, include_dependencies?, include_tests?, include_consumers?)` | Compile bounded source context |

Give your connected agent an ordinary repository task, for example: “Replace the Identity role field with explicit permissions while preserving refund authorization.” The tool descriptions explain when to map, search, inspect dependencies, expand and pack; the prompt need not mention Conceptualize. Tool adoption still depends on the host agent.

Generate an absolute-path configuration and verify the real connection:

```powershell
python -m conceptualize_mcp.setup config --format codex
# Copy the generated block into Codex config; the key is inherited from your environment.
$env:CONCEPTUALIZE_API_KEY = 'YOUR_CX_KEY'
python -m conceptualize_mcp.setup doctor --api-url http://127.0.0.1:8000
# Other MCP clients: python -m conceptualize_mcp.setup config --format json
```

Doctor initializes a real stdio MCP session, discovers all five tools, calls map and reports its persisted trace ID. Configuration generation never prints your key. Pass project credentials explicitly when a client does not inherit environment variables. The server remains a thin HTTP adapter.

## HTTP operations

```powershell
$headers = @{ Authorization = "Bearer YOUR_CX_KEY" }
$body = @{ operation = "pack"; paths = @("src/auth"); token_budget = 8000;
           include_dependencies = $true; include_tests = $true } | ConvertTo-Json
Invoke-RestMethod http://127.0.0.1:8000/v1/runtime -Method Post -Headers $headers `
  -ContentType 'application/json' -Body $body
```

`POST /v1/runtime` accepts one of the five operations; OpenAPI documents request validation. `GET /v1/overview`, `/v1/traces`, `/v1/traces/{id}`, `/v1/graph`, and `/v1/git?path=src/auth` expose project-scoped observations. Trace listing supports `limit` and `offset`. Git history and cochanges are based on the last 20 indexed commits. Indexing chooses an available main/master base automatically for other branches; `--base` overrides it. Working-tree and committed branch changes, merge base and diff statistics are recorded separately.

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

## Real-agent evaluation

See [evaluations/README.md](evaluations/README.md) for paired CONTROL/CONCEPTUALIZE runs, three cross-file tasks, independent checks and JSON evidence. [evaluations/DEMO.md](evaluations/DEMO.md) records the actual demonstration, including failed setup attempts and limitations. The evaluator is an external-agent test harness; it adds no model calls to the context runtime.

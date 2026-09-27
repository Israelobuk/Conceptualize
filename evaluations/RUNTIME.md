# Deterministic context runtime milestone

Conceptualize does not run a model. Tree-sitter structure, lexical identifiers, graph edges, Git metadata and session delivery records determine context. Existing API, SQL database, Redis cache, stdio MCP bridge and dashboard remain in place.

## Disclosure and session contract

The existing five tools remain: `map`, `search`, `dependencies`, `expand`, `pack`. V0.3 adds one tool, `inspect(target, depth=1, include_dependencies=true, include_consumers=true, include_tests=true, include_git=true, token_budget=4000, manifest_only=false)`, combining a compact manifest, structural relationships and bounded priority source. Choose the fewest useful calls; no complete tool chain is required. `map` returns file/symbol boundaries; `dependencies` returns signatures and relationships; `expand(level="structure")` inspects structure and `expand(level="source")` returns specifically requested source; `pack` assembles bounded source coverage. Search is lexical and may include matching snippets. Unresolved entities yield no invented relationships.

Every stdio server process has a session ID. API sessions are isolated by project and ID, persisted in `mcp_sessions.context_state`, and updated atomically with successful traces. Delivery records identify paths, symbols, disclosure levels, fingerprints, file hashes, source ranges and supplying trace/operation. Packs are traced operations with their individual delivered units. Maps/structure never count as already-delivered source. Source ranges merge across operations; a partial symbol read does not mark the rest of a file known. Truncated fallback content is conservatively not remembered as a complete range. The last 1,000 delivery records are retained; eviction can cause a conservative resend.

Unchanged known content is referenced through `previous_context`, including supplying operation, stable context ID and ranges. V0.3 refreshes the repository before each operation, reparses changed files and invalidates dependent structure and cached results. Fast change detection uses size/mtime/ctime; adversarial edits preserving all metadata require `force_refresh=true`, which reads files again. That flag also explicitly resends known context. File, symbol, range, dependency and bundle fingerprints derive deterministically from content and dependencies. New processes start fresh sessions unless `CONCEPTUALIZE_SESSION_ID` is explicitly configured for a resumed session. No inference about the agent's understanding is made.

## Selection

Default weights are in `packages/conceptualize_runtime/scoring.py`. API `score_weights` and MCP pack `score_weights` override named integer weights (absolute bound 1,000); unknown signals are rejected. Additive reasons expose each weight and structural evidence. Explicit entity, dependency, consumer, referenced symbol, related test, branch/working-tree modifications, observed Git co-change, same directory, path proximity, graph distance, prior access and redundant content affect scores. Test/path and co-change relations are labelled heuristics, not proof of relevance. Scores are structural priority, not calibrated probabilities.

Pack preserves explicit requests first, then relationship priority tiers, then score per marginal delivery cost, score and deterministic path ties. It is a transparent greedy coverage heuristic, not a global knapsack optimum. Dependencies/consumers/tests precede path-only neighbors. Each candidate records score reasons, selected/omitted/referenced/truncated status, marginal/full token costs, distance, known status and omission reason. The compiled delta respects the exact caller token budget; API metadata is outside that budget. No lower token count automatically implies more useful context.

Delta accounting reports full candidate context, full selected context, previously supplied tokens, new compiled tokens, duplicate tokens avoided and forced duplicate retransmission. Full blocks and deltas have different headers/separators; BPE boundaries mean totals need not add exactly. These quantities measure redundant transmission, not task quality. Referenced source can remain logically selected without being included again.

Trace details expose scoring and delta evidence in the existing panel. Apply migration `0002_session_context` with `alembic upgrade head`, restart API/MCP and reindex for Tree-sitter v3 signatures. PostgreSQL/Redis remain the normal services; SQLite and unavailable Redis are explicitly local QA configurations.

## Reproduce evidence

Use the installed virtual environment and a functioning native Codex executable. Same task prompts are supplied in both modes; only enabled mode receives the Conceptualize MCP server. Other MCP servers are disabled in both modes. Model, CLI version, baseline commit, prompt hash and suite-definition hash must match before comparison. Successful agents also have to pass independently supplied checks. Failed/timeout/runner attempts retain raw evidence.

```powershell
.venv/Scripts/python.exe -m conceptualize_evaluation.suite run --output evaluations/runs/new-suite --codex <native-codex.exe> --model <same-model> --api-url http://127.0.0.1:8000 --workers 2
.venv/Scripts/python.exe -m conceptualize_evaluation.suite report --output evaluations/runs/new-suite
.venv/Scripts/python.exe -m conceptualize_evaluation.profile --output evaluations/results/new-overhead.json --api-url http://127.0.0.1:8000
```

The runner's `DATABASE_URL` must name the same database used by the API because isolated fixture projects and project keys are provisioned there. Keys stay out of persisted result files. Each task pair runs sequentially; two independent pairs may run concurrently. Alternating order reduces a fixed order effect but is not randomized replication. Use `--workers 1` for serial timing measurements.

Ten tasks cover shared receipts, authorization consumers, notification retry dependencies, configured limits, Unicode customer identity, pagination hidden consumers, stock shared records, UTC round trips, slug/test discovery, and current-branch shipping tariffs. These are small deterministic fixtures; they do not establish performance in large real repositories.

Reports preserve elapsed time, test success, MCP calls, compiled context and observed literal-read/search/listing evidence. Total filesystem reads and corrective iterations remain null where not instrumented. Relevant-file coverage uses modified Python source and test files from successful independently checked changes as an explicitly imperfect post-hoc proxy. Unchanged necessary files can be misclassified. Recall is source delivered before a supported observed read, not a claim all other reading is observable. Raw event steps identify early discovery. Candidate files surfaced but absent from the proxy are reported without silently removing them.

## Performance interpretation

The earlier 93-second control / 122-second enabled pair passed in both modes and does not demonstrate speed improvement. Preserve that baseline. New comparisons report actual observations rather than a predetermined conclusion.

Stage timers include graph traversal/build, scoring, context compilation, snapshot loading, cache attempts, tracing before commit and commit, plus MCP HTTP round trip. The profiler separately measures stdio startup and wall time. Graph build is nested inside snapshot timing, server stages inside HTTP timing, and HTTP inside stdio wall time; do not sum overlapping timers. Git analysis occurs during indexing; fixture provisioning/indexing is outside agent elapsed time. Profiles with unavailable Redis reveal failed-cache costs rather than normal Redis throughput. JSON byte size exposes metadata overhead beyond compiled token counts.


Post-profile optimizations reuse an MCP-lifespan HTTP client, omit duplicate source/symbol/evidence metadata from MCP responses (full evidence remains in the trace API), and impose a five-second cache retry cooldown after Redis connection errors. The runtime still recomputes correctly during cache outages and automatically retries after cooldown. Class/method source ranges are merged before compilation to avoid overlapping delivery. Before/after profiling results are separate from the original benchmark cohort; no optimized-agent speed claim is inferred.

Use `conceptualize_evaluation.suite run --tasks times,slugs,shipping` for a separate recovery cohort. Configuration records selected tasks, workers, timeout and a runtime source hash. Existing run directories are never overwritten. Reports distinguish provider failures, required MCP startup failures, agent timeouts, usage limits and independent-check timeouts. Unequal agent timeout limits mark a pair non-comparable. Successful matched pairs without logged provider disruption are shown separately while all original attempts remain visible. Even this stratum does not control every network/model timing factor. Strict recall before any independent read stays null; observed subsequent reads establish the narrower source-discovery ordering metric, while source delivered without an observed read is reported separately.

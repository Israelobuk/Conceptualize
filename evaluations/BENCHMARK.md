# Context runtime evidence

The deterministic runtime, progressive disclosure, durable session records, range-aware deltas and scored budget selection are implemented. No model runs inside Conceptualize. Architecture and dashboard layout are preserved; existing trace details expose scoring, known-context references and timing.

## Actual external-agent results

All runs used **gpt-6-sol** and the same native Codex CLI. Within each matched pair the task prompt, fixture commit and suite definition agree. Raw events, execution records, traces, check outputs and diffs remain under `evaluations/runs/`.

| Cohort | Tasks / attempts | Control passed | Enabled passed | Successful matched pairs |
|---|---:|---:|---:|---:|
| Original runtime | 10 / 20 | 7 | 7 | 7 |
| Separate recovery after overhead fixes | 3 / 6 | 3 | 2 | 2 |

Nine distinct tasks have a successful matched pair. Shipping's original pair encountered provider failures; its recovery control passed, while the enabled recovery was interrupted by the account usage limit before completing its change. The enabled recovery is blocked/incomplete: it demonstrates neither success nor a completed task failure. Raw check outcomes remain preserved. The original time-task enabled attempt failed required MCP startup; its shorter control recovery timeout makes that original pair non-comparable. Stock control succeeded after provider interruptions, contaminating its elapsed time.

Full per-task success, elapsed time, observed files, relevant discovered files, unnecessary-observed proxy, repeated reads, compiled context, unknown corrective iterations, MCP calls and failure signals are in:

- [Original ten-task report](results/runtime-suite-v1.md), [machine-readable results](results/runtime-suite-v1.json).
- [Separate three-task recovery report](results/runtime-suite-recovery.md), [machine-readable results](results/runtime-suite-recovery.json).

Original attempts are preserved rather than replaced by retries. Do not combine cohorts into a controlled before/after speed experiment. The earlier 93-second control / 122-second enabled result also remains preserved and does not demonstrate improvement.

## Where the evidence helps, hurts, or remains inconclusive

**Observable discovery benefit:** In the slug recovery, pack surfaced the subsequently modified formatter and test file at raw event step 15, before their supported independent read commands. This is verified ordering within the available telemetry, not proof every filesystem access is captured. Its enabled run still took 127.575 seconds versus 85.701 seconds for control.

**Lower observed exploration in some runs:** The six original successful matched pairs without logged provider disruption had 28 observed unique files in control versus 20 enabled, with mean elapsed times of 78.121 and 118.763 seconds respectively. These counts are lower bounds from supported commands. They do not prove eight fewer total files were inspected. Receipt source was supplied through MCP without a supported observed read; strict independent-read ordering there is unknown.

**No observed read-count benefit in other runs:** Customers and pagination each had four observed files in both modes in the original cohort. Retry's enabled run attempted a map call that automatic approval review rejected before it reached the API, and inspected five observed files versus four control. There were zero successful runtime operations; this cannot measure a ranking effect. Many packs arrived after supported manual reads, so source disclosure was late for those files.

**Costs and failures:** Enabled completion was slower in the clean original stratum and in both successful recovery pairs. Large map/selection metadata and broad structural candidates add transmission and attention cost. Original map-containing operations surfaced 25–28 files outside the modified-file proxy in several tasks; unchanged necessary files can also fall outside that proxy, so these are not definitive irrelevant-file counts. Required MCP startup failed in one original attempt. Provider interruptions and the account limit are separately recorded.

**Session deltas work, but no agent-session savings were demonstrated here:** Actual agent runs recorded zero duplicate context tokens avoided. The separate real MCP protocol profile deliberately repeats structure and pack; the repeated pack returns zero new compiled tokens and references prior context, avoiding 888 estimated block tokens. This proves deterministic delivery behavior, not improved agent task utility or speed.

The report leaves total filesystem reads, strict relevant-file recall before any independent read, and corrective iterations unavailable. Relevant-file coverage uses Python source/test files modified in independently checked successful changes as a post-hoc proxy. It misses unchanged required dependencies and can include incidental changes. Searches, grep operations, listings, supported reads, unresolved read commands, early-discovery event steps, protocol byte sizes and runtime timing are retained explicitly. No positive product claim follows from token reduction alone.

## Runtime overhead

[Before](results/runtime-overhead-before.json) and [after](results/runtime-overhead-after.json) record actual stdio MCP calls through HTTP, database and runtime on the same fixture; no agent/model participates.

| Call | Before wall ms | After wall ms | Before / after structured JSON bytes |
|---|---:|---:|---:|
| Map | 777.291 | 457.784 | 61,520 / 37,352 |
| Structure | 547.774 | 130.478 | 11,911 / 7,093 |
| Dependencies | 540.748 | 110.043 | 7,509 / 6,403 |
| Source | 552.235 | 109.287 | 7,719 / 6,057 |
| Pack | 587.242 | 124.297 | 43,413 / 24,772 |
| Repeated pack | 579.219 | 120.024 | 26,061 / 22,649 |

Before optimization, unavailable QA Redis cost roughly 411–424 ms per call in repeated failed read/write attempts. A five-second failure cooldown avoids immediate retries while recomputing valid context; the first after-profile miss still costs 221 ms, with subsequent cache checks around 0.01 ms. The MCP bridge now reuses its lifespan HTTP client. Transport projection omits duplicate source/symbol/evidence metadata while full candidate provenance remains inspectable in the trace API/dashboard. Overlapping explicit class/method ranges also merge before compilation.

Graph traversal, scoring and compilation take milliseconds on this fixture; database and graph-building timings are retained per call. [Actual Git analysis](results/git-overhead.json) took about 1.25 seconds during indexing of a benchmark repository, outside agent elapsed time. Stdio startup remains about 2.8–3.0 seconds. Normal PostgreSQL/available Redis and large repositories were not profiled here; SQLite and deliberately unavailable Redis are local QA conditions.

Original successful enabled runs spent roughly 0.66–1.96 seconds in measured MCP HTTP calls when tools were invoked. Those calls plus profiled startup cannot by themselves account for the roughly 41-second clean-stratum mean completion gap. The remainder includes unmeasured host/model/network work, response processing and changed agent behavior; this harness cannot cleanly apportion those causes. Timers overlap (graph build inside snapshot, server inside HTTP, HTTP inside stdio wall time) and must not be added indiscriminately.

## Reproduction and verification

[Runtime contract and commands](RUNTIME.md) document weights, progressive levels, force refresh, snapshot invalidation, delta accounting, session retention, migration and paired suite/profile commands. Configuration for the recovery cohort records selected tasks, timeout, workers and a runtime source hash. Existing evidence directories are never overwritten by the runner.

Validation: **48 Python tests**, lint, frontend type checking, **4 frontend tests** and production build passed. Real stdio MCP integration is included. The existing dashboard at `http://127.0.0.1:3019/` passed overview → trace → score/delta → overview checks at 1589×990 and 390×844 with no page/console errors. Desktop remains one viewport without scrolling; mobile retains its existing vertical layout. The initial local database was backed up and migrated to session state, then reindexed for v3 signatures. No unrelated UI features were added.

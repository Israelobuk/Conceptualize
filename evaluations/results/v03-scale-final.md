# Final protocol scale profile

Scripted real MCP client, four calls per condition. No model/agent. Nearest-rank P50/P95, not causal speed estimates. Metadata bytes include more than compiled context; budgets apply to context text.

| Python files | Session | Call errors | Roundtrip ms per call | Response bytes per call | Duplicate tokens avoided per call |
|---:|---|---:|---|---|---|
| 60 | cold | 0 | 559, 134, 460, 1177 | 56010, 10055, 56008, 56067 | 0, 0, 0, 0 |
| 60 | warm | 0 | 242, 135, 189, 1176 | 56003, 10042, 58189, 66937 | 0, 91, 2984, 1026 |
| 400 | cold | 0 | 1780, 1086, 2660, 3184 | 109236, 10071, 109240, 108333 | 0, 0, 0, 0 |
| 400 | warm | 0 | 2500, 344, 1668, 3500 | 109267, 10049, 180587, 249120 | 0, 91, 3872, 3940 |
| 2000 | cold | 0 | 8700, 1388, 7234, 9063 | 214857, 10069, 214891, 213950 | 0, 0, 0, 0 |
| 2000 | warm | 0 | 9130, 1309, 9601, 11118 | 214889, 10096, 286214, 354821 | 0, 91, 3872, 3940 |

## Stage percentiles across 24 calls

| Stage | Samples | Missing | P50 ms | P95 ms |
|---|---:|---:|---:|---:|
| transport_ms | 24 | 0 | 47.844 | 353.191 |
| index_lookup_ms | 24 | 0 | 218.894 | 1007.643 |
| graph_ms | 24 | 0 | 75.601 | 701.313 |
| git_ms | 24 | 0 | 0.758 | 878.704 |
| scoring_ms | 24 | 0 | 29.74 | 288.52 |
| packing_ms | 24 | 0 | 75.544 | 6115.782 |
| cache_ms | 24 | 0 | 207.253 | 440.526 |
| trace_write_ms | 24 | 0 | 22.026 | 208.902 |
| total_runtime_ms | 24 | 0 | 1305.038 | 9337.191 |

Stage values overlap. Transport is an HTTP residual including serialization/authentication, not pure wire latency. Deliberately unavailable Redis and SQLite are QA conditions. Git history unavailable in these generated scale repositories; the harmless edit exercises filesystem freshness, not a multi-commit Git scenario. Warm stages retain server context, cold creates a fresh MCP process/session each time. Shared host and fixed order can affect timing.

Full raw responses: `evaluations/runs/v03-protocol-final`. Per-size stage distributions and manifests: `evaluations/results/v03-scale-final.json`. Earlier failed 2,000-file conditions and intermediate optimized results remain separately preserved.
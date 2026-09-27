# Protocol scale profile

Scripted real MCP client; no agent/model. Four calls per condition. Budgets apply to compiled context, not full response metadata. Separate profiles do not demonstrate agent speed improvement.

| Python files | Session | Errors | Roundtrip ms | JSON bytes | Duplicate tokens avoided |
|---:|---|---:|---|---|---|
| 60 | cold | 0 | 576, 177, 511, 1068 | 64993, 12352, 65014, 65015 | 0, 0, 0, 0 |
| 60 | warm | 0 | 484, 175, 238, 1063 | 64991, 12394, 78788, 76500 | 0, 91, 2984, 1026 |
| 400 | cold | 0 | 1811, 440, 1816, 2430 | 127935, 12323, 127935, 127048 | 0, 0, 0, 0 |
| 400 | warm | 0 | 1869, 376, 1700, 3218 | 127921, 12387, 221811, 269161 | 0, 91, 3872, 3940 |
| 2000 | cold | 0 | 11842, 1349, 8341, 9097 | 233566, 12341, 233552, 232633 | 0, 0, 0, 0 |
| 2000 | warm | 0 | 8459, 1346, 11434, 12474 | 233548, 12399, 327452, 374855 | 0, 91, 3872, 3940 |

## Stage percentiles

Nearest-rank P50/P95 across these calls; per-condition distributions and missing counts remain in JSON.

| Stage | Count | Missing | P50 ms | P95 ms |
|---|---:|---:|---:|---:|
| transport_ms | 24 | 0 | 42.352 | 254.293 |
| index_lookup_ms | 24 | 0 | 204.365 | 989.643 |
| graph_ms | 24 | 0 | 76.405 | 763.837 |
| git_ms | 24 | 0 | 0.465 | 780.412 |
| scoring_ms | 24 | 0 | 33.643 | 277.61 |
| packing_ms | 24 | 0 | 79.455 | 7702.09 |
| cache_ms | 24 | 0 | 209.823 | 499.955 |
| trace_write_ms | 24 | 0 | 19.715 | 247.25900000000001 |
| total_runtime_ms | 24 | 0 | 1268.871 | 11093.159 |

Scripted calls do not measure agent task success or exploration.
Transport is an HTTP client residual, not pure wire latency.
Stage timers are approximate; roundtrip includes serialization.
Sequential order and shared host activity can affect latency.

Raw response directory: C:\Users\isobu\OneDrive\Desktop\Projects\Conceptualize\evaluations\runs\v03-protocol-release
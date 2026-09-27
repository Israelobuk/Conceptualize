# V0.2 versus V0.3

All original ten tasks are retained. Separate executions are observational cohorts, not a controlled runtime-version causal experiment. Unknown values remain unavailable. Relevant files use the modified-source/test proxy; unchanged required dependencies are not fully measured.

| Task | Mode | V0.2 outcome | V0.3 outcome | V0.2 / V0.3 seconds | Observed files | MCP attempts |
|---|---|---|---|---:|---:|---:|
| receipts | control | success | success | 88.911 / 100.03 | 6 / 1 | 0 / 0 |
| receipts | conceptualize | success | success | 114.075 / 105.343 | 0 / 6 | 3 / 0 |
| auth | control | success | success | 93.151 / 84.493 | 5 / 5 | 0 / 0 |
| auth | conceptualize | success | success | 120.986 / 93.35 | 3 / 3 | 3 / 0 |
| retry | control | success | success | 63.197 / 67.027 | 4 / 4 | 0 / 0 |
| retry | conceptualize | success | success | 120.655 / 109.708 | 5 / 1 | 1 / 0 |
| limits | control | success | success | 67.753 / 81.554 | 5 / 1 | 0 / 0 |
| limits | conceptualize | success | success | 133.115 / 103.86 | 4 / 5 | 2 / 0 |
| customers | control | success | success | 84.601 / 61.766 | 4 / 0 | 0 / 0 |
| customers | conceptualize | success | success | 122.297 / 108.456 | 4 / 4 | 3 / 0 |
| pages | control | success | success | 71.115 / 71.055 | 4 / 1 | 0 / 0 |
| pages | conceptualize | success | success | 101.448 / 109.441 | 4 / 0 | 1 / 0 |
| stock | control | success | success | 1580.864 / 80.202 | 1 / 6 | 0 / 0 |
| stock | conceptualize | success | success | 127.633 / 100.304 | 3 / 6 | 3 / 0 |
| times | control | incomplete | success | 60.182 / 84.65 | 5 / 0 | 0 / 0 |
| times | conceptualize | incomplete | success | 624.577 / 99.672 | 0 / 4 | 0 / 0 |
| slugs | control | incomplete | success | 34.836 / 92.594 | 0 / 0 | 0 / 0 |
| slugs | conceptualize | incomplete | success | 19.846 / 103.614 | 0 / 0 | 0 / 0 |
| shipping | control | incomplete | success | 16.826 / 80.25 | 0 / 4 | 0 / 0 |
| shipping | conceptualize | incomplete | success | 19.278 / 94.711 | 0 / 1 | 0 / 0 |

## Aggregate and stage percentiles

```json
{
  "v02": {
    "control": {
      "available_attempts": 10,
      "successful_attempts": 7,
      "mean_elapsed_seconds_all_available": 216.1436,
      "observed_unique_files_sum": 34,
      "mcp_attempts": 0,
      "successful_mcp_calls": 0,
      "stage_statistics": {
        "transport_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "index_lookup_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "graph_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "git_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "scoring_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "packing_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "cache_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "trace_write_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "total_runtime_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        }
      }
    },
    "conceptualize": {
      "available_attempts": 10,
      "successful_attempts": 7,
      "mean_elapsed_seconds_all_available": 150.391,
      "observed_unique_files_sum": 23,
      "mcp_attempts": 16,
      "successful_mcp_calls": 15,
      "stage_statistics": {
        "transport_ms": {
          "count": 0,
          "missing": 15,
          "p50": null,
          "p95": null
        },
        "index_lookup_ms": {
          "count": 0,
          "missing": 15,
          "p50": null,
          "p95": null
        },
        "graph_ms": {
          "count": 0,
          "missing": 15,
          "p50": null,
          "p95": null
        },
        "git_ms": {
          "count": 0,
          "missing": 15,
          "p50": null,
          "p95": null
        },
        "scoring_ms": {
          "count": 0,
          "missing": 15,
          "p50": null,
          "p95": null
        },
        "packing_ms": {
          "count": 0,
          "missing": 15,
          "p50": null,
          "p95": null
        },
        "cache_ms": {
          "count": 0,
          "missing": 15,
          "p50": null,
          "p95": null
        },
        "trace_write_ms": {
          "count": 0,
          "missing": 15,
          "p50": null,
          "p95": null
        },
        "total_runtime_ms": {
          "count": 0,
          "missing": 15,
          "p50": null,
          "p95": null
        }
      }
    }
  },
  "v03": {
    "control": {
      "available_attempts": 10,
      "successful_attempts": 10,
      "mean_elapsed_seconds_all_available": 80.3621,
      "observed_unique_files_sum": 22,
      "mcp_attempts": 0,
      "successful_mcp_calls": 0,
      "stage_statistics": {
        "transport_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "index_lookup_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "graph_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "git_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "scoring_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "packing_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "cache_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "trace_write_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "total_runtime_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        }
      }
    },
    "conceptualize": {
      "available_attempts": 10,
      "successful_attempts": 10,
      "mean_elapsed_seconds_all_available": 102.8459,
      "observed_unique_files_sum": 30,
      "mcp_attempts": 0,
      "successful_mcp_calls": 0,
      "stage_statistics": {
        "transport_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "index_lookup_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "graph_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "git_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "scoring_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "packing_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "cache_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "trace_write_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        },
        "total_runtime_ms": {
          "count": 0,
          "missing": 0,
          "p50": null,
          "p95": null
        }
      }
    }
  }
}
```

CLI arrival spans are retained per operation; they include buffering and do not establish model idle time. P50/P95 use nearest rank, report sample counts and leave missing stages null. HTTP transport is a client residual. Stage timers overlap; do not sum them as a complete time decomposition.

Version identity checks are in JSON. V0.2 recovery, rejected calls, blocked Shipping, and V0.3 harness-contaminated attempts remain in separate diagnosis reports and raw directories. No attempt is silently replaced.
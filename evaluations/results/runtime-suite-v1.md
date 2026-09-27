# Conceptualize paired benchmark

Actual external-agent runs. Pairs validate identical task, prompt, baseline, model, CLI version and suite definition. One run per mode/task; synthetic fixture, not general product evidence.

Observed reads are lower bounds from supported successful literal read commands. Relevance is a post-hoc modified-source-file proxy after independent checks pass. Unchanged but necessary files may be misclassified. Source recall is before an observed read, not proof no other read happened. Corrective iterations and complete filesystem access are unavailable (—). Context tokens measure compiled source/structure, not the entire MCP JSON response. Token savings are redundant transmission accounting, not utility.

| Task | Mode | Passed | Seconds | Observed files | Relevant discovered* | Unnecessary observed* | Repeated reads | Context tokens | Corrections | MCP calls | Provider disruption |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---|
| receipts | control | True | 88.911 | 6 | shop/checkout.py, shop/contracts.py, shop/orders.py, shop/warehouse.py, test_shop.py | 1 | 0 | 0 | — | 0 | False |
| receipts | conceptualize | True | 114.075 | 0 | shop/checkout.py, shop/contracts.py, shop/orders.py, shop/warehouse.py, test_shop.py | 0 | 0 | 1415 | — | 3 | False |
| auth | control | True | 93.151 | 5 | shop/auth.py, shop/refunds.py, test_shop.py | 2 | 1 | 0 | — | 0 | False |
| auth | conceptualize | True | 120.986 | 3 | shop/auth.py, shop/refunds.py, test_shop.py | 0 | 0 | 1291 | — | 3 | False |
| retry | control | True | 63.197 | 4 | shop/notifications.py, test_shop.py | 2 | 0 | 0 | — | 0 | False |
| retry | conceptualize | True | 120.655 | 5 | shop/notifications.py, test_shop.py | 3 | 0 | 0 | — | 0 | False |
| limits | control | True | 67.753 | 5 | shop/settings.py, test_shop.py | 3 | 0 | 0 | — | 0 | False |
| limits | conceptualize | True | 133.115 | 4 | shop/settings.py, test_shop.py | 2 | 0 | 961 | — | 2 | False |
| customers | control | True | 84.601 | 4 | shop/customer_keys.py | 3 | 0 | 0 | — | 0 | False |
| customers | conceptualize | True | 122.297 | 4 | shop/customer_keys.py, test_shop.py | 2 | 0 | 1306 | — | 3 | False |
| pages | control | True | 71.115 | 4 | shop/export_job.py, shop/settings.py, test_shop.py | 1 | 0 | 0 | — | 0 | False |
| pages | conceptualize | True | 101.448 | 4 | shop/export_job.py, shop/settings.py | 2 | 0 | 481 | — | 1 | False |
| stock | control | True | 1580.864 | 1 | test_shop.py | 0 | 0 | 0 | — | 0 | True |
| stock | conceptualize | True | 127.633 | 3 | shop/reconciliation.py, shop/stock.py, test_shop.py | 0 | 0 | 1239 | — | 3 | False |
| times | control | False | 60.182 | 5 | — | — | 0 | 0 | — | 0 | False |
| times | conceptualize | False | 624.577 | 0 | — | — | 0 | 0 | — | 0 | False |
| slugs | control | False | 34.836 | 0 | — | — | 0 | 0 | — | 0 | True |
| slugs | conceptualize | False | 19.846 | 0 | — | — | 0 | 0 | — | 0 | True |
| shipping | control | False | 16.826 | 0 | — | — | 0 | 0 | — | 0 | True |
| shipping | conceptualize | False | 19.278 | 0 | — | — | 0 | 0 | — | 0 | True |

*Relative to the modified-source proxy; not a definitive unnecessary-work count.

## Aggregate

```json
{
  "control": {
    "runs": 10,
    "successes": 7,
    "mean_seconds": 216.1436,
    "median_seconds": 69.434,
    "provider_disrupted_runs": 3,
    "observed_files_successful_runs": 29,
    "observed_files_total": 34,
    "observed_repeated_reads_total": 1,
    "compiled_context_tokens_total": 0
  },
  "conceptualize": {
    "runs": 10,
    "successes": 7,
    "mean_seconds": 150.391,
    "median_seconds": 120.82050000000001,
    "provider_disrupted_runs": 2,
    "observed_files_successful_runs": 23,
    "observed_files_total": 23,
    "observed_repeated_reads_total": 0,
    "compiled_context_tokens_total": 6693
  }
}
```

Full source recall, early discovery event steps, surfaced non-proxy files, duplicate retransmission and avoidance, searches, grep operations, listings and read evidence are in summary.json and each run/result.json. Raw agent events, traces, test outputs and diffs remain in each run directory.

Missing tasks: none
Non-comparable attempts: times
Failure signals are retained in summary.json and per-run results, including required MCP startup and account usage-limit failures; failures are not silently discarded.

Elapsed differences combine agent behavior and tool overhead. Stage timing in raw traces measures runtime overhead; timings overlap and must not be summed blindly. No conclusion of superiority follows automatically from these measurements.
Provider-disrupted runs, including successful recovery, contaminate elapsed comparisons. Failed outcomes provide no relevance ground truth. Relevant discovered combines observed reads and MCP surfacing relative to the modified-source proxy; MCP-only source recall remains separate in JSON.

## Successful matched pairs without logged provider disruption

This separate stratum is not evidence that all network or model timing was controlled. Every excluded attempt remains in the full table above.

Tasks: receipts, auth, retry, limits, customers, pages

```json
{
  "control": {
    "pairs": 6,
    "mean_seconds": 78.12133333333333,
    "median_seconds": 77.858,
    "observed_files_total": 28
  },
  "conceptualize": {
    "pairs": 6,
    "mean_seconds": 118.76266666666666,
    "median_seconds": 120.82050000000001,
    "observed_files_total": 20
  }
}
```

## Context delivery evidence

| Task | MCP relevant source files | Confirmed source-before-observed-read fraction* | Non-proxy files surfaced | Duplicate tokens avoided | Duplicate tokens resent |
|---|---|---:|---:|---:|---:|
| receipts | shop/checkout.py, shop/contracts.py, shop/orders.py, shop/warehouse.py, test_shop.py | 0.0 | 25 | 0 | 0 |
| auth | shop/auth.py, shop/refunds.py, test_shop.py | 0.0 | 27 | 0 | 0 |
| retry | — | 0.0 | 0 | 0 | 0 |
| limits | shop/settings.py | 0.0 | 28 | 0 | 0 |
| customers | shop/customer_keys.py, test_shop.py | 0.0 | 28 | 0 | 0 |
| pages | — | 0.0 | 27 | 0 | 0 |
| stock | shop/reconciliation.py, shop/stock.py, test_shop.py | 0.0 | 27 | 0 | 0 |
| times | — | — | — | — | — |
| slugs | — | — | — | — | — |
| shipping | — | — | — | — | — |

*Only an observed subsequent read establishes ordering. Files surfaced without any observed read are listed separately in JSON; strict recall before any independent read remains unavailable. Structural map exposure is separate from source. Non-proxy counts can include unchanged necessary dependencies; do not interpret them as definitive waste.

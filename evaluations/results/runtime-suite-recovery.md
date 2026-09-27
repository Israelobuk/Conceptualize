# Conceptualize paired benchmark

Actual external-agent runs. Pairs validate identical task, prompt, baseline, model, CLI version and suite definition. One run per mode/task; synthetic fixture, not general product evidence.

Observed reads are lower bounds from supported successful literal read commands. Relevance is a post-hoc modified-source-file proxy after independent checks pass. Unchanged but necessary files may be misclassified. Source recall is before an observed read, not proof no other read happened. Corrective iterations and complete filesystem access are unavailable (—). Context tokens measure compiled source/structure, not the entire MCP JSON response. Token savings are redundant transmission accounting, not utility.

| Task | Mode | Passed | Seconds | Observed files | Relevant discovered* | Unnecessary observed* | Repeated reads | Context tokens | Corrections | MCP calls | Provider disruption |
|---|---|---|---:|---:|---|---:|---:|---:|---:|---:|---|
| times | control | True | 106.344 | 1 | — | 1 | 0 | 0 | — | 0 | False |
| times | conceptualize | True | 138.201 | 1 | shop/time_format.py, shop/time_reader.py | 1 | 0 | 306 | — | 2 | False |
| slugs | control | True | 85.701 | 4 | shop/slugs.py, test_shop.py | 2 | 0 | 0 | — | 0 | False |
| slugs | conceptualize | True | 127.575 | 4 | shop/slugs.py, test_shop.py | 2 | 0 | 1318 | — | 3 | False |
| shipping | control | True | 81.289 | 6 | shop/shipping.py, test_shop.py | 4 | 0 | 0 | — | 0 | False |
| shipping | conceptualize | False | 70.567 | 0 | — | — | 0 | 1289 | — | 3 | False |

*Relative to the modified-source proxy; not a definitive unnecessary-work count.

## Aggregate

```json
{
  "control": {
    "runs": 3,
    "successes": 3,
    "mean_seconds": 91.11133333333333,
    "median_seconds": 85.701,
    "provider_disrupted_runs": 0,
    "observed_files_successful_runs": 11,
    "observed_files_total": 11,
    "observed_repeated_reads_total": 0,
    "compiled_context_tokens_total": 0
  },
  "conceptualize": {
    "runs": 3,
    "successes": 2,
    "mean_seconds": 112.11433333333333,
    "median_seconds": 127.575,
    "provider_disrupted_runs": 0,
    "observed_files_successful_runs": 5,
    "observed_files_total": 5,
    "observed_repeated_reads_total": 0,
    "compiled_context_tokens_total": 2913
  }
}
```

Full source recall, early discovery event steps, surfaced non-proxy files, duplicate retransmission and avoidance, searches, grep operations, listings and read evidence are in summary.json and each run/result.json. Raw agent events, traces, test outputs and diffs remain in each run directory.

Missing tasks: none
Non-comparable attempts: none
Failure signals are retained in summary.json and per-run results, including required MCP startup and account usage-limit failures; failures are not silently discarded.

Elapsed differences combine agent behavior and tool overhead. Stage timing in raw traces measures runtime overhead; timings overlap and must not be summed blindly. No conclusion of superiority follows automatically from these measurements.
Provider-disrupted runs, including successful recovery, contaminate elapsed comparisons. Failed outcomes provide no relevance ground truth. Relevant discovered combines observed reads and MCP surfacing relative to the modified-source proxy; MCP-only source recall remains separate in JSON.

## Successful matched pairs without logged provider disruption

This separate stratum is not evidence that all network or model timing was controlled. Every excluded attempt remains in the full table above.

Tasks: times, slugs

```json
{
  "control": {
    "pairs": 2,
    "mean_seconds": 96.0225,
    "median_seconds": 96.0225,
    "observed_files_total": 5
  },
  "conceptualize": {
    "pairs": 2,
    "mean_seconds": 132.888,
    "median_seconds": 132.888,
    "observed_files_total": 5
  }
}
```

## Context delivery evidence

| Task | MCP relevant source files | Confirmed source-before-observed-read fraction* | Non-proxy files surfaced | Duplicate tokens avoided | Duplicate tokens resent |
|---|---|---:|---:|---:|---:|
| times | — | 0.0 | 1 | 0 | 0 |
| slugs | shop/slugs.py, test_shop.py | 1.0 | 28 | 0 | 0 |
| shipping | — | — | — | — | — |

*Only an observed subsequent read establishes ordering. Files surfaced without any observed read are listed separately in JSON; strict recall before any independent read remains unavailable. Structural map exposure is separate from source. Non-proxy counts can include unchanged necessary dependencies; do not interpret them as definitive waste.

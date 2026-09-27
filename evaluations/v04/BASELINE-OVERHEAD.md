# Connected but unused baseline

Eight real gpt-6-sol trials used the identical arithmetic prompt and repository baseline. Four matched repetitions alternated control/connected order. All answers were correct; no trial invoked MCP.

| Repetition | Mode | Elapsed seconds | First message ms | Input tokens | Cached input | Output tokens |
|---|---|---:|---:|---:|---:|---:|
| 1 | control | 6.399 | 4712.0 | 19016 | 0 | 5 |
| 1 | connected | 11.773 | 8570.3 | 23864 | 12416 | 5 |
| 2 | connected | 9.941 | 8389.6 | 23864 | 12416 | 5 |
| 2 | control | 7.859 | 4624.1 | 19016 | 12416 | 5 |
| 3 | control | 6.656 | 4716.7 | 19016 | 18816 | 5 |
| 3 | connected | 11.885 | 9139.2 | 23864 | 23680 | 5 |
| 4 | connected | 10.994 | 8236.9 | 23864 | 8320 | 5 |
| 4 | control | 6.150 | 4727.6 | 19016 | 12416 | 5 |

| Mode | Mean s | Median s | Min s | Max s | Sample SD s |
|---|---:|---:|---:|---:|---:|
| control | 6.766 | 6.527 | 6.150 | 7.859 | 0.757 |
| connected | 11.148 | 11.383 | 9.941 | 11.885 | 0.897 |

These observations show higher elapsed time in this small connected cohort. They do not isolate MCP transport cost from host prompt preparation, provider scheduling, caching or model behavior. Separate host startup/initialization timing and host retry counts are unavailable and remain null. First-message timestamps are buffered CLI observations, not provider execution timestamps. No listed provider-network interruption signal was observed; this does not establish absence of all provider effects.

Every connected trial reported 23,864 input tokens; every control trial reported 19,016, a consistent 4,848-token difference in this cohort. This is consistent with additional host tool/instruction material, but exact host prompt packing is unavailable and the serialized MCP schema alone does not explain or prove that attribution. Cached-input counts varied and are retained per trial.

The connected tool listing measured 4,885 serialized bytes; control had no Conceptualize tools. This is not a measurement of model-visible prompt packing or token causality. No runtime operation occurred, so runtime execution cannot explain this cohort difference.

This environment baseline is separate from adoption/coding benchmarks. Explicit reachability is tested separately. A broken-server condition was not run. Raw events, stderr, registration and timelines remain under evaluations/runs/v04-unused-connection; machine-readable measurements are in evaluations/results/v04-unused-connection.json.

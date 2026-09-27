# Autonomous adoption evidence

Status: evaluation in progress; incomplete cohorts are not final benchmark evidence

Explicit pre/post-change reachability proves that Codex can see and invoke inspect, receive valid responses and persist traces. Historical zero-call runs do not prove intentional rejection; their exact model-visible prompt is unavailable. Reduced schema/descriptions and clearer decision boundaries are implemented. These changes cannot be individually attributed as causes without an ablation.

| Cohort | Task | Mode | Success | Seconds | Observed files | Repeated reads | MCP calls | Context tokens | First operation | Discovery | Useful relationship |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|
| adoption | delivery-contract #1 | control | True | 76.00 | 5 | 0 | 0 | 0 | none | unknown | None |
| adoption | delivery-contract #1 | conceptualize | True | 102.53 | 1 | 0 | 1 | 275 | inspect | before observed relevant source evidence | True |
| adoption | unicode-identity #1 | conceptualize | True | 103.97 | 0 | 0 | 1 | 261 | inspect | after observed relevant source evidence | True |
| adoption | unicode-identity #1 | control | True | 82.46 | 0 | 0 | 0 | 0 | none | unknown | None |
| adoption | batch-contract #1 | control | True | 87.60 | 0 | 0 | 0 | 0 | none | unknown | None |
| adoption | batch-contract #1 | conceptualize | True | 119.55 | 7 | 0 | 0 | 0 | none | unknown | None |
| adoption | retry-interface #1 | conceptualize | True | 113.48 | 0 | 0 | 0 | 0 | none | unknown | None |
| adoption | retry-interface #1 | control | True | 71.14 | 0 | 0 | 0 | 0 | none | unknown | None |
| adoption | record-schema #1 | control | True | 88.67 | 0 | 0 | 0 | 0 | none | unknown | None |
| adoption | record-schema #1 | conceptualize | True | 107.89 | 2 | 0 | 1 | 348 | inspect | before observed relevant source evidence | True |
| adoption | route-normalization #1 | conceptualize | True | 107.48 | 1 | 0 | 0 | 0 | none | unknown | None |
| adoption | route-normalization #1 | control | True | 74.62 | 0 | 0 | 0 | 0 | none | unknown | None |

adoption: 12/12 trials recorded.
control: 6/6 checks passed; mean elapsed 80.08s; MCP invoked in 0 trials.
conceptualize: 6/6 checks passed; mean elapsed 109.15s; MCP invoked in 3 trials.
| receipts | receipts #1 | control | True | 80.73 | 6 | 0 | 0 | 0 | none | unknown | None |
| receipts | receipts #1 | conceptualize | True | 97.64 | 6 | 0 | 1 | 591 | inspect | before observed relevant source evidence | True |
| receipts | receipts #2 | conceptualize | True | 101.59 | 3 | 0 | 1 | 317 | inspect | before observed relevant source evidence | True |
| receipts | receipts #2 | control | True | 85.55 | 6 | 0 | 0 | 0 | none | unknown | None |
| receipts | receipts #3 | control | True | 96.42 | 6 | 0 | 0 | 0 | none | unknown | None |
| receipts | receipts #3 | conceptualize | True | 109.10 | 1 | 0 | 1 | 317 | inspect | before observed relevant source evidence | True |

receipts: 6/6 trials recorded.
control: 3/3 checks passed; mean elapsed 87.57s; MCP invoked in 0 trials.
conceptualize: 3/3 checks passed; mean elapsed 102.78s; MCP invoked in 3 trials.
| negative | typo #1 | control | True | 68.34 | 2 | 0 | 0 | 0 | none | unknown | None |
| negative | typo #1 | conceptualize | True | 85.59 | 2 | 0 | 0 | 0 | none | unknown | None |
| negative | constant #1 | conceptualize | True | 102.67 | 2 | 0 | 0 | 0 | none | unknown | None |

negative: 3/6 trials recorded.
control: 1/1 checks passed; mean elapsed 68.34s; MCP invoked in 0 trials.
conceptualize: 2/2 checks passed; mean elapsed 94.13s; MCP invoked in 0 trials.

## Selective adoption and interpretation

adoption/delivery-contract #1: Delivered required relationship paths, appropriate for cross-file understanding; causal use and speed benefit remain unproven.
Persisted API operation latencies: [266] ms. Host startup, model wait and client transport are not included or inferred from these values.
adoption/unicode-identity #1: Delivered required relationship paths, appropriate for cross-file understanding; causal use and speed benefit remain unproven.
Persisted API operation latencies: [251] ms. Host startup, model wait and client transport are not included or inferred from these values.
adoption/batch-contract #1: No MCP call. A passing manual implementation does not show that skipping was wrong, or that the context runtime affected this trial.
adoption/retry-interface #1: No MCP call. A passing manual implementation does not show that skipping was wrong, or that the context runtime affected this trial.
adoption/record-schema #1: Delivered required relationship paths, appropriate for cross-file understanding; causal use and speed benefit remain unproven.
Persisted API operation latencies: [256] ms. Host startup, model wait and client transport are not included or inferred from these values.
adoption/route-normalization #1: No MCP call. A passing manual implementation does not show that skipping was wrong, or that the context runtime affected this trial.
receipts/receipts #1: Delivered required relationship paths, appropriate for cross-file understanding; causal use and speed benefit remain unproven.
Persisted API operation latencies: [260] ms. Host startup, model wait and client transport are not included or inferred from these values.
receipts/receipts #2: Delivered required relationship paths, appropriate for cross-file understanding; causal use and speed benefit remain unproven.
Persisted API operation latencies: [259] ms. Host startup, model wait and client transport are not included or inferred from these values.
Warehouse relationship discovery: before observed source evidence (surfaced event 8, source evidence event 10, explicit read event None).
receipts/receipts #3: Delivered required relationship paths, appropriate for cross-file understanding; causal use and speed benefit remain unproven.
Persisted API operation latencies: [258] ms. Host startup, model wait and client transport are not included or inferred from these values.
Warehouse relationship discovery: unknown (surfaced event 8, source evidence event None, explicit read event None).
negative/typo #1: Skipped MCP for a clearly local edit, consistent with the intended decision boundary.
negative/constant #1: Skipped MCP for a clearly local edit, consistent with the intended decision boundary.

Files/read counts are supported command-derived lower bounds. Discovery also considers source-bearing rg/grep/Select-String output; plain directory/file listings do not establish a relationship. Useful relationships mean required oracle paths appeared in delivered relationship metadata, not merely in the full trace. Their causal use in changes remains unknown. Positive results do not imply faster execution; unnecessary-files proxies include legitimate tests and alternative implementations. Agent usage, cached tokens, wire bytes, full trace bytes, comparability checks and sandbox/account-limit observations are in ADOPTION-SUITE.json.

Coding agent trials ran serially on a shared development host; local validation and normal background activity were not eliminated. Scheduling, approval/sandbox failures and provider effects remain timing confounders. The eight connected-but-unused trials are separate in BASELINE-OVERHEAD.md. Historical V0.2/V0.3 evidence is unchanged. No model runs inside Conceptualize.

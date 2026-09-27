# Autonomous adoption evidence

Status: evaluation in progress; incomplete cohorts are not final benchmark evidence

Explicit pre/post-change reachability proves that Codex can see and invoke inspect, receive valid responses and persist traces. Historical zero-call runs do not prove intentional rejection; their exact model-visible prompt is unavailable. Reduced schema/descriptions and clearer decision boundaries are implemented. These changes cannot be individually attributed as causes without an ablation.

| Cohort | Task | Mode | Success | Seconds | Observed files | Repeated reads | MCP calls | Context tokens | First operation | Discovery | Useful relationship |
|---|---|---|---|---:|---:|---:|---:|---:|---|---|---|
| adoption | delivery-contract #1 | control | True | 76.00 | 5 | 0 | 0 | 0 | none | unknown | None |
| adoption | delivery-contract #1 | conceptualize | True | 102.53 | 1 | 0 | 1 | 275 | inspect | before observed relevant manual read | True |
| adoption | unicode-identity #1 | conceptualize | True | 103.97 | 0 | 0 | 1 | 261 | inspect | unknown | True |
| adoption | unicode-identity #1 | control | True | 82.46 | 0 | 0 | 0 | 0 | none | unknown | None |

adoption: 4/12 trials recorded.
control: 2/2 checks passed; mean elapsed 79.23s; MCP invoked in 0 trials.
conceptualize: 2/2 checks passed; mean elapsed 103.25s; MCP invoked in 2 trials.

receipts: 0/6 trials recorded.

negative: 0/6 trials recorded.

Files/read counts are supported command-derived lower bounds. Useful relationships mean required oracle paths appeared in delivered relationship metadata, not merely in the full trace. Their causal use in changes remains unknown. Positive results do not imply faster execution; unnecessary-files proxies include legitimate tests and alternative implementations. Agent usage, cached tokens, wire bytes, full trace bytes, comparability checks and sandbox/account-limit observations are in ADOPTION-SUITE.json.

The eight connected-but-unused trials are separate in BASELINE-OVERHEAD.md. Historical V0.2/V0.3 evidence is unchanged. No model runs inside Conceptualize.

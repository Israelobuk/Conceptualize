# Per-pair protocol diagnosis

Unknown elapsed discovery and waiting times remain null. Event steps cannot be translated to seconds. Classification is descriptive and uses a changed-file relevance proxy, not semantic judgment. Shipping usage interruption is blocked/incomplete; previous check results describe repository state, not a completed benchmark failure.

| Cohort | Task | Mode | Outcome | Category | First relevant event | Reads (observed unique) | Searches | MCP | HTTP ms |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| v03-cold-isolated | auth | conceptualize | success | inconclusive | 8 | 3 | 1 | 0 | 0.0 |
| v03-cold-isolated | auth | control | success | inconclusive | 8 | 5 | 1 | 0 | 0.0 |
| v03-cold-isolated | customers | conceptualize | success | inconclusive | 8 | 4 | 2 | 0 | 0.0 |
| v03-cold-isolated | customers | control | success | inconclusive | None | 0 | 0 | 0 | 0.0 |
| v03-cold-isolated | limits | conceptualize | success | inconclusive | 8 | 5 | 1 | 0 | 0.0 |
| v03-cold-isolated | limits | control | success | inconclusive | 8 | 1 | 2 | 0 | 0.0 |
| v03-cold-isolated | pages | conceptualize | success | inconclusive | None | 0 | 1 | 0 | 0.0 |
| v03-cold-isolated | pages | control | success | inconclusive | 8 | 1 | 1 | 0 | 0.0 |
| v03-cold-isolated | receipts | conceptualize | success | inconclusive | 8 | 6 | 1 | 0 | 0.0 |
| v03-cold-isolated | receipts | control | success | inconclusive | 8 | 1 | 1 | 0 | 0.0 |
| v03-cold-isolated | retry | conceptualize | success | inconclusive | 8 | 1 | 1 | 0 | 0.0 |
| v03-cold-isolated | retry | control | success | inconclusive | 8 | 4 | 0 | 0 | 0.0 |
| v03-cold-isolated | shipping | conceptualize | success | inconclusive | 8 | 1 | 2 | 0 | 0.0 |
| v03-cold-isolated | shipping | control | success | inconclusive | 8 | 4 | 1 | 0 | 0.0 |
| v03-cold-isolated | slugs | conceptualize | success | inconclusive | None | 0 | 1 | 0 | 0.0 |
| v03-cold-isolated | slugs | control | success | inconclusive | None | 0 | 0 | 0 | 0.0 |
| v03-cold-isolated | stock | conceptualize | success | inconclusive | 9 | 6 | 1 | 0 | 0.0 |
| v03-cold-isolated | stock | control | success | inconclusive | 8 | 6 | 1 | 0 | 0.0 |
| v03-cold-isolated | times | conceptualize | success | inconclusive | 11 | 4 | 1 | 0 | 0.0 |
| v03-cold-isolated | times | control | success | inconclusive | None | 0 | 1 | 0 | 0.0 |

## Pattern evidence

## Pairwise first-observation comparison

Buffered arrival timestamps and modified-file proxy only; within 1,000 ms is labelled similar. Unknown times remain inconclusive. This is not a causal MCP effect.
- v03-cold-isolated / auth: context discovered earlier; enabled minus control ms: -1124.8819999999978.
- v03-cold-isolated / customers: inconclusive; enabled minus control ms: None.
- v03-cold-isolated / limits: context discovered later; enabled minus control ms: 11621.29.
- v03-cold-isolated / pages: inconclusive; enabled minus control ms: None.
- v03-cold-isolated / receipts: context discovered later; enabled minus control ms: 4490.734.
- v03-cold-isolated / retry: context discovered later; enabled minus control ms: 16960.488999999998.
- v03-cold-isolated / shipping: context discovered later; enabled minus control ms: 7981.529000000002.
- v03-cold-isolated / slugs: inconclusive; enabled minus control ms: None.
- v03-cold-isolated / stock: context discovered later; enabled minus control ms: 5876.532999999999.
- v03-cold-isolated / times: inconclusive; enabled minus control ms: None.
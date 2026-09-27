# Per-pair protocol diagnosis

Unknown elapsed discovery and waiting times remain null. Event steps cannot be translated to seconds. Classification is descriptive and uses a changed-file relevance proxy, not semantic judgment. Shipping usage interruption is blocked/incomplete; previous check results describe repository state, not a completed benchmark failure.

| Cohort | Task | Mode | Outcome | Category | First relevant event | Reads (observed unique) | Searches | MCP | HTTP ms |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| v03-cold-suite | auth | conceptualize | success | inconclusive | 8 | 3 | 2 | 0 | 0.0 |
| v03-cold-suite | auth | control | success | inconclusive | 8 | 3 | 1 | 0 | 0.0 |
| v03-cold-suite | customers | conceptualize | success | inconclusive | 8 | 30 | 0 | 0 | 0.0 |
| v03-cold-suite | customers | control | success | inconclusive | None | 0 | 0 | 0 | 0.0 |
| v03-cold-suite | limits | conceptualize | success | inconclusive | 8 | 5 | 2 | 0 | 0.0 |
| v03-cold-suite | limits | control | success | inconclusive | 8 | 1 | 2 | 0 | 0.0 |
| v03-cold-suite | pages | conceptualize | success | inconclusive | None | 0 | 1 | 0 | 0.0 |
| v03-cold-suite | pages | control | success | inconclusive | 8 | 4 | 1 | 0 | 0.0 |
| v03-cold-suite | receipts | conceptualize | success | inconclusive | 11 | 2 | 0 | 0 | 0.0 |
| v03-cold-suite | receipts | control | success | inconclusive | 8 | 6 | 1 | 0 | 0.0 |
| v03-cold-suite | retry | conceptualize | success | inconclusive | 8 | 5 | 1 | 0 | 0.0 |
| v03-cold-suite | retry | control | success | inconclusive | 8 | 3 | 0 | 0 | 0.0 |
| v03-cold-suite | shipping | conceptualize | success | inconclusive | 8 | 1 | 1 | 0 | 0.0 |
| v03-cold-suite | shipping | control | success | inconclusive | 8 | 4 | 2 | 0 | 0.0 |
| v03-cold-suite | slugs | control | success | inconclusive | 8 | 4 | 0 | 0 | 0.0 |
| v03-cold-suite | stock | control | success | inconclusive | 8 | 5 | 1 | 0 | 0.0 |

## Pattern evidence

## Pairwise first-observation comparison

Buffered arrival timestamps and modified-file proxy only; within 1,000 ms is labelled similar. Unknown times remain inconclusive. This is not a causal MCP effect.
- v03-cold-suite / auth: context discovered later; enabled minus control ms: 9161.323.
- v03-cold-suite / customers: inconclusive; enabled minus control ms: None.
- v03-cold-suite / limits: context discovered later; enabled minus control ms: 7302.834000000003.
- v03-cold-suite / pages: inconclusive; enabled minus control ms: None.
- v03-cold-suite / receipts: context discovered later; enabled minus control ms: 13379.743999999999.
- v03-cold-suite / retry: context discovered later; enabled minus control ms: 6669.325000000001.
- v03-cold-suite / shipping: context discovered later; enabled minus control ms: 10445.203999999998.
- v03-cold-suite / slugs: inconclusive; enabled minus control ms: None.
- v03-cold-suite / stock: inconclusive; enabled minus control ms: None.
- v03-cold-suite / times: inconclusive; enabled minus control ms: None.

Unavailable result: v03-cold-suite / slugs / conceptualize. Preserve runner logs; no outcome inferred.

Unavailable result: v03-cold-suite / stock / conceptualize. Preserve runner logs; no outcome inferred.

Unavailable result: v03-cold-suite / times / conceptualize, control. Preserve runner logs; no outcome inferred.
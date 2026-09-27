# Per-pair protocol diagnosis

Unknown elapsed discovery and waiting times remain null. Event steps cannot be translated to seconds. Classification is descriptive and uses a changed-file relevance proxy, not semantic judgment. Shipping usage interruption is blocked/incomplete; previous check results describe repository state, not a completed benchmark failure.

| Cohort | Task | Mode | Outcome | Category | First relevant event | Reads (observed unique) | Searches | MCP | HTTP ms |
|---|---|---|---|---|---:|---:|---:|---:|---:|
| runtime-suite-v1 | auth | conceptualize | success | repeated/redundant exploration | 8 | 3 | 2 | 3 | 1797.9 |
| runtime-suite-v1 | auth | control | success | inconclusive | 8 | 5 | 1 | 0 | 0.0 |
| runtime-suite-v1 | customers | conceptualize | success | repeated/redundant exploration | 8 | 4 | 1 | 3 | 1685.3 |
| runtime-suite-v1 | customers | control | success | inconclusive | 8 | 4 | 1 | 0 | 0.0 |
| runtime-suite-v1 | limits | conceptualize | success | repeated/redundant exploration | 8 | 4 | 1 | 2 | 1168.6 |
| runtime-suite-v1 | limits | control | success | inconclusive | 8 | 5 | 2 | 0 | 0.0 |
| runtime-suite-v1 | pages | conceptualize | success | inconclusive | 8 | 4 | 1 | 1 | 660.8 |
| runtime-suite-v1 | pages | control | success | inconclusive | 8 | 4 | 0 | 0 | 0.0 |
| runtime-suite-v1 | receipts | conceptualize | success | excessive context | 6 | 0 | 0 | 3 | 1717.0 |
| runtime-suite-v1 | receipts | control | success | inconclusive | 8 | 6 | 1 | 0 | 0.0 |
| runtime-suite-v1 | retry | conceptualize | success | inconclusive | 11 | 5 | 2 | 1 | — |
| runtime-suite-v1 | retry | control | success | inconclusive | 8 | 4 | 0 | 0 | 0.0 |
| runtime-suite-v1 | shipping | conceptualize | incomplete | inconclusive | None | 0 | 0 | 0 | 0.0 |
| runtime-suite-v1 | shipping | control | incomplete | inconclusive | None | 0 | 0 | 0 | 0.0 |
| runtime-suite-v1 | slugs | conceptualize | incomplete | inconclusive | None | 0 | 0 | 0 | 0.0 |
| runtime-suite-v1 | slugs | control | incomplete | inconclusive | None | 0 | 0 | 0 | 0.0 |
| runtime-suite-v1 | stock | conceptualize | success | repeated/redundant exploration | 8 | 3 | 1 | 3 | 1960.9 |
| runtime-suite-v1 | stock | control | success | inconclusive | 22 | 1 | 0 | 0 | 0.0 |
| runtime-suite-v1 | times | conceptualize | incomplete | inconclusive | None | 0 | 0 | 0 | 0.0 |
| runtime-suite-v1 | times | control | incomplete | inconclusive | None | 5 | 1 | 0 | 0.0 |
| runtime-suite-recovery | shipping | conceptualize | blocked_incomplete | inconclusive | None | 0 | 0 | 3 | 850.4 |
| runtime-suite-recovery | shipping | control | success | inconclusive | 8 | 6 | 1 | 0 | 0.0 |
| runtime-suite-recovery | slugs | conceptualize | success | context discovered earlier | 8 | 4 | 0 | 3 | 1111.6 |
| runtime-suite-recovery | slugs | control | success | inconclusive | 8 | 4 | 1 | 0 | 0.0 |
| runtime-suite-recovery | times | conceptualize | success | inconclusive | 13 | 1 | 0 | 2 | 568.7 |
| runtime-suite-recovery | times | control | success | inconclusive | None | 1 | 1 | 0 | 0.0 |

## Pattern evidence

## Pairwise first-observation comparison

Buffered arrival timestamps and modified-file proxy only; within 1,000 ms is labelled similar. Unknown times remain inconclusive. This is not a causal MCP effect.
- runtime-suite-recovery / shipping: inconclusive; enabled minus control ms: None.
- runtime-suite-recovery / slugs: inconclusive; enabled minus control ms: None.
- runtime-suite-recovery / times: inconclusive; enabled minus control ms: None.
- runtime-suite-v1 / auth: inconclusive; enabled minus control ms: None.
- runtime-suite-v1 / customers: inconclusive; enabled minus control ms: None.
- runtime-suite-v1 / limits: inconclusive; enabled minus control ms: None.
- runtime-suite-v1 / pages: inconclusive; enabled minus control ms: None.
- runtime-suite-v1 / receipts: inconclusive; enabled minus control ms: None.
- runtime-suite-v1 / retry: inconclusive; enabled minus control ms: None.
- runtime-suite-v1 / shipping: inconclusive; enabled minus control ms: None.
- runtime-suite-v1 / slugs: inconclusive; enabled minus control ms: None.
- runtime-suite-v1 / stock: inconclusive; enabled minus control ms: None.
- runtime-suite-v1 / times: inconclusive; enabled minus control ms: None.

### runtime-suite-v1 / auth / conceptualize

```json
[
  {
    "pattern": "pack_after_host_reads",
    "step": 15,
    "evidence": {
      "files": [
        "shop/refunds.py",
        "shop/auth.py",
        "test_shop.py"
      ]
    },
    "interpretation": "Host reads are not MCP delivery history; runtime cannot deduplicate undisclosed host reads."
  }
]
```

### runtime-suite-v1 / customers / conceptualize

```json
[
  {
    "pattern": "pack_after_host_reads",
    "step": 15,
    "evidence": {
      "files": [
        "shop/customer_keys.py",
        "shop/segment_writer.py",
        "shop/customer_store.py",
        "test_shop.py"
      ]
    },
    "interpretation": "Host reads are not MCP delivery history; runtime cannot deduplicate undisclosed host reads."
  }
]
```

### runtime-suite-v1 / limits / conceptualize

```json
[
  {
    "pattern": "pack_after_host_reads",
    "step": 12,
    "evidence": {
      "files": [
        "shop/settings.py",
        "shop/batch_gateway.py",
        "shop/inventory.py"
      ]
    },
    "interpretation": "Host reads are not MCP delivery history; runtime cannot deduplicate undisclosed host reads."
  }
]
```

### runtime-suite-v1 / stock / conceptualize

```json
[
  {
    "pattern": "pack_after_host_reads",
    "step": 17,
    "evidence": {
      "files": [
        "shop/stock.py",
        "shop/reconciliation.py",
        "test_shop.py"
      ]
    },
    "interpretation": "Host reads are not MCP delivery history; runtime cannot deduplicate undisclosed host reads."
  }
]
```
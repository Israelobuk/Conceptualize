# Receipt migration demonstration

A request that starts at checkout also changes a shared receipt type and an audit consumer: `shop/warehouse.py` imports `Receipt` and stores dollar-denominated summaries. Migrating the contract without updating this consumer breaks order recording.

The task prompt asked for integer-cent receipts and preserved audit semantics. It did **not** mention Conceptualize or identify the warehouse file.

## Actual paired evidence

Both runs used the same committed baseline (`30051f824885d390d1a6776bf1f8ece5ab76d66d`), identical prompt hash, bundled Codex version, and `gpt-6-sol`. The corrected configuration disabled unrelated MCP servers in both modes and enabled only Conceptualize for the enabled run.

| Observation | Control | Conceptualize |
| --- | ---: | ---: |
| Independent checks plus repository tests | Passed | Passed |
| Modified files | 5 | 5 |
| Recorded elapsed seconds | 93.251 | 121.872 |
| Completed shell command executions | 6 | 5 |
| Conceptualize operations | 0 | 3 |
| Compiled context tokens returned | 0 | 1,012 |
| Agent-reported total input tokens | 188,077 | 280,516 |
| Of those, cached input tokens | 155,776 | 238,208 |
| Agent-reported output tokens | 1,296 | 1,909 |

The enabled agent autonomously called:

1. `conceptualize_map`: establish source structure.
2. `conceptualize_dependencies` with target `shop/contracts.py`: discover receipt consumers, including warehouse and checkout.
3. `conceptualize_pack`: obtain bounded working source context and its selection evidence.

It then updated checkout, the receipt contract, ordering, the warehouse consumer, and associated tests. Both runs modified the same five files and passed independently maintained behavior checks. Raw events show the tool calls and subsequent edits; persisted API traces show the imported-symbol relationship to `Receipt` and the selected warehouse source.

This demonstrates autonomous adoption and useful cross-file discovery. It **does not demonstrate improved speed or token efficiency**: the enabled run was slower and used more agent-reported input tokens in this single pair. One fewer shell command does not establish fewer repository reads. Repeat tasks and run order before making performance claims.

## Review the evidence

- `results/receipts-comparison.json`: validated paired measurements.
- `results/receipts-traversal.json`: actual graph traversal and selection evidence.
- `runs/receipts-control-connected/`: full control events, independent test output, diff and result.
- `runs/receipts-conceptualize-final/`: full enabled events, independent test output, diff, traces and result.

The raw run directories are intentionally ignored by Git and indexing, but remain on disk. Unknown file-read counts, unnecessary reads and corrective iterations are null. Compiled context token counts exclude structured MCP metadata overhead. Recorded agent usage includes repeated cached input.

## Inspect in the dashboard

The current local dashboard at `http://127.0.0.1:3019/` is configured for the actual demonstration project. Select the pack activity row, click **Open**, and expand **Context selection evidence**. The existing layout and one-screen overview are preserved.

Project ID: `23458fc9-3623-4d7a-b4ba-19c148ac75a0`.

Recorded agent trace IDs:

- Pack: `2b8fc646-2cbb-4019-a84e-97b921047900`.
- Dependencies: `9a3a218a-aa59-496b-9ace-d4e862d0aa78`.
- Map: `9d802f80-b2fe-45b7-8b01-3542fb090002`.

The live demonstration API uses an isolated SQLite QA database on port 8029. PostgreSQL/Redis remain the normal deployment configuration. No source or outcome was hardcoded into a tool response; the ordinary index/runtime/API produced these traces, and the coding agent produced the changes.

## Preserved unsuccessful attempts

Earlier runs are retained under `runs/`:

- `receipts-control` and `receipts-conceptualize`: both passed, but the initial configuration bypass caused zero MCP adoption; this pair does not prove integration.
- `receipts-conceptualize-verified`: configuration startup failed while disabling injected transports.
- `receipts-conceptualize-connected`: autonomous map/dependencies/pack calls succeeded, but Windows default text decoding interrupted result export. Raw events and source edits remain. UTF-8 regression coverage now protects recording, and the final run above completed normally.

These attempts were not merged into successful measurements or silently replaced.

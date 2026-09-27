# MCP surface measurements

Six existing tools are preserved. Decision-boundary descriptions identify when inspection is useful and when isolated edits should skip it. Full selection provenance remains in API/dashboard traces; MCP returns bounded context, relationship previews, previous-context references and every stale context ID.

| Measurement | Before | After |
|---|---:|---:|
| Description characters | 2,904 | 1,472 |
| Input/output schema bytes | 17,078 | 2,810 |
| Serialized tool listing bytes | 20,349 | 4,885 |
| Initialization bytes | 834 | 826 |

These are serialized JSON measurements, not model token savings. Optional output schemas were removed; inputs and validated runtime responses remain compatible. The capability resource reports indexed file/symbol counts only when requested. No automatic source or map is injected.

Explicit pre-change and post-change Codex reachability tests successfully invoked inspect and persisted their traces. The post-change agent identified checkout and warehouse as direct consumers. This proves reachability in that test, not autonomous adoption or product benefit. Raw before/after surfaces are preserved under evaluations/results. New adoption and unused-connection experiments remain required before claiming benefit.

The post-change actual inspect payload was 2,210 bytes, compared with a 13,460-byte full API result and 14,146-byte full trace. Its host event result was 4,614 bytes: JSON source appears in both text fallback and structured content for compatibility. Whether the host exposes both copies to the model is unavailable; this is not counted as proven token duplication. Full candidate scores, reasons, timings and provenance remain in the trace.

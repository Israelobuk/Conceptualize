# V0.9 context-utilization fix — human audit

Frozen fixture: `de91afc78218b084a6e569ba1e611d952490861dea9864fe720f55bb18c42370`. Frozen evaluator prompt: `080d5dd01dc138bdb5907de8ff144ea566fb1df39fbcf9f9a4cb15048d157522`.
Full passes: **3/3**. Retrieval / Working Context / answer coverage: **100.0% / 100.0% / 100.0%**.
Context Utilization Rate: **100.0%**. Critical Context Utilization Rate: **100.0%**.

## Run 1

Pass: **True**; calls: 1; context: 3376 local tokens; provider input/cached/output: 96393/72960/692; latency: approximately 25313.3 ms.

| Proposition | Retrieval | Working Context | Final answer | Answer evidence |
|---|---|---|---|---|
| ARCH_01 | present | present | present | The current client is one browser PWA for desktop and mobile, using the existing HTTPS JSON API. |
| ARCH_02 | present | present | present | These boundaries remain separate so either implementation can change without rewriting the screens. |
| DEC_01 | present | present | present | structured inspection records are in IndexedDB, while an attachment adapter prefers the File System Access API when available and falls back to IndexedDB blobs. |
| DEC_02 | present | present | present | The shared adapter interface is drafted |
| CON_01 | present | present | present | Drafts and photos stay local until the API confirms the authenticated upload of that specific attachment. |
| OLD_01 | present | present | present | The earlier **native desktop, localStorage-only, filesystem-only, WebSocket** proposal is superseded. |
| STATE_01 | present | present | present | The shared adapter interface is drafted, but its production backends and common contract tests are incomplete. |
| NEXT_01 | present | present | present | After those tests pass, connect the adapter to SyncEngine |

ARCH_02 classification: `none; present through retrieval, compilation, and answer`.

## Run 2

Pass: **True**; calls: 1; context: 3307 local tokens; provider input/cached/output: 141954/119808/587; latency: approximately 27358.54 ms.

| Proposition | Retrieval | Working Context | Final answer | Answer evidence |
|---|---|---|---|---|
| ARCH_01 | present | present | present | One browser based PWA serves desktop and mobile through the existing HTTPS JSON API. |
| ARCH_02 | present | present | present | `LocalStore` persists inspection records in IndexedDB and owns a separate attachment adapter. |
| DEC_01 | present | present | present | That adapter prefers the File System Access API when available and falls back to IndexedDB blobs |
| DEC_02 | present | present | present | both backends must provide the same write, read, and delete behavior. |
| CON_01 | present | present | present | Drafts and photos stay on the device until the API confirms the authenticated upload of that specific item. |
| OLD_01 | present | present | present | `localStorage` drafts, filesystem only attachments, and WebSocket sync is historical. It is not the current plan. |
| STATE_01 | present | present | present | Attachment bytes still use a temporary test path. The adapter contract is drafted, but its two production backends and shared tests are unfinished. |
| NEXT_01 | present | present | present | Next, implement backend selection and the common contract; test reload persistence, permission fallback, failed uploads, and cleanup only after acknowledgement; then connect the adapter to `SyncEngine`. |

ARCH_02 classification: `none; present through retrieval, compilation, and answer`.

## Run 3

Pass: **True**; calls: 1; context: 3307 local tokens; provider input/cached/output: 141897/119808/567; latency: approximately 24820.57 ms.

| Proposition | Retrieval | Working Context | Final answer | Answer evidence |
|---|---|---|---|---|
| ARCH_01 | present | present | present | One browser-based PWA serves desktop and mobile through the existing HTTPS JSON API. |
| ARCH_02 | present | present | present | through a replaceable adapter: File System Access API where supported, with IndexedDB blobs as the fallback. `SyncEngine` is a separate transfer layer. |
| DEC_01 | present | present | present | `LocalStore` keeps structured inspection drafts in IndexedDB and will store attachments through a replaceable adapter: File System Access API where supported, with IndexedDB blobs as the fallback. |
| DEC_02 | present | present | present | Finish both attachment backends and their shared write/read/delete tests |
| CON_01 | present | present | present | remove each local attachment only after its own upload is acknowledged. |
| OLD_01 | present | present | present | localStorage is no longer the storage plan. |
| STATE_01 | present | present | present | IndexedDB record persistence, and record metadata sync—including replay and conflict handling—are implemented. Attachment bytes still use a temporary test path. |
| NEXT_01 | present | present | present | Finish both attachment backends and their shared write/read/delete tests, covering reload persistence, permission fallback, and retention after failed uploads. Then connect the adapter to `SyncEngine` |

ARCH_02 classification: `none; present through retrieval, compilation, and answer`.

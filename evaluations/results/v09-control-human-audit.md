# Human audit — V0.9 control

Blind semantic evaluator decisions are shown verbatim. This artifact does not regrade answers.

## Run 1 (answer_001)

Pass: **False**; critical coverage: 87.5%; total coverage: 87.5%.

| Proposition | Ground truth | Evaluator status | Answer evidence |
|---|---|---|---|
| ARCH_01 | The current client is a browser PWA for desktop and mobile, using the existing HTTPS JSON API. | present | current client is a browser PWA for desktop and mobile, using the existing HTTPS JSON API |
| ARCH_02 | Local persistence and synchronization are separate layers that can be replaced independently. | absent | **LocalStore** owns device persistence |
| DEC_01 | Inspection records use IndexedDB; attachments prefer File System Access when available and fall back to IndexedDB blobs. | present | inspection records are in IndexedDB, while an attachment adapter prefers filesystem storage when supported and permitted, with IndexedDB blobs as the fallback |
| DEC_02 | Both attachment storage backends share the same read, write, and delete interface. | present | the shared write/read/delete contract is drafted |
| CON_01 | Keep each local attachment until its own authenticated upload is acknowledged by the server. | present | Drafts and photos must remain local until the API acknowledges their *own* authenticated upload. |
| OLD_01 | The localStorage-only production storage decision is superseded and is not current. | present | The earlier **localStorage-only** choice is superseded. |
| STATE_01 | Record persistence and metadata synchronization are integrated, but production attachment backends, shared contract tests, and end-to-end attachment transfer remain unfinished. | present | The PWA shell, record form, IndexedDB draft recovery, and record metadata sync are implemented. |
| NEXT_01 | Implement backend selection and shared adapter behavior, test reload persistence, permission fallback, and acknowledgement-safe cleanup, then integrate the adapter with SyncEngine. | present | Once those pass, connect the adapter to SyncEngine. |

## Run 2 (answer_002)

Pass: **False**; critical coverage: 87.5%; total coverage: 87.5%.

| Proposition | Ground truth | Evaluator status | Answer evidence |
|---|---|---|---|
| ARCH_01 | The current client is a browser PWA for desktop and mobile, using the existing HTTPS JSON API. | present | one browser PWA for desktop and mobile, using the existing HTTPS JSON API |
| ARCH_02 | Local persistence and synchronization are separate layers that can be replaced independently. | absent | **LocalStore** owns device persistence |
| DEC_01 | Inspection records use IndexedDB; attachments prefer File System Access when available and fall back to IndexedDB blobs. | present | inspection records are in IndexedDB, while an attachment adapter prefers filesystem storage when available and permitted and falls back to IndexedDB blobs |
| DEC_02 | Both attachment storage backends share the same read, write, and delete interface. | present | Both attachment backends must provide the same write, read, and delete contract. |
| CON_01 | Keep each local attachment until its own authenticated upload is acknowledged by the server. | present | Drafts and photos must remain local until the API acknowledges their **own authenticated upload**. |
| OLD_01 | The localStorage-only production storage decision is superseded and is not current. | present | The earlier **localStorage-only** proposal is superseded. |
| STATE_01 | Record persistence and metadata synchronization are integrated, but production attachment backends, shared contract tests, and end-to-end attachment transfer remain unfinished. | present | IndexedDB draft recovery, and record metadata sync are integrated. Metadata sync uses a stable client UUID |
| NEXT_01 | Implement backend selection and shared adapter behavior, test reload persistence, permission fallback, and acknowledgement-safe cleanup, then integrate the adapter with SyncEngine. | present | Once those pass, connect the adapter to SyncEngine. |

## Run 3 (answer_003)

Pass: **False**; critical coverage: 87.5%; total coverage: 87.5%.

| Proposition | Ground truth | Evaluator status | Answer evidence |
|---|---|---|---|
| ARCH_01 | The current client is a browser PWA for desktop and mobile, using the existing HTTPS JSON API. | present | current client is a browser PWA for desktop and mobile, using the existing HTTPS JSON API |
| ARCH_02 | Local persistence and synchronization are separate layers that can be replaced independently. | absent | **LocalStore** owns local persistence |
| DEC_01 | Inspection records use IndexedDB; attachments prefer File System Access when available and fall back to IndexedDB blobs. | present | inspection records are in IndexedDB, while an attachment adapter prefers filesystem storage when supported and permitted, with IndexedDB blobs as the fallback |
| DEC_02 | Both attachment storage backends share the same read, write, and delete interface. | present | the common write/read/delete contract, then run the same tests against both backends |
| CON_01 | Keep each local attachment until its own authenticated upload is acknowledged by the server. | present | Drafts and photos must remain local until the API acknowledges their **own authenticated upload** |
| OLD_01 | The localStorage-only production storage decision is superseded and is not current. | present | The early **localStorage-only** choice is superseded |
| STATE_01 | Record persistence and metadata synchronization are integrated, but production attachment backends, shared contract tests, and end-to-end attachment transfer remain unfinished. | present | The attachment interface is drafted, but its production backends, shared contract tests, and end-to-end transfer are unfinished. |
| NEXT_01 | Implement backend selection and shared adapter behavior, test reload persistence, permission fallback, and acknowledgement-safe cleanup, then integrate the adapter with SyncEngine. | present | Cover permission denial, reload persistence, failed writes, and cleanup only after per-attachment acknowledgement. Once those pass, connect the adapter to SyncEngine. |

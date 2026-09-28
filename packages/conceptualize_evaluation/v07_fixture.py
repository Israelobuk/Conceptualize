"""Build and freeze the single realistic V0.7 economics conversation fixture."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from conceptualize_runtime.adapters import ConversationAdapter
from conceptualize_runtime.runtime import token_count

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "evaluations" / "v05-conversation-problem.json"
OUT = ROOT / "evaluations" / "v07"
VERSION = "v0.7-context-economics-atlas-9"
QUESTION = (
    "Based on everything we've decided so far, summarize the current implementation plan. "
    "Include the current architecture, the constraints we must preserve, which earlier "
    "decisions are no longer current, and the next implementation step."
)

# Additional engineering discussion is deliberately specific and useful: API and client
# contracts, failure handling, release scope, and implementation reviews. Some messages
# repeat prior decisions naturally, while several concern unrelated release work.
DISCUSSION = [
    ("user", "The first LocalStore prototype is now running in the browser shell. It writes an inspection record with a client-generated identifier and a small sync state, then restores that draft after a reload while offline. Keep that work behind the LocalStore boundary so the page components never reach into IndexedDB directly. We still need to settle attachments separately because binary data has different browser capabilities and failure modes than the text fields. Please treat the prototype as progress on the record path, not as evidence that the attachment path is complete."),
    ("assistant", "I will keep the record store and attachment store behind the same client boundary while leaving their implementations distinct. The current prototype covers structured inspection records in IndexedDB and survives reloads without a network connection. It does not yet provide the attachment behavior. I will keep the next implementation plan focused on completing that adapter contract and its fallback tests before wiring those calls into synchronization."),
    ("user", "We reviewed the native-client proposal with the field team. They need the same inspection workflow on managed laptops and personal phones, and installing a signed desktop build on every device would add an avoidable deployment step. Keep the browser-based PWA as the client and preserve the existing HTTPS API. Local persistence and synchronization still need replaceable boundaries so we can change either implementation without rewriting the screens. This is a direction change from the first kickoff note, not a second supported client target."),
    ("assistant", "The current client is the browser PWA on desktop and mobile, using the existing HTTPS JSON API. LocalStore and SyncEngine remain separate replaceable boundaries. The earlier native desktop idea is no longer a release direction. I will keep references to that initial proposal in the history only as a superseded decision, not as an active deployment option."),
    ("user", "The record schema review confirmed that an inspection has a stable client UUID before its first upload. The API uses that key to treat retries of the same create request as one inspection, including after a connection drops before the response reaches the browser. The server assigns its own identifier as well, and the local record keeps both values with the last acknowledged version. We should not use timestamps as identity because two offline devices can create records at similar times."),
    ("assistant", "The client UUID is the idempotency key and exists before upload. The server ID and acknowledged version are stored alongside it after a response. A retry with the same client UUID must not create a second inspection. Timestamps remain descriptive metadata rather than identity. I will carry this contract into the API integration tests and keep the browser retry path safe when the response is lost."),
    ("user", "One of the conflict tests exposed an important recovery case. A crew member can edit an inspection on a tablet while a supervisor updates the server copy from a second device. The server should compare the version the client last read and return a conflict when it is stale; it must not silently replace the supervisor's newer data. The tablet's draft and photos remain on the device so the person can review and resolve the conflict. A conflict is a user-visible state, not a transient network failure to retry repeatedly."),
    ("assistant", "The version supplied with an update is checked against the server version. A stale update receives a conflict response and keeps the local draft available for a person to resolve. It is not automatically retried as though connectivity were down. The client UUID still provides idempotency for safe repeats of a request, while version checks prevent an old edit from overwriting newer server data."),
    ("user", "Please keep the offline guarantee explicit in both the data flow and the acceptance tests. Photos and draft fields stay local until an authenticated upload is confirmed by the API. A timeout, browser close, expired session, or validation response does not count as confirmation. If a request fails after the server may have received bytes, the same client identifiers make a retry safe, but the browser still retains its source copy until it receives a valid success response. We need to test interruption at the boundary before deleting or marking any local attachment as uploaded."),
    ("assistant", "The local source remains until the server returns a successful authenticated-upload response. Network uncertainty and validation failures leave the record and attachments available. Only acknowledged success advances the sync state. The stable client UUID protects a retry from duplicating an inspection, but it does not justify removing the local source before acknowledgement."),
    ("user", "We compared browser attachment APIs on the devices in the pilot. The File System Access API is convenient on supported desktop browsers, but it is not available everywhere and permission can be denied even where the API exists. Use filesystem-backed storage as the preferred option when available and authorized; fall back to an IndexedDB blob for the same attachment when it is not. The calling code should depend on one read, write, and delete contract, not branch on browser detection throughout the sync flow."),
    ("assistant", "The filesystem path is an optional preferred backend, not a universal requirement. The adapter selects it only when the capability and permission checks succeed, and otherwise uses an IndexedDB blob. Both implementations expose the same read, write, and delete behavior to LocalStore. This updates the earlier filesystem-only wording while keeping the attachment storage behind a small replaceable contract."),
    ("user", "For the fallback, please cover more than initial creation. A blob written to IndexedDB must be readable after a reload, must remain linked to its inspection UUID, and must be removed only after the upload acknowledgement. If the preferred filesystem write fails partway through, the adapter should return a clear error or use the fallback according to the agreed policy; it must not report success with a missing attachment. The contract tests should run against both backends with the same cases so behavior stays aligned."),
    ("assistant", "The contract suite will exercise write/read/delete and association with the stable inspection ID for both implementations. It will include reload persistence and a failed preferred-backend path. A missing or partial attachment cannot be reported as a successful write. Local cleanup remains tied to confirmed upload acknowledgement rather than the start of a request."),
    ("user", "The sync worker will run when the app opens, after the user pulls to refresh, and after an edit while the device is online. It should resume an interrupted transfer from the last acknowledged state. We do not need a background timer for the first release, and we should not depend on browser push or websocket delivery to discover work. These triggers are easier for field staff to understand and easier to validate while offline."),
    ("assistant", "The first release uses explicit client-triggered sync on app launch, pull to refresh, and an online local edit. It resumes interrupted work and does not require WebSocket push or periodic background sync. Those excluded mechanisms should remain out of the implementation plan unless the scope is deliberately revisited later."),
    ("user", "Retry behavior should distinguish transport trouble from a response that requires human correction. Temporary connection loss and server-unavailable responses use exponential backoff with jitter, with a ceiling so a device does not retry forever at a high rate. A validation error is shown with enough detail to correct the inspection and is not retried automatically. A version conflict also pauses for user resolution. Please avoid a single retry flag that treats all non-success responses alike."),
    ("assistant", "The retry policy is limited to transient network and service failures, with exponential backoff and jitter. Validation errors require correction and version conflicts require resolution, so neither loops through automatic retries. The sync state should retain which class of failure occurred so the UI can show an actionable message."),
    ("user", "We are keeping inspection text fields plain text for this release. Rich text, embedded markup, and an editor toolbar would make offline validation and API versioning harder without helping the field workflow. The server can still validate lengths and required fields. Error messages should point to the affected field and remain readable when the user is offline, rather than relying only on an icon or a colored badge."),
    ("assistant", "V1 text fields are plain text with length and required-field validation. There is no rich-text editor in scope. Offline and sync-error status must have readable text and screen-reader announcements; color or icon alone is not enough."),
    ("user", "The accessibility pass found that the sync spinner announces every retry, which becomes noisy in a poor-coverage area. Announce the transition into a useful state, such as waiting to reconnect or requiring a correction, and announce completion after the server acknowledges it. The retry counter is implementation telemetry, not user-facing content. This does not change the durable offline behavior or the requirement that drafts remain accessible to assistive technology."),
    ("assistant", "I will announce meaningful sync-state changes instead of each timer tick. The accessible status will distinguish queued offline work, a correctable validation failure, a conflict needing review, and acknowledged completion. The local draft remains available throughout each state."),
    ("user", "The backend has settled on PostgreSQL for inspection rows and their version state. We do not need a second storage engine in this milestone. The request body carries the client UUID and the version the device last saw; the response includes the server ID and current version. Idempotency handles replay of the same logical create, while optimistic version checking handles a genuinely stale edit. Those are related but separate guarantees."),
    ("assistant", "PostgreSQL remains the API's inspection store. The client UUID provides idempotency for replay, and the version check rejects stale updates with a conflict. The response records the server ID and acknowledged version locally. Keeping those guarantees distinct makes the failure cases and tests clearer."),
    ("user", "I found an old planning note that says to store everything in localStorage because it is easy to inspect. Please do not revive it in the implementation summary. Structured drafts need IndexedDB, and attachments use the adapter with filesystem support where available and an IndexedDB blob fallback. We should preserve the history of how the choice changed, but the active architecture should say only what we currently intend to build."),
    ("assistant", "Understood. The localStorage proposal is explicitly superseded. The current structured record store is IndexedDB, and attachment files use the capability-aware adapter with an IndexedDB blob fallback. The earlier note stays in the project history so the decision remains auditable, but it is not current guidance."),
    ("user", "The API contract tests now cover create replay with one UUID, reject a stale version, and preserve the existing server row. The client tests cover reopening a draft after reload and displaying a conflict without clearing the local copy. The missing area is attachment contract coverage across the two backends, especially fallback after permission denial and cleanup only after an acknowledged upload. Please keep that gap visible in the status report."),
    ("assistant", "The UUID replay, stale-version conflict, draft recovery, and conflict display checks are passing in the current branch. Attachment backend parity and acknowledgement-gated cleanup remain unfinished. I will not describe the attachment path as complete until its fallback and persistence tests pass."),
    ("user", "The UI review asked for an analytics dashboard and a push-notification panel so managers can watch uploads. That is useful later, but it is not necessary for a reliable offline inspection workflow and would add new permissions and services. Keep manager analytics, push notifications, and background periodic sync outside this release. We should finish durable local capture and explicit recovery before revisiting operational reporting."),
    ("assistant", "Those manager-facing additions are outside the current release scope: no analytics dashboard, push notification service, or periodic background sync. The implementation remains focused on local inspection, foreground synchronization, and user-visible recovery."),
    ("user", "Please retain the server API name and the LocalStore and SyncEngine boundary names. A branch proposal suggested renaming the API to match the new PWA package, but that would create churn for the existing deployment and clients. The browser client can change independently while continuing to use the established HTTPS JSON endpoints. Names in the code should distinguish the local data boundary from the transfer process."),
    ("assistant", "The established HTTPS API name and endpoints remain unchanged. LocalStore denotes client-side persistence, and SyncEngine denotes transfer and retry orchestration. The PWA implementation can evolve behind those boundaries without renaming the deployed service."),
    ("user", "For database conflict resolution, do not automatically merge two free-text inspection narratives. If the server version has moved, preserve the device's draft and show the server version for comparison. We can revisit field-level merge rules if the product defines them, but this release should not guess which note is authoritative. Stable identifiers let us associate both versions without silently replacing either one."),
    ("assistant", "A conflict pauses automatic upload and retains the local draft for explicit review. The server's newer record is not overwritten, and the client does not invent a merge for free-text fields. No automatic conflict merge is part of the current contract."),
    ("user", "The mobile browser can suspend a tab while offline work is queued, so the retry loop must not assume a continuously running page. When the app returns, it reads the durable sync state and resumes from the last acknowledged record or attachment. The initial architecture still avoids background periodic work; resuming on app launch is sufficient. We should test process interruption as well as an ordinary request timeout."),
    ("assistant", "Queued work and its acknowledged progress must survive page suspension and reload. The app resumes when opened and uses the stored sync state. This is foreground recovery, not a request for a background timer or push mechanism."),
    ("user", "The field labels should be translatable later, but translation support itself is not a storage or sync dependency for V1. Keep values in plain text and keep validation rules on the shared API contract. We can localize labels without changing what is persisted. This is a minor interface note and should not distract from the unresolved attachment adapter work."),
    ("assistant", "Localization of labels can be handled at the UI layer later. Persisted inspection text remains plain text, and this does not alter the current synchronization or adapter plan."),
    ("user", "I pasted the original kickoff note below so the review can see why the plan changed: ‘Let's ship a native desktop client and save every draft in localStorage. We can use filesystem-only attachments and a websocket to push sync updates.’ That paragraph is historical context only. The later reviews explicitly changed the client, record store, attachment fallback, and synchronization triggers. Please do not copy the quoted proposal into the current plan."),
    ("assistant", "The quotation is the original proposal, not an active requirement. The browser PWA, IndexedDB records, capability-aware attachment fallback, and client-triggered HTTPS synchronization are the current direction. I will list the older options only under superseded decisions."),
    ("user", "Current delivery status as of this week's integration review: the PWA shell and record form are in place. LocalStore can persist and restore the structured record in IndexedDB. SyncEngine submits record metadata with the client UUID, handles idempotent replay, stores the server version, and pauses on conflict or validation correction. Attachment bytes are not yet connected end to end; the adapter interface has been drafted, but the filesystem/IndexedDB implementations and shared contract tests are still open."),
    ("assistant", "That is the current implementation state: record persistence and metadata synchronization are implemented, including replay and conflict behavior. Attachment integration is not complete. The next work should finish both adapter backends and prove the shared contract before the sync path begins deleting an acknowledged local source."),
    ("user", "The next pull request should have a narrow acceptance boundary. First, implement adapter selection and the common read/write/delete methods. Second, run the same contract cases against the filesystem backend when supported and the IndexedDB blob backend otherwise. Third, verify that a denied permission or a failed upload leaves the source available. Only after that should SyncEngine call the adapter for attachment transfer. Please do not combine this with manager analytics or a new server endpoint."),
    ("assistant", "Agreed. The next step is the LocalStore attachment adapter contract and its filesystem/IndexedDB fallback tests, including persistence and acknowledgement-gated cleanup. Wiring the adapter into SyncEngine follows after those tests pass. No analytics, new endpoint, or other product work is needed for that step."),
    ("user", "A release coordinator asked if we can promise a North-region pilot date in the same update. Training owns that schedule and has not confirmed device availability. Keep the date out of the technical plan and do not infer a launch commitment from the implementation work. The project conversation contains release and design notes alongside architecture decisions, so the summary should stay focused on the current engineering plan."),
    ("assistant", "The pilot date is not part of the technical implementation plan and remains unconfirmed by its owner. I will keep release scheduling separate from the architecture and next engineering step."),
    ("user", "One last review of the local retention rule: even when the API returns a validation error, authentication expires, or the network drops after the request is sent, the attachment remains stored. We only mark that particular upload complete after the API has acknowledged it. An unrelated successful record request must not cause all queued photos to be deleted. The user can retry a correctable failure after updating the record, while a version conflict waits for review."),
    ("assistant", "Retention and acknowledgement are tracked per uploaded item. A successful response for one record does not authorize cleanup of unrelated attachments. Validation and authentication failures preserve local data, and a conflict remains paused for human resolution."),
    ("user", "This should be a useful handoff summary, not a transcript search exercise. The current architecture is distributed across the initial client decision, storage review, API contract, retry discussion, and later implementation update. A few older proposals are quoted or repeated because teams refer back to them. Please recover the settled choices, distinguish the shipped record path from the unfinished attachment path, and identify the immediate next implementation step."),
    ("assistant", "I will distinguish adopted architecture from historical alternatives and current progress from the remaining attachment work. The upcoming summary should state the active storage and sync boundaries, durable offline constraints, explicit exclusions, superseded choices, and the adapter tests that unblock integration."),
]

DISCUSSION.extend([
    ("user", "The storage review also covered quota and permission failures. The adapter should treat browser capability detection as a runtime choice because managed devices do not all expose the same APIs. If filesystem permission is not granted, the user should still be able to complete an inspection using the blob fallback without an unexplained data loss. If IndexedDB itself reports a quota or transaction failure, surface an actionable error and keep the form state in memory until it can be saved; do not claim the draft is durable until the transaction commits."),
    ("assistant", "Capability selection belongs inside the attachment adapter. A denied or unavailable filesystem path uses the IndexedDB blob backend. A failed IndexedDB transaction is a failed persistence operation, not success; the UI must retain its working form state and communicate that it has not been safely saved."),
    ("user", "We should make the adapter contract describe ownership clearly. A write takes the inspection UUID and attachment identifier and returns a persisted reference only after the backend confirms the bytes are stored. A read returns the original bytes and metadata, and delete removes only that reference. The adapter should not decide whether a server upload is complete; SyncEngine owns acknowledgement and asks LocalStore to remove a local attachment only after the successful response for that attachment."),
    ("assistant", "The adapter handles durable local bytes and references. SyncEngine tracks transfer state and server acknowledgement. Delete is a local storage primitive, while the decision to invoke it is gated by a confirmed upload response. Keeping that distinction prevents a storage implementation from guessing about network state."),
    ("user", "For large photos, the upload can be interrupted after several chunks. Store the last server-acknowledged offset or equivalent transfer marker with the local sync state, then resume without starting over when the app returns. Do not mark the complete image as uploaded because an earlier chunk succeeded. If the server cannot resume a particular object, restart that object safely using its stable attachment identifier while retaining its local source."),
    ("assistant", "Progress is recorded per attachment and advances only as chunks are acknowledged. App launch resumes from the durable marker. A retry that restarts an object must still be idempotent, and local bytes remain until the full attachment receives a successful completion acknowledgement."),
    ("user", "The API team asked whether the client UUID belongs in the route or body. Keep it explicit in the request contract so logs and retries can carry it consistently, and store it with the server row under a unique constraint. A replay should return the existing inspection identity and current state. The version field remains a separate precondition on updates; a matching idempotency key should not bypass a stale-version conflict."),
    ("assistant", "The client-generated UUID is an explicit request field backed by a unique server constraint. Replaying a create resolves to the same inspection. On update, the server still checks the submitted version and returns a conflict when stale. Idempotency does not authorize overwriting a newer row."),
    ("user", "I want the UI to distinguish queued, sending, waiting for connectivity, needs correction, conflict review, and complete. These states help the crew understand why a draft is still local. The retry scheduler can record a next-attempt time, but the user should not have to understand the backoff calculation. A validation response should identify the field, and a conflict should offer compare or retry-after-resolution actions rather than an automatic loop."),
    ("assistant", "The sync state model will expose plain-language status while keeping retry timing internal. Transient transport failures schedule backoff with jitter. Validation waits for a field correction, and a version conflict waits for a person to resolve it. Completion is shown only after acknowledgement."),
    ("user", "A design note proposes using the phone's notification service to tell field crews that uploads finished. That could be useful for a later release, but the current flow shows completion when the app is open or next resumes. Please do not add notification permission prompts or push delivery to this milestone. It is the same out-of-scope push request discussed during the earlier manager review."),
    ("assistant", "Push notifications remain outside the release scope. The client displays the current sync state when open and restores it on the next launch. No notification permission or delivery service is required for the current implementation."),
    ("user", "The acceptance test for authenticated upload should include a valid session, a session that expires before transfer, and a response lost after the server has committed. The expired session must leave the local bytes intact and wait for reauthentication. The lost response should be safe to retry with the same idempotency identifiers. We should also verify that an unrelated attachment is not cleaned up when one upload succeeds."),
    ("assistant", "Those cases cover the important acknowledgement boundary: expired authentication preserves data; an ambiguous response retries safely with stable identifiers; and cleanup is scoped to the item whose completion was acknowledged. I will keep them with the attachment integration acceptance checks."),
    ("user", "The PWA can be installed from the browser, but that does not turn it into a separate native desktop client. We still ship one browser application to desktop and mobile devices and use the existing API. An old architecture sketch labels a desktop wrapper as a fallback if offline persistence is difficult. That sketch predates the IndexedDB and attachment adapter decision, so do not present it as an active contingency."),
    ("assistant", "Installability does not change the client architecture. The supported client remains the browser PWA on desktop and mobile. The native wrapper sketch is historical and is not a fallback plan."),
    ("user", "The backend contract review confirmed that the API reports the current version on successful read and write. LocalStore saves the last acknowledged value with the draft, and SyncEngine submits it during a later update. If it no longer matches, conflict review starts and local content stays available. The server does not accept a client-provided version as proof of ownership; authentication remains required independently."),
    ("assistant", "The version value detects stale state but does not replace authentication. Every upload still requires an authenticated request. A mismatch pauses the update and preserves the draft; a successful response becomes the next acknowledged version stored locally."),
    ("user", "The QA matrix should separate browser support from server behavior. We can unit-test backend selection and the read/write/delete contract in a deterministic environment, then manually verify capability permission on representative browsers. The API tests cover UUID replay, auth, version conflict, and validation. A failure in browser support should not be papered over by changing the server contract or by deleting the local file."),
    ("assistant", "Local adapter tests and API contract tests remain separate layers. Browser permission checks get focused compatibility coverage. None of those failures should remove local content or change idempotency and version semantics."),
    ("user", "A proposal to add an analytics dashboard has resurfaced in the sprint board because the manager asked for upload counts. Keep it parked. This delivery is still about reliable field capture, local persistence, and explicit foreground synchronization. We should avoid taking on reporting, notification, or background scheduling work before the attachment path is complete and the core recovery cases pass."),
    ("assistant", "Manager reporting remains out of scope for this delivery. The next engineering work is still the attachment adapter and its parity/fallback tests, followed by SyncEngine integration and acknowledgement-gated cleanup."),
    ("user", "When the offline queue has several inspections, a failure on one item should not prevent an unrelated valid item from syncing if the scheduler can safely continue. Keep ordering where a record must exist before its attachment, but isolate transient errors per item and preserve each draft. This is implementation detail for the retry tests; it does not introduce background work or change the client-triggered sync schedule."),
    ("assistant", "The foreground worker can continue independent queue items when dependencies permit, while preserving each failed item and respecting record-before-attachment order. This is per-item error isolation within the existing sync trigger model, not a new scheduler feature."),
    ("user", "We reviewed the plain-text rule with the API team. Text fields are UTF-8 strings with explicit maximum lengths; we should not persist HTML generated by a rich-text editor. The offline form can still support line breaks and normal text entry. If richer formatting becomes necessary later, it should be a new versioned contract rather than an implicit format change in the current payload."),
    ("assistant", "The current API payload carries plain UTF-8 text with length validation. Rich-text markup is not part of V1, and adding it later would require an explicit contract revision."),
    ("user", "The sync review asked for WebSocket as an optional optimization even if the client also polls. We should reject that suggestion for this release: app launch, pull to refresh, and an online local edit are the supported triggers. An optional websocket still adds deployment and reconnect behavior that we do not need to finish reliable foreground recovery. The old proposal should remain under superseded decisions."),
    ("assistant", "WebSocket is not an optional dependency for the current release. Sync remains client-triggered over the HTTPS API using the three agreed foreground triggers. Reconnect and retry behavior belong to the existing resumable SyncEngine."),
    ("user", "The prototype status can be stated without overstating completion: record persistence and metadata sync are integrated, but photos still follow a temporary path in the test harness. The shared attachment interface is drafted, and neither production backend has passed the common suite. Next we should complete backend selection, blob fallback, persistence across reload, and cleanup after acknowledgement, then wire the adapter into transfer."),
    ("assistant", "I will describe attachments as unfinished until both backends pass the shared tests. The immediate task remains completing the adapter implementations and fallback contract, then connecting them to SyncEngine. The metadata path being complete does not imply the photo path is complete."),
])

TRUTH = {
    "version": VERSION,
    "created_before_model_runs": True,
    "pass_rule": {
        "all_critical_facts_required": True,
        "minimum_overall_coverage_percent": 90,
        "stale_current_claims_allowed": 0,
        "next_step_must_be_correct": True,
    },
    "current_architecture": [
        {"id": "pwa_https_api", "critical": True, "alternatives": [["pwa", "https"], ["browser-based", "https api"]]},
        {"id": "localstore_indexeddb_records", "critical": True, "alternatives": [["localstore", "indexeddb"], ["inspection records", "indexeddb"]]},
        {"id": "attachment_filesystem_preferred", "critical": True, "alternatives": [["filesystem", "available"], ["filesystem", "supported"], ["file system", "supported"]]},
        {"id": "attachment_idb_blob_fallback", "critical": True, "alternatives": [["indexeddb", "blob", "fallback"], ["idb", "blob", "fallback"], ["indexeddb", "blobs", "falls back"], ["indexeddb blobs", "otherwise"]]},
        {"id": "shared_attachment_adapter", "critical": True, "alternatives": [["adapter", "read", "write", "delete"], ["adapter contract", "both backends"]]},
        {"id": "syncengine_resumable", "critical": True, "alternatives": [["syncengine", "resume"], ["sync", "resumable"], ["acknowledged transfer progress", "interruption recovery"], ["acknowledged transfer progress", "recovery after suspension or reload"], ["acknowledged progress", "resuming interrupted"], ["resuming from durable acknowledged progress"]]},
        {"id": "client_uuid_idempotency", "critical": True, "alternatives": [["uuid", "idempotent"], ["uuid", "idempotency"], ["client-generated id", "duplicate"], ["uuid", "replay", "duplicates"]]},
        {"id": "version_conflict_check", "critical": True, "alternatives": [["version", "conflict"], ["version checks"], ["stale", "reject"]]},
        {"id": "postgres_api", "critical": False, "alternatives": [["postgresql", "api"], ["postgres", "server"]]},
    ],
    "current_constraints": [
        {"id": "retain_until_ack", "critical": True, "alternatives": [["local", "authenticated upload", "acknowledg"], ["device", "server confirms", "draft"], ["retain drafts and photos", "authenticated upload", "acknowledged", "item"], ["retain drafts and photos", "authenticated success", "acknowledged", "particular item"], ["retain drafts", "authenticated", "acknowledged", "specific item"], ["retain drafts", "authenticated completion", "acknowledged", "specific item"], ["preserve drafts and photos", "authenticated success", "acknowledged", "specific item"]]},
        {"id": "retry_transient_only", "critical": True, "alternatives": [["exponential backoff", "jitter", "transient"], ["backoff", "transient", "validation"]]},
        {"id": "plain_text_accessibility", "critical": True, "alternatives": [["plain text", "screen reader"], ["plain utf 8", "screen reader"], ["plain text", "accessible"], ["plain utf 8", "accessible"]]},
        {"id": "foreground_sync_scope", "critical": True, "alternatives": [["app launch", "pull to refresh", "local edit"], ["app launch", "pull to refresh", "online local edit"], ["client-triggered", "no websocket"]]},
        {"id": "no_background_or_manager_features", "critical": False, "alternatives": [["background", "analytics", "push", "out of scope"], ["no periodic", "no analytics"]]},
        {"id": "conflicts_require_review", "critical": True, "alternatives": [["conflict", "local draft", "review"], ["conflict", "draft", "review"], ["stale", "preserve", "user"], ["conflict", "local content", "review"], ["conflict", "preserve local content", "explicit resolution"], ["conflicts preserve local content", "await resolution"]]},
    ],
    "superseded_decisions": [
        {"id": "localstorage_replaced", "critical": True, "alternatives": [["localstorage", "superseded"], ["localstorage", "replaced", "indexeddb"], ["localstorage"]]},
        {"id": "native_client_replaced", "critical": True, "alternatives": [["native desktop", "replaced", "pwa"], ["desktop app", "superseded", "browser"], ["native desktop"]]},
        {"id": "filesystem_only_updated", "critical": True, "alternatives": [["filesystem-only", "fallback"], ["filesystem only", "indexeddb", "fallback"], ["filesystem-only"]]},
        {"id": "websocket_proposal_rejected", "critical": False, "alternatives": [["websocket", "not", "current"], ["websocket", "superseded"], ["no websocket"], ["websocket sync"]]},
    ],
    "current_state": [
        {"id": "record_store_done", "critical": True, "alternatives": [["record", "indexeddb", "implemented"], ["localstore", "persist", "restore"], ["indexeddb record persistence", "integrated"], ["record", "indexeddb", "in place"]]},
        {"id": "metadata_sync_done", "critical": True, "alternatives": [["syncengine", "metadata", "implemented"], ["sync", "uuid", "version", "implemented"], ["metadata synchronization", "integrated"]]},
        {"id": "attachments_incomplete", "critical": True, "alternatives": [["attachment", "not complete"], ["attachment", "unfinished"], ["adapter", "still open"]]},
    ],
    "next_step": {
        "id": "attachment_adapter_contract_tests",
        "critical": True,
        "alternatives": [["attachment adapter", "contract", "filesystem", "indexeddb", "test"], ["adapter", "both backends", "fallback", "tests"], ["adapter", "both implementations", "contract tests"]],
    },
    "stale_claims": [
        {"id": "localstorage_is_current", "scope": "current_architecture", "reject_if_current_contains": [r"(?:use|store|save|write|keep)\s+(?:drafts?\s+in\s+)?localstorage", r"localstorage\s+(?:is\s+)?(?:the\s+)?(?:current|production|record)\s+store"]},
        {"id": "native_desktop_is_current", "scope": "current_architecture", "reject_if_current_contains": [r"(?:ship|build|target|use)\s+(?:a\s+)?native desktop", r"native desktop (?:client|app)\s+(?:is\s+)?(?:current|supported)"]},
        {"id": "filesystem_only_is_current", "scope": "current_architecture", "reject_if_current_contains": [r"filesystem-only", r"file system only", r"only filesystem storage"]},
        {"id": "websocket_push_is_current", "scope": "current_constraints", "reject_if_current_contains": [r"(?:use|enable|add|require|depend on)\s+(?:a\s+)?websocket", r"websocket push\s+(?:is\s+)?(?:current|required|supported)"]},
        {"id": "delete_before_ack", "scope": "current_constraints", "reject_if_current_contains": [r"(?:delete|remove|clear)\b.{0,35}\b(?:before|prior to)\b.{0,20}\b(?:acknowledg|confirm|success)"]},
    ],
    "excluded_unrelated_topics": ["green icon", "North region pilot date", "analytics dashboard"],
}


def build() -> tuple[dict, dict]:
    previous = json.loads(SOURCE.read_text(encoding="utf-8"))
    history = [message for message in previous["history"] if message["id"] != "h39"]
    # Preserve source provenance, but explicitly annotate the architecture decisions
    # whose updates are already stated in the original, unmodified V0.5 history.
    by_id = {message["id"]: message for message in history}
    by_id["h03"].setdefault("metadata", {})["supersedes"] = ["h01"]
    by_id["h09"].setdefault("metadata", {})["supersedes"] = ["h07"]
    by_id["h19"].setdefault("metadata", {}).setdefault("relationships", []).append(
        {"kind": "updates", "target": "h09"}
    )
    start = datetime(2026, 5, 14, 9, 0, tzinfo=timezone.utc)
    for index, (role, content) in enumerate(DISCUSSION, start=40):
        happened = start + timedelta(days=(index - 40) // 2, minutes=(index % 2) * 14)
        history.append({
            "id": f"v07-{index:03d}",
            "role": role,
            "timestamp": happened.isoformat().replace("+00:00", "Z"),
            "content": content,
        })
    history.append({
        "id": "v07-question",
        "role": "user",
        "timestamp": "2026-07-01T09:30:00Z",
        "content": QUESTION,
    })
    fixture = {
        "version": VERSION,
        "title": "Atlas offline inspection implementation handoff",
        "history_id": "atlas-v07-economics",
        "history": history,
        "question": QUESTION,
        "output_requirements": [
            "Return concise bullet points under these headings: CURRENT ARCHITECTURE, CURRENT CONSTRAINTS, SUPERSEDED DECISIONS, CURRENT STATE, NEXT STEP.",
            "Use only this supplied conversation. Include the implemented versus unfinished state; do not present old proposals or unrelated release notes as current.",
        ],
        "model_runs_started": False,
    }
    return fixture, TRUTH


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    fixture, truth = build()
    fixture_bytes = (json.dumps(fixture, ensure_ascii=False, indent=2) + "\n").encode()
    truth_bytes = (json.dumps(truth, ensure_ascii=False, indent=2) + "\n").encode()
    (OUT / "fixture.json").write_bytes(fixture_bytes)
    (OUT / "ground-truth.json").write_bytes(truth_bytes)
    payload = ConversationAdapter().ingest({"conversations": [{
        "id": fixture["history_id"], "title": fixture["title"], "messages": fixture["history"]
    }]})
    ordered = sorted((unit for unit in payload if unit.source_type == "message"), key=lambda unit: unit.metadata["order"])
    full_history = "\n\n".join(
        f"[{unit.metadata['timestamp']} {unit.metadata['role']}] {unit.content}" for unit in ordered
    )
    freeze = {
        "fixture_version": VERSION,
        "fixture_sha256": hashlib.sha256(fixture_bytes).hexdigest(),
        "ground_truth_sha256": hashlib.sha256(truth_bytes).hexdigest(),
        "question": QUESTION,
        "messages": len(fixture["history"]),
        "history_tokens_cl100k": token_count(full_history),
        "model_runs_started": False,
        "pass_rule": truth["pass_rule"],
    }
    (OUT / "freeze.json").write_text(json.dumps(freeze, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(freeze, indent=2))


if __name__ == "__main__":
    main()

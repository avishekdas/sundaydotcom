# 05 — Events & Real-time

## 5.1 Outbox → EventBridge (ADR-004)
1. The single mutation statement inserts outbox row(s) `(event_id uuid, type, board_id, item_id, payload)` (03 §3.5).
2. After the statement returns, the Lambda calls `PutEvents` (AWS SDK, ~15 ms, not a Data API call) and then responds. It does **not** mark the row (AR-3).
3. An EventBridge rule routes every event also to the small `outbox-ack` queue; `outbox-acker` λ marks `published_at` in batches (`update … where event_id in (…)`, one statement per 10 events).
4. `outbox-sweeper` (every 1 min, singleton via **lease row** `tl.leases` + function concurrency limit 1 — advisory locks don't survive Data API calls, FR-3) republishes rows with `published_at is null and created_at < now() - 30s` using **exponential backoff per row** (`publish_attempts`, `last_published_at`: 30 s, 1, 2, 4… min, max 1 h) and a **cap of 500 rows per tick**; alarms on rows with attempts > 3 and on backlog > 1,000; if the ack rate is zero for 5 min while publishes succeed, the sweeper stops republishing (circuit open, alarm) — protects consumers from duplicate floods when the acker is broken (OPS-5).
   - `PutEvents` partial failures (`FailedEntryCount > 0`) are retried inline once; metric `outbox.put_partial_fail` (OPS-16).
   - An ack proves delivery to the `outbox-ack` target only; every EventBridge rule target has a retry policy and its own DLQ (OPS-4) and a daily per-consumer reconciliation compares consumer high-water marks with the outbox.
   - Fan-out keeps a 10-minute DynamoDB dedup of event ids already sent to sockets.
5. Consumers are idempotent by `event_id`. Published rows are purged after 7 days.
- Ordering: EventBridge delivers to standard SQS queues. Consumers that need ordering (automations, recompute) have a small **dispatcher** step that reads the standard queue, resolves the work (which automations listen, which dependents to recompute) and enqueues to an SQS **FIFO** queue with a dynamic `MessageGroupId` (`auto:{automationId}:{itemId}`, `comp:{itemId}`). EventBridge targets only support a static group id, hence the dispatcher.
- Event size ≤ 64 KB; payload carries ids + changed column ids + new values for scalar columns (not computed values; see D-018).

## 5.2 Event catalog (P1)
| Type | Emitted by | Key payload | Consumers |
|---|---|---|---|
| `item.created` | workmgmt | item id, board, group, creator actor, initial values | realtime, automation (T1), recompute, indexer, notifier (people) |
| `item.values_changed` | workmgmt | item, changes `[{col, old, new}]`, actor, version | realtime, automation (T2/T3), recompute, indexer, notifier |
| `item.moved` (group/board) | workmgmt | from, to | realtime, automation (T6), recompute |
| `item.archived/deleted/restored` | workmgmt | | realtime, recompute, indexer |
| `item.links_changed` | workmgmt | column, added, removed (both sides) | realtime, automation (T2 on reflected side), recompute |
| `item.computed_changed` | computed | item, columns, `computed_version`, `full_visibility_boards`, hop | realtime (D-018), recompute (next hop, AR-14) |
| `board.bulk_changed` | workmgmt, jobs | item ids or all | realtime |
| `board.structure_changed` | workmgmt | kind of change, version | realtime, automation (G1.15 validation), recompute (formula/mirror dependency rebuild) |
| `view.changed`, `group.*` | workmgmt | | realtime |
| `button.clicked` | workmgmt | item, column | automation (T5) |
| `crm.activity_created` | crm | activity item, related items, type, start | automation (T7, once per related item's board) |
| `update.posted/edited/deleted`, `update.liked` | collab | | realtime, notifier (mentions, replies, subscribers), indexer (P2) |
| `notification.created` | collab | user | realtime (user channel) |
| `permission.changed` | identity | user ids or board id, new perm_epoch | realtime (re-authorize), all caches |
| `automation.run_finished` | automation | status | realtime (run history live), notifier (failures, G7.3) |
| `schedule.tick` | scheduler | local times due | automation (T4), recompute (nightly TODAY), jobs (purge, partition maintenance) |

## 5.3 WebSocket protocol (ADR-005)
- Connect: `wss://ws.<domain>?ticket=<single-use ticket>` from `POST /realtime/ticket` (07 §7.1); the `$connect` authorizer consumes the ticket; connection row stored with user id and current `perm_epoch`. No JWT in URLs.
- Client → server messages: `{"op":"sub","ch":"board:123"}`, `{"op":"unsub",…}`, `{"op":"ping"}` (every 30 s; also presence heartbeat), `{"op":"presence","board":123}`.
- Channels: `board:{id}` (items, structure, views, presence), `item:{id}` (updates, timeline), `user:{id}` (notifications, permission changes), `dashboard:{id}` (widget invalidations).
- **Revocation rule (one bound, FR-8)**: authorization at subscribe time; targeted re-authorization of the affected users' connections on `permission.changed`; and on every batch, an epoch backstop re-checks any connection whose stored epoch is older than the global epoch and was last authorized > 30 s ago. Bound: ≤ 30 s + event lag (< 60 s) — F7.7, AC-F7-2.
- Server → client envelope: `{"ch":"board:123","type":"item.values_changed","item":"90210","version":57,"seq":10433,"mutation_id":"…","data":{…}}` — `seq` is the `board_changes.seq` of the change; `mutation_id` echoes the client's mutation (09 §9.3a). Schema: `contracts/ws-messages.json`.
- **Payload shaping (D-018)**: scalar values are sent as-is to anyone allowed on the board; `item.computed_changed` carries values only for connections whose user can see all `full_visibility_boards`; others get `{"type":"invalidate","item":…,"columns":[…]}` and re-fetch via `GET /items/{id}?columns=` (per-viewer computation). Row-level boards (`row_visibility='related'`) check per-item visibility before sending (D-020).
- **Ordering & gaps (AR-2)**: messages carry `version` (user data) or `computed_version` (computed values) per item, plus the board `seq` (03 §3.3a). Client rule per item and counter: `v ≤ cached` → drop; `v == cached + 1` → apply; `v > cached + 1` → apply the delta **and** refetch the row (`GET /items/{id}?columns=…`) because intermediate deltas may be missing or delayed. A contract test injects reordered and dropped messages.
- **Reconnect**: client calls `POST /boards/{id}/changes {since_xmin}` (03 §3.3a xid cursor) and refetches listed rows via `items:fetch`; `410 resync` (cursor > 24 h) or > 2,000 changes → full view reload (F7.3, AC-F7-3).
- **Message size**: payloads > 28 KB (WebSocket frame 32 KB) are replaced by `invalidate` for the affected item/columns.
- **Presence (AR-10)**: heartbeat (30 s) upserts `presence{board,user,last_seen}`; reads filter `last_seen > now − 60 s` (TTL is garbage collection only). Leave events: `$disconnect` publishes `presence.changed`; stale entries (`last_seen` older than 60 s) are detected by `ws-handlers` whenever it processes a heartbeat on that board, and by a once-per-minute sweep job dispatched by `scheduler-tick` (FR-7), emitting `left` → avatar disappears ≤ 60 s while others are on the board, ≤ 2 min otherwise; clients also filter avatars by `last_seen` locally so the UI never shows stale presence > 60 s (AC-F7-4).

## 5.4 Fan-out worker
SQS realtime (standard, batch 10, window 100 ms) → `fanout` λ (`MaximumConcurrency` 25; events of a batch processed in parallel, grouped by channel; each connection receives **one array message per batch**; partial batch response) (PERF-13):
1. Resolve channel → connection records (GSI `channel`); each record holds `user_id, role, perm_epoch_at_subscribe, visible_boards_hash` captured at subscribe (AR-11).
2. `permission.changed` events carry the **affected user ids** (or a board id); only those users' connections are re-authorized, in one SQL statement (PERF-13). The global `perm_epoch` remains the backstop described in §5.3 (FR-8). Revoked ones get `{"type":"access_revoked"}` and are unsubscribed (AC-F7-2). Channel authorization (SEC-13): `board:{id}` → board visible; `item:{id}` → item visible incl. row visibility; `user:{id}` → must equal caller; `dashboard:{id}` → dashboard visible; presence messages accepted only for boards the caller can see and always attributed to the caller's own user id; unknown channel types denied.
3. Row-level boards (D-020): one SQL statement per event returns the subset of subscribed user ids that can see the item.
4. Computed events (D-018): one statement returns users with full visibility of the contributing boards; others get `invalidate`.
5. `PostToConnection` in parallel (thread pool 32); `GoneException` deletes the connection.
Target ≤ 2 s p95 commit → socket, measured by the synthetic canary.

**Bulk changes (AR-22)**: bulk operations, imports, template apply and nightly recompute emit one `board.bulk_changed {item_ids (≤ 1,000) | all}` event per transaction/batch instead of per-item realtime events (per-item events still flow to automations/recompute/indexer via a `realtime:false` flag); clients re-query the current page. Fan-out is rate-limited per board (≤ 20 messages/s per connection, excess coalesced into `invalidate`), with the per-board counter held in DynamoDB (PERF-13).

## 5.5 Notifications pipeline
`notifier` consumes item/update/automation events → computes recipients (assignee added, mentions, subscribers, automation recipients) minus actor, minus muted, minus users who cannot see the item → inserts `notifications` (unique `(user_id, event_id, type)` for dedup; grouping key for A1 "and N more").
- **Per-recipient rendering (AR-17, D-019)**: automation notify actions store the message **template + variable references** in the event; the notifier renders the text per recipient, using that recipient's visibility for visibility-sensitive variables (per-viewer mirror/formula path). AC-G1-11 is an integration test.
- **Low latency (AR-29)**: the notifier pushes `notification.created` **directly** to the recipient's `user:{id}` connections (`PostToConnection`) instead of a second EventBridge/SQS hop; mentions therefore reach the bell in ≈ 2 hops total (AC-E3-1).
- **SES hygiene (OPS-11)**: account-level suppression list; configuration sets `transactional` (invites, resets, notifications) and `crm` (P2) with event destinations (bounce/complaint/delivery → SNS → notifier marks the address undeliverable on the user/contact); alarms on bounce > 2 % and complaint > 0.05 %; throttling → backoff; sandbox exit and quota request in the bootstrap runbook.
- **Email**: enqueue to SQS with `DelaySeconds=300` keyed `(user,item)`; when the delayed message fires, send one SES email summarizing unsent notifications for that pair (A9.3 coalescing, AC-A9-4).

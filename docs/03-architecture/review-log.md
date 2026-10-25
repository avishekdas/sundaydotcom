# Architecture Review Log

## Round 1 — independent architecture agent (2026-10-24)
Verdict: 45 % ready. 2 Blockers, 23 Majors, 8 Minors. All resolved in v0.2:

| ID | Sev | Resolution |
|---|---|---|
| AR-1 | Blocker | ADR-013 auth proxy; per (email, viewer IP) counter before Cognito (07 §7.1) |
| AR-2 | Blocker | version/computed_version gap detection + refetch; contract test with reordering (05 §5.3, 09) |
| AR-3 | Major | single writable-CTE statement per mutation; deltas in SQL; ≤ 2 calls hot path; async ack instead of mark-published (03 §3.5, 05 §5.1) |
| AR-4 | Major | JSON-text sets; strict fake rejects arrays (03 §3.9, 07 §7.2) |
| AR-5 | Major | reader removed from perf mitigations; failover-only option (02 §2.3, 08 §8.1, 10 §10.2) |
| AR-6 | Major | execute-api disabled, origin secret header, origin request policy, WS limits (02 §2.5, 07 §7.4) |
| AR-7 | Major | app-authoritative counters on viewer IP, WAF JS SDK + token label → header, Bot Control costed (07 §7.4) |
| AR-8 | Major | pool MFA ON + `SetUserPoolMfaConfig`; breached-password Bloom in auth proxy (07 §7.1) |
| AR-9 | Major | `tokens_valid_after`; WebSocket single-use tickets (07 §7.1) |
| AR-10 | Major | presence `last_seen` filter + disconnect/sweep leave events (05 §5.3) |
| AR-11 | Major | connection records carry epoch; batch re-authorization; one SQL per event for row/computed visibility (05 §5.4) |
| AR-12 | Major | version-keyed caches (automation_version, perm_epoch piggy-back); no "event invalidation" (06 §6.2, 07 §7.2) |
| AR-13 | Major | UnitOfWork: step row in the same statement; `created_idem_key` (06 §6.3, 03) |
| AR-14 | Major | second hop dispatched from first-hop computed event; coalescing dedup ids (08 §8.2) |
| AR-15 | Major | formula → SQL compiler; explicit depth-2 per-viewer CTE; perf test (08 §8.3) |
| AR-16 | Major | visibility rule table + ADR-014 single builder + generated tests (07 §7.2a) |
| AR-17 | Major | notifier renders per recipient from template + variable refs (05 §5.5) |
| AR-18 | Major | ADR-015 board_changes seq + overlap; `/changes` endpoint (03 §3.3a, 04) |
| AR-19 | Major | one row per link, reflection via reverse index; ordered locks; replace semantics (03) |
| AR-20 | Major | containment filters for GIN; no runtime DDL; item_sort_keys fallback; Spike S-1 gate (08 §8.1) |
| AR-21 | Major | list projections cap bodies; activity log truncation; size test (03 §3.9) |
| AR-22 | Major | board.bulk_changed; 28 KB cap → invalidate; per-board fan-out rate limit (05 §5.4) |
| AR-23 | Major | authoritative inventory 02 §2.7; 01/05/06/11 aligned; endpoints added to 04; this log created |
| AR-24 | Major | StrictDataApiFake + local-data-api job blocking per PR; in-process bus; deployed e2e with fake clock (10 §10.3) |
| AR-25 | Major | 2 API functions; SnapStart xor PC chosen by measurement; costed (02 §2.4, ADR-012) |
| AR-26 | Minor | cost re-estimated; standard ≈ $225 / lean ≈ $185; user decision (10 §10.4) |
| AR-27 | Minor | T4 per-automation watermark with catch-up and DST handling (06 §6.4) |
| AR-28 | Minor | outbox purge; notification unique key; in-progress idempotency rows; form submission_id (03, 05, 07) |
| AR-29 | Minor | notifier pushes user-channel directly (05 §5.5) |
| AR-30 | Minor | presigned POST with length range; magic-byte sniff; separate files domain; attachment for SVG/HTML (07 §7.3) |
| AR-31 | Minor | MaximumConcurrency instead of reserved concurrency; quota runbook (02 §2.4) |
| AR-32 | Minor | migrations as pipeline step; expand/contract across releases; staging rehearsal (02 §2.6) |
| AR-33 | Minor | in-region DR scope; Cognito export; multi-region KMS; reconciliation script (10 §10.2) |

## Round 2 — Architecture council (4 independent reviewers, 2026-10-24)
| Reviewer | Verdict | Findings |
|---|---|---|
| Security | 65 % | 1 Blocker (SEC-1), 13 Major, 6 Minor |
| Performance & data | 75 % | 1 Blocker (PERF-1), 12 Major, 7 Minor |
| Reliability, ops & cost | 60 % ready | 1 Blocker (OPS-1, a defect in the AR-14 fix), 11 Major, 6 Minor |
| DX, testability & frontend | 72 % | 2 Blockers (DX-1, DX-2), 12 Major, 5 Minor |

Resolutions (section references are where the fix lives):
| IDs | Resolution |
|---|---|
| SEC-1, SEC-2, SEC-3 | file binding + write-reference authorization + permission guard inside the mutation (03 §3.5); visibility table rows (07 §7.2a) |
| SEC-4…7 | per-account cap + CAPTCHA, Cognito interplay (D-022 proposed), no enumeration, rate limits, IP parsing, WAF-prefixed header + CloudFront Function stripping, Spike S-2 (07 §7.1/7.4) |
| SEC-8, SEC-9, SEC-10 | form built only from definition; CSV escaping + job ownership + safe parsing; formula→SQL allow-list + bind params + read-only role (07, 08 §8.3) |
| SEC-11 | `auth` λ split; Postgres roles per function class (07 §7.3, 02 §2.7) |
| SEC-12 | WS ticket-only in 05 (also DX-17) |
| SEC-13 | channel authorization rules (05 §5.4, 07 §7.2a) |
| SEC-14…20 | logs/error redaction; idempotency PK per user; revocation steps + MFA reset; rich-text write validation + headers; CloudFront signed URLs; WS behind CloudFront+WAF; account baseline, OIDC trust, fake clock excluded at synth |
| PERF-1, PERF-2 | order-preserving, empty-safe delta SQL; locking pre-image CTE + CTE rules (03 §3.5) |
| PERF-3 | connect locks/version bumps for every affected item (03 §3.5) |
| PERF-4 | transactional cursor with `xid8` / snapshot xmin (03 §3.3a) |
| PERF-5/6/7/8, OPS-1 | recompute redesign: dirty set, inline same-item formulas, set-based bulk, leaf-set depth 2, decomposable partial aggregates, drift checker (08 §8.2/8.3) |
| PERF-9, PERF-11 | lz4, single-pass `jsonb_to_record` extraction, `item_text`, composite GIN measured in S-1, fillfactor (03, 08 §8.1) |
| PERF-10 | S-1 side-by-side measurements; target D-023 proposed |
| PERF-12, PERF-13 | widget result cache keyed by seq; fan-out batching/concurrency/targeted re-authorization (08 §8.5, 05 §5.4) |
| PERF-14…20 | board search via index; ordered bulk locks + chunked conversions; daily partitions for outbox/board_changes; round-trip budget; no `any(:param)`; ids not creation-ordered; activity_log indexes + `to_board_id` |
| OPS-2…6 | delivery contract table + CDK assertions (02 §2.8); dispatcher re-send + reaper; EventBridge/Scheduler retry+DLQ+KMS grants; sweeper backoff/cap/circuit; singleton leases, heartbeat alarm, partition headroom |
| OPS-7…12 | Sev1/Sev2 alarms, paging, runbooks; canary deploys + versioned events + consumer-first order; migration lock_timeout + squawk + retain/replace gate; SSM-based restore + db_generation; SES hygiene; scheduled 2 ACU floor + DB visibility |
| OPS-13…18 | reader re-costed; Lambda/S3/paging re-costed (≈ $245 lean, D-024 proposed); sampling/log rules; PutEvents partial failure; dev resume handling + masked rehearsal; per-DLQ policies + replay |
| DX-1…19 | entity store + pending-ops reconciler + subscribe-then-load + batched fetch + ordered id list (09 §9.3a/b); QuerySpec (03 §3.4a); layered modules + Mutation fragments (11); local stack (10 §10.5); chaos bus; CI budget & Tier A/B north star (10 §10.3); column/WS/settings contracts (09 §9.3c); catalog DTO (06 §6.7); formula semantics (08 §8.6); D-021 server-side filtering |

## Round 3 — architect final pass (2026-10-25)
Verdict: no Blockers; 5 Majors + 7 Minors introduced or left by earlier fixes; 80 % → ≈ 88 % after fixes.
| ID | Resolution |
|---|---|
| FR-1 | gap-sync cursor is an xid8 watermark (`since_xmin`), no overlap; 03 §3.3a, 05, 04, 09 aligned |
| FR-2 | recompute claim with lease; delete only on matching seq in the write statement; reaper; fault test |
| FR-3 | `tl.leases` table instead of advisory locks; concurrency 1 on sweeper/tick |
| FR-4 | row-visibility contributors never folded per board; visibility table row added |
| FR-5 | forms use the Python domain service with `worker_forms` grants (no PL/pgSQL submit) |
| FR-6 | 02 §2.7 is the single source; DB role column; 01/04/08 names fixed; single dispatcher |
| FR-7 | presence sweep: ws-handlers on heartbeat + tick-dispatched job |
| FR-8 | one real-time revocation rule (targeted + epoch backstop, < 60 s) |
| FR-9 | CTE rule 3 reworded; numeric person ids; parent-item guard; 404/403/retry classification |
| FR-10 | `on conflict … do update … returning id` for step replays |
| FR-11 | `tokens_valid_after` truncated to seconds |
| FR-12 | retention made consistent (48 h partitions, 24 h cursors); global-epoch cost documented |
Status: architecture v1.0 — ready for TDD milestone planning, gated by Spikes S-1, S-2, S-3 in M0. Pending user decisions D-022…D-024 (plan uses the proposed values and re-plans if changed).

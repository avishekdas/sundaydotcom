# 10 — Operations, Reliability, Cost

## 10.1 Observability (NFR-O1…O3)
- **Powertools for AWS Lambda (Python)**: structured JSON logger with `correlation_id` (API request id → propagated in outbox event `meta.correlation_id` → SQS → runner → fan-out), Tracer (X-Ray, segments for Data API calls), Metrics (EMF).
- **SLO metrics**: API latency p95 per route group; `realtime.fanout_lag_ms` (commit → PostToConnection); `automation.trigger_to_action_ms`; `recompute.lag_ms`; `search.index_lag_ms`; `outbox.unpublished_age_s`; queue `ApproximateAgeOfOldestMessage`; DLQ depth; Data API errors/throttles; Aurora ACU & CPU; WebSocket connection errors.
- **Alarms with severities (OPS-7)** — each alarm description contains its runbook URL (`ops/runbooks/*.md`):
  - **Sev1 (page via AWS Incident Manager / SMS)**: canary failing 2/3 runs; API 5xx > 2 % for 5 min; SLO burn rate (1 h window, 14× budget); outbox unpublished age > 5 min; scheduler heartbeat missing 3 min; Aurora unavailable; SES sending paused.
  - **Sev2 (ticket/email)**: SLO burn rate (6 h, 6×); any DLQ depth > 0; stuck automation runs > 5 min; EventBridge/Scheduler failed invocations; Lambda throttles and event-source-mapping errors; PostToConnection error rate > 5 %; Data API throttling; Aurora at max ACU 10 min, deadlocks, free storage; partitions < 2 ahead; computed drift > 0; SES bounce > 2 % / complaint > 0.05 %; budget 80 %/100 %; Cost Anomaly Detection.
- **Runbooks (minimum set)**: DLQ triage & redrive per queue policy (02 §2.8), outbox backlog / circuit open, Aurora at max ACU, writer failover, PITR restore, SES suspension, Lambda quota exhaustion, bad-deploy rollback, consumer replay (`ops/replay --consumer X --from --to` over the outbox), Cognito user restore.
- **Database visibility (OPS-12)**: `pg_stat_statements`, `log_min_duration_statement=500ms`, `auto_explain` (sampled) shipped to CloudWatch; Performance Insights during business hours (≥ 2 ACU).
- **Tracing & logs cost (OPS-15)**: X-Ray sampling 1 req/s + 5 %; INFO logs with dynamic DEBUG via Powertools; retention prod 30 d app / 90 d audit-relevant, staging 7 d.
- **Synthetic canaries** (CloudWatch Synthetics, every 5 min, prod & staging): sign-in → edit cell → receive WebSocket event (measures F7 ≤ 2 s) → public form submit.
- **Dashboards**: one CloudWatch dashboard per stage with the SLO panels.

## 10.2 Reliability (NFR-A1…A4)
| Concern | Design |
|---|---|
| 99.9 % availability | All managed multi-AZ services. Aurora storage is 6-way replicated across 3 AZs; without a reader, writer replacement takes ≈ 10 min (≈ 4 such events/month still meet 99.9 % = 43 min). A reader (failover only — Data API is writer-only) is a config switch (+≈ $45/mo) |
| RPO ≤ 5 min / RTO ≤ 4 h | **Scope: in-region restore** (meets NFR-A2). Aurora PITR (35 d); DynamoDB PITR; S3 versioning. Off-region: AWS Backup daily copy with multi-region KMS keys + S3 replication (disaster insurance, not covered by the RTO). Cognito users exported nightly to S3 (TOTP seeds cannot be exported → users re-enroll MFA after a pool rebuild). Restore runbook (OPS-10): restore to a new cluster → enable Data API → swap SSM parameters → redeploy; purge/quarantine SQS queues and DynamoDB connection/presence tables; increment `account.db_generation` (clients full-reload); replay unpublished outbox; rebuild search index; verify S3 objects referenced by `tl.files`. Drill time recorded against the 4 h RTO each release (in a quarantined account). |
| Durable async work | Outbox + sweeper (backoff, cap, circuit); delivery contract 02 §2.8; idempotent consumers; per-queue DLQ policies and `ops/replay` (OPS-18) |
| Graceful degradation (NFR-A3) | SPA falls back to 30 s polling of `changes?since` if WebSocket fails; search failure falls back to name `ilike` on visible boards |
| DB cold starts | Prod never auto-pauses; dev auto-pauses — the `Db` adapter treats `DatabaseResumingException` as retryable (up to 30 s) and the post-merge pipeline wakes the cluster first (OPS-17) |
| Planned maintenance | fixed weekly maintenance window (Sun 03:00 account tz); engine patch restarts counted against the 99.9 % error budget (OPS-12) |
| Lambda cold starts | 2 API functions only; slim packages; measured in Milestone 0; then SnapStart **or** provisioned concurrency on `api` (mutually exclusive) |

## 10.3 Testing pyramid & CI/CD (revised after AR-24)
| Layer | Runs where | What |
|---|---|---|
| Unit (pytest, vitest) | every PR | pure logic: authz, codecs, formula (Python + SQL compile golden table), query plans, triggers, variables, visibility rule table |
| Integration — DB | every PR, **blocking** | domain services against Postgres 16 in Docker through **`StrictDataApiFake`** (wraps psycopg, enforces Data API semantics: no array params, typed parameter mapping, 64 KB row / 1 MiB response limits, 45 s timeout); pytest-xdist with a template database per worker + per-test rollback. The `PsycopgDb` and `local-data-api` emulator variants run on main and nightly (DX-9). `InProcessBus` in two modes: `sync` (deterministic) and **`chaos`** (seeded shuffle, duplicates, delays, honours FIFO group ids) — flow tests (automation chains, two-hop recompute, notifier dedup, client sync) run in chaos mode with 3 fixed seeds per PR and 500 rotating seeds nightly (DX-8, plan TP-12) |
| Contract | every PR | OpenAPI conformance; permission matrix (AC-K3-4) and visibility table (07 §7.2a) generated tests; WebSocket message schema & reorder/drop injection (AR-2); CDK assertions on synthesized templates (queues ↔ rules ↔ functions inventory 02 §2.7) + cdk-nag |
| **North star Tier A** (DX-10) | every PR | `tests/system/test_north_star.py` drives the HTTP API through the devserver + InProcessBus (sync and chaos) with a fake clock; steps gated per milestone by `@milestone(n)`; steps defined once in `contracts/north_star.yaml` |
| Deployed e2e — **North star Tier B** | dev **and staging on every merge to main** (satisfies NFR-Q3) | Playwright north-star from the same manifest, API e2e via generated client, real Data API / Cognito / WebSocket / EventBridge wiring; fake-clock endpoint (dev/staging only, flag-guarded) for T4/DST and nightly tests |
| Load / perf | staging, end of each milestone | k6: NFR-P targets relevant to delivered features; Spike S-1 at Milestone 0 |

Migration rehearsal runs on a **masked, synthetic-scale** staging database (no prod PII copied); the real prod snapshot is used only in the quarantined restore drill (OPS-17).

Pipeline: PR (budget ≤ 10 min): `lint` (ruff, mypy --strict, import-linter, eslint, tsc) → `unit` → `integration` (StrictDataApiFake, chaos flows) → `contract` (incl. contract drift + oasdiff) → `north star Tier A` → `synth`. Merge to main: deploy dev → migrate → Tier B → deploy staging → migrate → Tier B (+ load gates at milestone ends) → manual approval → prod. Feature flags (`tl.flags`) for dark-launching P2 features.

## 10.4 Cost model (revised after AR-25/26; us-east-1 list prices, monthly, 100 active users)
| Item | Basis | Standard profile | Lean profile |
|---|---|---|---|
| Aurora Serverless v2 writer | 0.5 ACU floor nights/weekends, 2 ACU floor business hours (OPS-12) | $110 | $110 |
| Aurora reader (failover only) | optional | $0 (off) | $0 |
| Aurora storage/IO, Data API | 20 GB, ~8 M calls | $8 | $8 |
| Lambda (13 functions, arm64; Data-API wait time is billed) | ~12 M invocations, ~2.4 M GB-s; Power Tuning in M0 (OPS-14) | $30 | $25 |
| Cold-start mitigation on `api` | SnapStart (cache + restores) or PC 1 × 1 GB | $15 | $0 (measure first) |
| API GW HTTP + WebSocket | | $10 | $10 |
| EventBridge + SQS (incl. idle pollers on 9 queues) | ~20 M | $10 | $10 |
| DynamoDB | | $4 | $4 |
| CloudFront (2 dists) + WAF ACL + rules | | $15 | $15 |
| WAF Bot Control (challenge SDK for forms) | targeted, low volume | $12 | $12 |
| Cognito Essentials | ≤ 10k MAU | $0 | $0 |
| CloudWatch logs, metrics, ~35 alarms | 30 d / 7 d retention | $25 | $15 |
| Synthetics canaries | every 5 min / every 15 min | $20 | $7 |
| X-Ray (sampled), KMS (8 keys), Secrets, Route 53, SES, Backup copy | | $22 | $20 |
| S3 files | per 100 GB incl. cross-region replica ≈ $5 (Intelligent-Tiering); 2 TB ≈ $90 | $5 | $5 |
| Incident Manager / SMS paging | | $5 | $5 |
| **Total prod** | | **≈ $290** | **≈ $245** |
| Staging | | ≈ $90 | ≈ $60 |
| Dev | auto-pause | ≈ $25 | ≈ $25 |
Optional: promotion-tier-0 reader ≈ +$75. Cost reporting (NFR-O5, OPS-15): cost-allocation tags per component, Cost Anomaly Detection, monthly Cost Explorer report per account.
The US$150 prod target cannot be met with the controls now required (WAF Bot Control for I7, origin protection, paging) and a database sized for NFR-P1 during business hours (2 ACU floor; cold resume would break NFR-P1). **Recommendation: lean profile (≈ $245/mo prod at 100 active users, ≈ $60 staging, ≈ $25 dev) — decision requested from the user.**

## 10.5 Local development stack (DX-7)
`make dev` starts: Postgres 16 (Docker) with migrations + seed (`tasklane seed --crm --items 5000`), `tasklane.devserver` (Starlette app mapping HTTP to the Powertools resolver events, a local WebSocket endpoint, the workers running in-process on `InProcessBus`), and Vite (proxy `/api`, `/ws`). Ports with fake/real adapters: `Db` (psycopg/StrictFake ↔ Data API), `Bus` (InProcess ↔ EventBridge), `ConnectionGateway` (local WS ↔ PostToConnection), `IdentityProvider` (dev provider issuing local JWTs ↔ Cognito via auth proxy), `Clock` (fake ↔ system), `BlobStore` (local dir ↔ S3), `Mailer` (file log ↔ SES). Goal: ≥ 90 % of tickets need no AWS access.

# Architecture Decision Records

Format: Context · Decision · Alternatives · Consequences. Status of all: **Proposed** (until architecture review completes).

## ADR-001 Aurora PostgreSQL Serverless v2 as system of record
**Context:** dynamic per-board schemas with ad-hoc AND/OR filters, multi-key sort, group-by, aggregates (B12, D2, H3), relations with reflections in one transaction (C18.1), 2-hop mirrors, row-level visibility joins (D-020), ≤ 1M items.
**Decision:** Aurora PostgreSQL 16, Serverless v2; cell values as JSONB per item; relations as rows.
**Alternatives:** (a) DynamoDB single-table + OpenSearch for queries — every filter/aggregate/visibility rule duplicated across two stores, eventual consistency between them, OpenSearch Serverless minimum ≈ US$350/mo; (b) DynamoDB only — ad-hoc filter/sort/aggregate infeasible without scans; (c) Aurora DSQL — no JSONB GIN indexes / limited features at time of writing.
**Consequences:** + one transactional, queryable store; + simpler testing (real Postgres in CI). − not "pure" pay-per-request (0.5 ACU floor in prod ≈ $45/mo); − vertical scaling limits far above D-007.

## ADR-002 RDS Data API instead of drivers in a VPC
**Decision:** Lambdas use the Data API (HTTPS, IAM auth, Secrets Manager credentials); repository code depends on a `Db` port with two adapters: `DataApiDb` (prod) and `PsycopgDb` (tests/local).
**Alternatives:** psycopg in VPC + RDS Proxy (≈ $90/mo proxy minimum at Serverless v2, NAT or VPC endpoints, ENI cold starts); psycopg without proxy (connection storms).
**Consequences:** + no VPC/NAT, simple scaling. − writer-only; no array parameters; 1 MiB response / 64 KB row / 45 s statement limits; +30–60 ms per call. **Rules** (AR-3/4/5): hot paths ≤ 2 calls, every mutation is one writable-CTE statement, sets passed as JSON text, list projections sized (03 §3.9). Enforced by `StrictDataApiFake` in every PR and an emulator job (10 §10.3). **Gate**: Spike S-1 in Milestone 0 measures real latency; fallback RDS Proxy + psycopg behind the same port (no domain changes).

## ADR-003 REST on API Gateway HTTP API, one `api` Lambdalith (+ `forms-public`)
**Revision (AR-25):** bounded contexts are packages inside one `api` function, not separate functions — fewer cold starts at 100–500 users.
**Alternatives:** AppSync GraphQL (subscriptions built in, but per-subscriber payload shaping for D-018 and row visibility is awkward; resolvers in VTL/JS or Lambda anyway); one Lambda per route (hundreds of functions, cold starts).
**Consequences:** 2 API Lambdas, OpenAPI-generated typed client, Powertools routing; cold-start mitigation per ADR-012.

## ADR-004 Transactional outbox → EventBridge → SQS
**Decision:** events written in the same transaction as state; published after commit with sweeper fallback; consumers idempotent; dispatchers re-enqueue to FIFO where ordering matters.
**Alternatives:** publish directly after commit (lost events on crash); Postgres logical replication/DMS (heavy, not serverless-friendly); DynamoDB Streams (state not in DynamoDB).
**Consequences:** at-least-once delivery everywhere; a sweeper every minute bounds worst-case delay at ~60 s for rare failures only.

## ADR-005 API Gateway WebSocket + DynamoDB registry + fan-out Lambda
**Alternatives:** AppSync Events (managed channels; no per-connection payload tailoring for D-018/D-020 without publishing per-user channels); IoT Core (MQTT, extra auth complexity).
**Consequences:** full control over per-subscriber filtering and revocation; we own reconnection/gap handling (05 §5.3).

## ADR-006 Automation engine on SQS FIFO with Postgres run state
**Alternatives:** Step Functions per run (≈ $25 per million state transitions; heavier; still need idempotency), EventBridge Pipes.
**Consequences:** per (automation, item) ordering, step-level resume and idempotency (G1.8, G1.13), cheap at 50 runs/s. Multi-step branching workflows (G8, P3) may later move to Step Functions.

## ADR-007 Search in PostgreSQL (FTS + pg_trgm)
**Alternatives:** OpenSearch Serverless (cost floor), Algolia (external SaaS, data residency).
**Consequences:** good enough relevance at ≤ 1M docs; same permission predicates as views; revisit if A7 targets fail.

## ADR-008 Application-level authorization, identity-only JWTs
**Decision:** Cognito authenticates; authorization is a pure policy module over a DB snapshot cached ≤ 30 s, invalidated by `perm_epoch`.
**Alternatives:** Amazon Verified Permissions (Cedar) — strong fit for RBAC/ABAC, but row-level and mirror visibility still need SQL predicates, adds latency and cost per check; claims in JWT — violates F7.7.
**Consequences:** one helper used by API, workers, fan-out, search, dashboards; generated permission matrix tests.

## ADR-009 Materialized computed values with per-viewer fallback
**Decision:** `items.computed` maintained by ordered recompute worker; served only to full-visibility viewers; per-viewer SQL/Python path otherwise (D-015).
**Consequences:** fast common path; slower path bounded to partial-visibility viewers; eventual consistency ≤ 5 s signalled by `computed_pending`.

## ADR-010 SPA: React + TS + Vite on S3/CloudFront
**Alternatives:** Next.js SSR (no SEO need; adds server runtime); Amplify Hosting (fine, but CloudFront+S3 keeps everything in CDK with WAF).

## ADR-011 Single region, three stages via CDK + GitHub Actions OIDC
**Consequences:** DR by backups to a second region (RTO ≤ 4 h), not active-active.

## ADR-012 Python 3.13 arm64 Lambdas; cold-start mitigation decided by measurement
**Decision (revised AR-25):** slim packages first; if `api` p95 misses NFR-P1, enable **either** SnapStart (Python: billed snapshot cache + restores; not combinable with provisioned concurrency; prune old versions) **or** provisioned concurrency 1–2, chosen in Milestone 0.
**Consequences:** Graviton cost savings; any init-time randomness (ticket secrets, uuid seeds) must be re-seeded after restore if SnapStart is chosen.

## ADR-013 Auth proxy in front of Cognito (AR-1, AR-8, AR-9)
**Context:** K7.1 needs per (account, IP) lockout; Cognito's built-in lockout is per user, the pre-auth trigger has no trustworthy IP, no trigger sees failed passwords or new passwords.
**Decision:** all sign-in and password flows go through `/api/auth/*` calling Cognito Admin APIs with ContextData; per (email, viewer IP) counters in DynamoDB; breached-password Bloom filter; refresh token in HttpOnly cookie; `tokens_valid_after` revocation; WebSocket single-use tickets.
**Alternatives:** Cognito Plus (compromised-credential detection on reset/change, not SRP sign-in; still per-user lockout) — rejected for K7.1; a custom IdP — far more code.
**Consequences:** the SPA has no Cognito SDK; the auth endpoints become a security-critical module with its own test suite (lockout, MFA setup, reset revocation).

## ADR-014 Single visibility query builder (AR-16)
**Decision:** every row-returning query is built from `VisibleItems(user)` CTE + link masking + computed policy per the table in 07 §7.2a; endpoint and event tests are generated from that table.
**Consequences:** one place to reason about D-012/D-015/D-018/D-020; slightly more complex SQL on every read.

## ADR-015 Board change log for client sync (AR-18)
**Decision:** `tl.board_changes` (bigserial seq) written in each mutation statement; clients resync with `since_seq` and a 200-entry overlap; 24 h retention.
**Alternatives:** timestamp-based `since` (misses late commits), logical replication (not serverless-friendly).

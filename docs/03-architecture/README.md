# Tasklane — Architecture & Design

**Version:** 1.0 — ready for planning (architect AR-1…33, council SEC/PERF/OPS/DX, final pass FR-1…12 applied; see review-log.md) · **Inputs:** requirements v1.0 (`../02-requirements`), decisions D-001…D-020 (`../00-decision-log.md`)

## 1. Architecture drivers
| Driver | Source | Consequence |
|---|---|---|
| Dynamic schema per board (≤ 200 typed columns) with arbitrary filter / sort / group-by / aggregation | B, C, D2, H | Needs a query engine that handles ad-hoc predicates and aggregates over ≤ 100k rows per board → relational store with JSONB, not a key-value store |
| Cross-item relations, mirrors (2 hops), formulas, materialization, per-viewer visibility | C17–C19, D-012, D-015 | Joins + transactional writes of link + reflection (C18.1) |
| Row-level visibility on Activities (D-016/D-020) | K3.5 | Visibility must be a query predicate on every read path |
| Real-time ≤ 2 s, per-subscriber filtering of payloads | F7, D-018 | Server-controlled fan-out, not a dumb broadcast |
| Automations: async, per-(automation,item) serialization, idempotent steps, ≤ 5 s | G1 | Ordered queues + durable run state |
| Scale: ≤ 500 users, ≤ 1M items, ≤ 50 runs/s | D-007 | Single regional database is ample; no sharding |
| Serverless-first unless it complicates (user) | D-003 | Lambda, API Gateway, Aurora Serverless v2, SQS, EventBridge, S3, CloudFront, Cognito, SES |
| Cost target ≈ US$150/month at 100 active users | README north star | Avoid always-on premium services (OpenSearch Serverless, NAT gateways, RDS Proxy minimums). Revised estimate ≈ $185 lean (10 §10.4) — user decision |
| Python backend, React/TS SPA, CDK Python | D-003 | |

## 2. Key decisions (full ADRs in `adr.md`)
| ADR | Decision |
|---|---|
| ADR-001 | **Aurora PostgreSQL Serverless v2** is the system of record (JSONB column values + relational relations), not DynamoDB |
| ADR-002 | Lambdas reach Aurora through the **RDS Data API** (no VPC, no NAT, no RDS Proxy); single-statement writes, ≤ 2 calls on hot paths; gated by Spike S-1 |
| ADR-003 | **REST/JSON API on API Gateway HTTP API**, OpenAPI-described, one `api` Lambdalith with bounded-context packages (+ `forms-public`) |
| ADR-004 | **Transactional outbox** in Postgres → EventBridge bus → SQS queues per consumer |
| ADR-005 | **API Gateway WebSocket API** + DynamoDB connection registry + fan-out Lambda for real-time and presence |
| ADR-006 | **Automation engine** on SQS FIFO (group = automation × item) with step-level idempotency in Postgres; EventBridge Scheduler for time triggers |
| ADR-007 | **Search** with PostgreSQL full-text + `pg_trgm` (no OpenSearch) |
| ADR-008 | **Authorization** in the application (policy module over Postgres), identity-only JWTs from **Cognito**, 30 s permission cache |
| ADR-009 | **Computed values** (formula, mirror) materialized by an ordered recompute worker; per-viewer path for partial visibility |
| ADR-010 | **SPA** React + TypeScript + Vite, TanStack Query/Virtual, served by S3 + CloudFront + WAF |
| ADR-011 | **Single AWS region**, three accounts/stages (dev, staging, prod) deployed by CDK Pipelines-style GitHub Actions with OIDC |
| ADR-012 | Python 3.13 on arm64; cold-start mitigation (SnapStart **or** provisioned concurrency) chosen by measurement |
| ADR-013 | **Auth proxy** in front of Cognito (per account+IP lockout, MFA setup, breached passwords, revocation, WS tickets) |
| ADR-014 | **Single visibility query builder** for every read path |
| ADR-015 | **Board change log** (`board_changes` seq) for real-time gap sync |

## 3. Document map
| File | Content |
|---|---|
| `01-context-containers.md` | C4 system context and container views, bounded contexts |
| `02-deployment.md` | **Deployment diagram**, AWS resources per stage, network, environments |
| `03-data-model.md` | Postgres schema, column value encoding, indexes, versioning, outbox |
| `04-api.md` | REST resources, conventions, concurrency, errors, pagination |
| `05-events-realtime.md` | Event catalog, outbox flow, WebSocket protocol, presence, per-subscriber filtering |
| `06-automations.md` | Automation engine design, triggers, runs, scheduling |
| `07-security-permissions.md` | Auth, permission model & evaluation, row-level visibility, threat model |
| `08-query-search-dashboards.md` | View query compiler, computed values, search, dashboards |
| `09-frontend.md` | SPA architecture, state, optimistic updates, virtualization |
| `10-operations-cost.md` | Observability, SLOs, backup/DR, CI/CD, cost model |
| `11-repo-structure.md` | Monorepo layout and module boundaries |
| `adr.md` | Architecture Decision Records |
| `coverage.md` | Requirements/NFR/decision → design traceability |
| `review-log.md` | Architecture agent + council findings and resolutions |

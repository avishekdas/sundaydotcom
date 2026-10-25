# 11 — API, Clients & Non-functional Requirements (Areas M, O, NFR)

## M1 API — P1 (internal, used by the SPA), P2 (documented public API + tokens)
- M1.1 Every UI capability is available through the same authenticated API (no UI-only backdoors); the SPA is just a client.
- M1.2 Style is decided in Step 3 (REST vs GraphQL); requirements: cursor pagination, field-level validation errors, idempotency keys on create endpoints, concurrency per D-010 (cell writes LWW with returned per-item `version`; multi-value cells as add/remove deltas; structural writes with `If-Match` version → 409 when stale), consistent error envelope.
- AC-M1-1 Given a create-item request retried with the same idempotency key, then exactly one item exists and both responses return the same item ID.
- AC-M1-2 Given two owners save the same view settings from version 7, then the first succeeds (version 8) and the second gets 409 with the current version.
- AC-M1-3 Given every action available in the SPA, then the e2e suite performs it through the public API client used by the SPA (no private endpoints).
- M1.3 Rate limits per user: 1,000 req/min burst, 10 req/s sustained per endpoint group (tunable); 429 with Retry-After.
- M1.4 Public API docs (OpenAPI or GraphQL SDL) generated from code — P2.

## M2 Outbound webhooks — P2
Per board subscriptions (item created, column changed, status changed, item deleted), HMAC-signed, retries with backoff, delivery log.

## M3, M4 — OUT

## O — Clients
- O1 Responsive web SPA; supported: latest 2 versions of Chrome, Edge, Firefox, Safari; min width 1024 px full experience, 768 px usable (tablet), < 768 px read + simple edits (P2 polish).
- O3 Keyboard shortcuts (P2): ⌘K search (P1), navigation and editing shortcuts.
- O4 Dark theme (P2). O5 English only, i18n-ready strings (P1). O6 WCAG 2.1 AA (P2; P1: semantic HTML, keyboard reachable core flows, color contrast ≥ 4.5:1 for text).
- O2 Native mobile — OUT.
- AC-O1-1 Given a 768 px wide viewport, then the north-star scenario steps 3–5 can be completed (Playwright run at 768×1024).
- AC-O5-1 Given the built SPA, then no user-visible string is hard-coded outside the i18n catalog (lint rule passes).

## NFR — Non-functional requirements (P1 unless stated)

### Performance (see README north-star metrics)
| ID | Requirement |
|---|---|
| NFR-P1 | API p95 ≤ 300 ms for single-item reads/writes; ≤ 800 ms for first page (≤ 500 items) of a board view with filters |
| NFR-P2 | Board table first meaningful paint ≤ 2.5 s p95 at 5,000 items; ≤ 4 s at 20,000 items |
| NFR-P3 | Real-time fan-out ≤ 2 s p95; automation execution ≤ 5 s p95; search index freshness ≤ 5 s p95; mirror/formula recompute ≤ 5 s p95 |
| NFR-P4 | Dashboard with 8 widgets over 20,000 items renders ≤ 3 s p95 |
| NFR-P5 | Cold start must not push p95 over targets (mitigation chosen in Step 3) |

### Scale (D-007)
≤ 500 users (≤ 500 concurrent connections, ≤ 100 on one board), ≤ 1,000,000 items total, ≤ 100,000 per board, ≤ 200 columns per board, ≤ 5,000 boards, ≤ 2 TB files, ≤ 50 automation runs/s burst.

### Availability & resilience
| ID | Requirement |
|---|---|
| NFR-A1 | 99.9% monthly availability of API and SPA |
| NFR-A2 | RPO ≤ 5 min (point-in-time recovery), RTO ≤ 4 h (single region); backups retained 35 days; restore drill each release |
| NFR-A3 | Graceful degradation: if real-time or search is down, core CRUD still works (fallback to polling / DB filtering on small boards) |
| NFR-A4 | Automation and import jobs are durable (survive function failures) with dead-letter handling and replay |

### Security & privacy
| ID | Requirement |
|---|---|
| NFR-S1 | All traffic TLS 1.2+; data encrypted at rest with KMS keys |
| NFR-S2 | Server-side authorization on every request (K3.2); deny by default; automated permission matrix tests (AC-K3-4) |
| NFR-S3 | OWASP ASVS L2 controls for web/API; WAF with managed rule sets on public endpoints; strict CSP; no secrets in client |
| NFR-S4 | Files: signed URLs ≤ 15 min, content-type sniffing, executable types blocked (P1), malware scan (P2) |
| NFR-S5 | Tenant of one, but least-privilege IAM per function; secrets in AWS Secrets Manager/SSM; no long-lived AWS keys |
| NFR-S6 | Audit trail of admin and security events (K9 P2; P1 writes the events even before the UI exists) |
| NFR-S7 | PII handling: user and CRM contact data exportable and deletable on request (GDPR-style "erase person" admin tool — P2) |

### Observability & operations
| ID | Requirement |
|---|---|
| NFR-O1 | Structured JSON logs with correlation id across API → queue → automation → real-time |
| NFR-O2 | Metrics & alarms on latency SLOs, error rates, queue age, DLQ depth, WebSocket connection errors |
| NFR-O3 | Distributed tracing on all backend paths |
| NFR-O4 | Infrastructure 100% as code (CDK Python), environments dev / staging / prod, one-command deploy, preview stacks per branch (P2) |
| NFR-O5 | Cost: monthly cost report per stage; budget alarm |

### Quality
| ID | Requirement |
|---|---|
| NFR-Q1 | TDD: every AC in these documents maps to ≥ 1 automated test (unit, integration, or e2e); traceability table maintained |
| NFR-Q2 | Backend unit coverage ≥ 90% lines on domain logic; frontend component tests on all column editors and views |
| NFR-Q3 | E2E north-star scenario runs on every merge to main against a deployed staging stack |
| NFR-Q4 | Load test at each milestone end for the NFR-P targets relevant to delivered features |

### Data portability
- NFR-D1 Full account export (all boards as CSV/JSON + files) for Admins — P2.
- NFR-D2 Import from a monday.com board export (XLSX) — P2 (uses A13 pipeline).

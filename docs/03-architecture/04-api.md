# 04 — API Design

## 4.1 Style & conventions (ADR-003)
- REST/JSON over HTTPS, base `/api/v1`, OpenAPI 3.1 generated from Pydantic v2 models (Powertools `APIGatewayHttpResolver` + `enable_validation`), published as an artifact and used to generate the SPA's typed client (`openapi-typescript` + `openapi-fetch`). Same client is used by e2e tests (AC-M1-3).
- Auth: sign-in and password flows go through the **auth proxy** `/api/auth/*` (07 §7.1). Other calls: `Authorization: Bearer <Cognito access token>`; HTTP API JWT authorizer validates signature/expiry; the app resolves user, permissions and `tokens_valid_after` from the DB (identity-only tokens, F7.7).
- IDs are strings in JSON (bigints exceed JS safe integer range eventually).
- **Idempotency**: `Idempotency-Key` header required on POST that creates resources; stored 24 h with request hash; replay returns the stored response (AC-M1-1).
- **Concurrency**: cell writes return `{version}`; structural PUT/PATCH require `If-Match: <version>` → 409 `version_conflict` with current representation.
- **Pagination**: lists use cursor-based `?cursor=&limit=` (≤ 500, keyset). Board queries return the ordered id list + group counts and hydrate rows via `items:fetch` (09 §9.3b).
- **Query DSL**: one `QuerySpec` model (03 §3.4a) used by views, widgets, automation conditions, kanban and exports.
- **Mutations** accept an optional client `mutation_id` echoed in events.
- **Errors**: `{"error": {"code": "validation_error", "message": "...", "fields": {"values.lead_email": "Invalid email"}, "request_id": "..."}}`. Codes: `validation_error` 400, `unauthenticated` 401, `forbidden` 403, `not_found` 404 (also used for no-access to avoid existence leaks), `version_conflict` 409, `limit_reached` 409, `gone` 410, `rate_limited` 429.
- **Rate limits** (M1.3): per user token bucket in DynamoDB counters (1,000/min burst, 10 rps per route group) → 429 + `Retry-After`.

## 4.2 Resource map (P1)
| Area | Endpoints (abridged) | Package (all served by `api` λ except public forms) |
|---|---|---|
| Auth proxy | `POST /auth/sign-in`, `/auth/challenge`, `/auth/refresh`, `/auth/forgot`, `/auth/reset`, `/auth/accept-invite`, `/auth/sign-out` | identity (no JWT authorizer) |
| Realtime | `POST /realtime/ticket` → `{ticket, url}` (single use, 30 s) | collab |
| Session | `GET /me`, `PATCH /me`, `GET /me/permissions?board_ids=` | identity |
| Account/admin | `GET/PATCH /account`, `GET/POST /users` (invite), `PATCH /users/{id}` (role, status, reassignment payload F1.5), `POST /users/{id}/resend-invite` | identity |
| Workspaces | `GET/POST /workspaces`, `GET/PATCH/DELETE /workspaces/{id}`, `/workspaces/{id}/members`, `GET /nav` (tree for left nav, A4) | workmgmt |
| Boards | `POST /boards`, `GET/PATCH/DELETE /boards/{id}`, `POST /boards/{id}/archive|restore|move`, `/boards/{id}/members`, `GET /boards/{id}/schema` (columns, groups, views, permissions for caller) | workmgmt |
| Groups | `POST /boards/{id}/groups`, `PATCH/DELETE /groups/{id}`, `POST /groups/{id}/duplicate|archive|restore` | workmgmt |
| Columns | `POST /boards/{id}/columns`, `PATCH/DELETE /boards/{id}/columns/{colId}`, `POST …/duplicate`, `POST …/convert` (C40.3, with `dry_run`) | workmgmt |
| Items | `POST /boards/{id}/items`, `GET /items/{id}`, `PATCH /items/{id}` (name, group, position), `PATCH /items/{id}/values` (map of col → value \| `{op:"add"/"remove", …}`), `POST /items/{id}/move|duplicate|archive|restore`, `DELETE /items/{id}`, `POST /boards/{id}/items:bulk` (B9) | workmgmt |
| Links | `POST /items/{id}/links/{colId}` `{add:[ids], remove:[ids]}`, `GET /items/{id}/links/{colId}` | workmgmt |
| Views & queries | `POST/PATCH/DELETE /boards/{id}/views/{viewId}`, **`POST /boards/{id}/query`** (filter/sort/group/search/columns → paged rows + group summaries + counts; see 08), **`POST /boards/{id}/changes`** `{since_xmin}` → changed item ids/kinds (gap sync, 03 §3.3a), **`POST /boards/{id}/items:fetch`** `{ids ≤ 200, columns}` (batched hydration, visibility-filtered), `POST /boards/{id}/columns:preview-formula`, `POST /formula:validate` (tokens + errors for editor autocomplete). `GET /schema` and `POST /query` return `as_of_xmin` | workmgmt |
| Kanban | `POST /views/{id}/lanes:query`, `PUT /views/{id}/positions` | workmgmt |
| Updates | `GET/POST /items/{id}/updates`, `PATCH/DELETE /updates/{id}`, `POST/DELETE /updates/{id}/like`, `POST /updates/{id}/pin` | collab |
| Files | `POST /files:presign` (purpose, size, mime) → **presigned POST** with `content-length-range`; `POST /files/{id}:complete` (HEAD + magic-byte sniff); `GET /files/{id}/url` (signed GET 15 min on files domain) | collab |
| Subscriptions & notifications | `PUT/DELETE /items/{id}/subscription`, `GET /notifications?cursor`, `POST /notifications:read`, `GET/PATCH /me/notification-settings`, `PUT /boards/{id}/mute` | collab |
| Activity log | `GET /boards/{id}/activity`, `GET /items/{id}/activity` | collab |
| Automations | `GET /automation-catalog`, `GET/POST /boards/{id}/automations`, `PATCH/DELETE /automations/{id}`, `GET /automations/{id}/runs`, `GET /boards/{id}/automation-runs` | automation |
| Dashboards | `GET/POST /workspaces/{id}/dashboards`, `GET/PATCH/DELETE /dashboards/{id}`, `/dashboards/{id}/widgets`, **`POST /dashboards/{id}/data`** (computes all widgets for caller with dashboard filters) | insights |
| Search | `GET /search?q=&types=` | insights |
| Import/Export | `POST /boards/{id}/imports` (presigned upload, mapping) → job, `POST /boards/{id}/exports` → job, `GET /jobs/{id}` | insights (async work in job-worker λ) |
| CRM | `POST /templates/crm:apply` → job, `GET /items/{id}/timeline?cursor&types&q`, `POST /items/{id}/activities`, `PATCH/DELETE /activities/{id}` | crm |
| Trash/Archive | `GET /trash`, `POST /trash/{type}/{id}:restore`, `DELETE /trash/{type}/{id}` (admin purge) | workmgmt |
| Public forms | `GET /forms/{token}` (definition), `POST /forms/{token}/uploads` (slot, counted per IP), `POST /forms/{token}/submissions` (body includes client `submission_id` for idempotency; may return `challenge_required`) | forms-public (no JWT, WAF-protected) |

## 4.3 Example: cell write
```http
PATCH /api/v1/items/90210/values
{"values": {"deal_stage": {"l": 1},
            "deal_owner": {"op": "add", "p": [{"t":"u","id":"42"}]}}}
→ 200 {"id":"90210","version":57,"values":{…changed keys…},"computed_pending":true}
```
`computed_pending` tells the client that dependent mirrors/formulas will arrive via real-time.

## 4.4 Domain service layer
Every endpoint is a thin adapter: parse → `authz.require(...)` → call a domain service (`workmgmt.items.set_values(ctx, item_id, changes)`) → map result. Automations, forms, imports and the CRM template call the **same services** with a different `Actor` (user / automation(owner) / form / import / system). This is how "no UI-only backdoor" (M1.1) and "automations act as owner" (G1.5) are guaranteed by construction.

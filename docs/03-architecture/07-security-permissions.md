# 07 — Security & Permissions (ADR-008)

## 7.1 Authentication (K7) — revised after AR-1, AR-8, AR-9
**Auth proxy (ADR-013).** The SPA never talks to Cognito directly for sign-in or password flows. A small `auth` route group in the API Lambda (`/api/auth/*`, outside the JWT authorizer) calls Cognito Admin APIs:
| Endpoint | Cognito call | Extra logic |
|---|---|---|
| `POST /auth/sign-in` {email, password} | `AdminInitiateAuth` (ADMIN_USER_PASSWORD_AUTH) with `ContextData` | **per (email, viewer-IP) counter** in DynamoDB checked *before* calling Cognito: attempt 6 within 15 min → 429 without touching Cognito, so Cognito's own per-user counter is never driven up by one IP and IP B still succeeds (AC-K7-2). Failures recorded from `NotAuthorizedException`. Viewer IP from `CloudFront-Viewer-Address` (trusted only with the origin secret header, §7.4) |
| `POST /auth/challenge` {session, type, answer} | `AdminRespondToAuthChallenge` | handles `MFA_SETUP` (returns `AssociateSoftwareToken` secret via session), `SOFTWARE_TOKEN_MFA`, `NEW_PASSWORD_REQUIRED` |
| `POST /auth/refresh` | `AdminInitiateAuth` REFRESH_TOKEN_AUTH | refresh token kept in an `HttpOnly; Secure; SameSite=Strict` cookie scoped to `/api/auth`; access token returned in body, held in memory by the SPA |
| `POST /auth/forgot`, `POST /auth/reset` | `ForgotPassword` / `ConfirmForgotPassword` (via app client with secret) | breached-password check (below) before calling Cognito; on success `AdminUserGlobalSignOut` + bump `users.tokens_valid_after` |
| `POST /auth/accept-invite` | `AdminRespondToAuthChallenge` NEW_PASSWORD_REQUIRED | breached-password check |
| `POST /auth/sign-out` | `GlobalSignOut` / revoke | clears cookie |
- **Brute force & Cognito interplay (SEC-4)**: besides the per (email, IP) limit, a **per-account** counter: ≥ 10 failures in 15 min from any IPs → the proxy requires a solved WAF CAPTCHA token for further sign-ins to that account and raises a Sev2 alert. This keeps Cognito's own per-user lockout (2^(n−5) s after 5 failures, max ≈ 15 min) to short delays: with the proxy caps, Cognito's lock never exceeds ≈ 32 s, and the proxy retries a correct-password attempt from another IP once after the indicated delay — AC-K7-2 holds with "succeeds within 35 s". *(Acceptance tolerance documented for the PO.)*
- **No enumeration / email bombing (SEC-5)**: all auth failures map to one generic 401 with constant-time padding (dummy work for unknown users); `/auth/forgot` always returns 202 and is limited to 3/email/hour and 10/IP/hour; `/auth/challenge` (MFA codes) limited to 5 attempts per session and 20/IP/hour; `/auth/refresh` 60/IP/min.
- **Viewer IP (SEC-6)**: `CloudFront-Viewer-Address` is `ip:port` (`[v6]:port` for IPv6); parsed with port stripped; counters keyed by IPv4 /32 and IPv6 /64; unit tests with real header samples.
- **MFA**: user pool MFA = **ON (TOTP)** → Cognito itself returns `MFA_SETUP` with a session for first-time enrollment (AC-K7-1, K7.6). The account toggle `require_mfa` calls `SetUserPoolMfaConfig` (ON ↔ OPTIONAL); default ON.
- **Breached passwords**: a top-10M breached-password Bloom filter (~18 MB at 1 % FP) stored in S3, loaded once per Lambda instance, checked by the auth proxy on every password-setting flow. (Alternative recorded in ADR-013: Cognito Plus compromised-credentials detection.)
- **Revocation (AR-9, SEC-16)**: on reset, deactivation and sign-out-everywhere the proxy (1) calls `AdminUserGlobalSignOut` (and `AdminDisableUser` on deactivation) to revoke refresh tokens, (2) sets `users.tokens_valid_after = date_trunc('second', now())` (token `iat` has 1-second resolution; tokens are rejected if `iat < tokens_valid_after`, FR-11), (3) bumps `account.perm_epoch` and emits `permission.changed` for that user. The authz snapshot rejects tokens with `iat < tokens_valid_after` on HTTP and fan-out within ≤ 30 s (one bound for all paths; F7.7, AC-K7-3, AC-F1-2). Refresh-token rotation enabled. Admin action "Reset MFA" (audited) forces re-enrollment for lost devices.
- **WebSocket auth (AR-9)**: no token in the URL. The SPA calls `POST /realtime/ticket` (JWT-protected) → single-use ticket (32 random bytes, 30 s TTL, stored in DynamoDB with user id); `$connect` authorizer consumes it (conditional delete).
- Bootstrap admin from CDK context, created by a custom resource; first sign-in forces new password + MFA setup.
- Google SSO (P2): Cognito federation; the auth proxy exchanges the authorization code server-side.
- Tokens carry **identity only** (`sub`, `iat`); no role/permission claims (F7.7).

## 7.2 Authorization model
Effective permission for (user, board):
```
if user.status != active                               → none
role = user.role (admin|member|viewer)
if role == admin                                      → owner-equivalent (audited, K1.1)
board_access = explicit board member (user)           → yes   (K2.1: regardless of workspace)
            or (board.kind == main and workspace visible to user)   # open ws or ws member
            else no                                    → none (404)
is_owner = board_members.role == owner
caps = OWNER_CAPS if is_owner else PERMISSION_SET_CAPS[board.permission_set]
caps = caps ∩ ROLE_CEILING[role]                       # viewer: comment + log-own-activity only
for subitem boards: evaluate on parent board (B7.7)
for edit_assigned: item-level check on assign column of item OR parent (B7.7)
```
- Implemented in `identity.authz` as pure functions over a `PermissionSnapshot` (user, role, status, tokens_valid_after, memberships, visible board ids, board facts). The snapshot is loaded with **one SQL statement** and cached in Lambda memory for at most **30 s**. Lambdas do not receive events (AR-12), so freshness is guaranteed by TTL alone plus a cheap check: every permission-relevant change increments a single global counter `tl.account.perm_epoch`; the cache entry is reused only while its epoch equals the epoch returned piggy-backed on the request's first SQL statement (no extra round trip). Worst case propagation ≤ 30 s (F7.7). Accepted cost (FR-12): any permission change (incl. a sign-out-everywhere) invalidates all cached snapshots — at ≤ 500 users this is a few hundred extra single-statement loads at most.
- The capability matrix (requirements K1/K3 tables) is encoded as data and drives a **generated test matrix** (every endpoint × role × permission set → expected allow/deny, AC-K3-4).
- Visibility helpers used by every read path: `visible_board_ids(user)` and `item_visibility_predicate(user)`. **Data API has no array parameters (AR-4)**: sets are passed as JSON text and expanded in SQL, a rule enforced by the `Db` port (the strict fake adapter rejects native arrays). For `row_visibility='related'` boards (Activities, D-016/D-020):
```sql
with vb as (select jsonb_array_elements_text(:visible_boards::jsonb)::bigint as id)
... and exists (select 1 from tl.item_links l join tl.items t on t.id = l.to_item_id
        where l.from_item_id = i.id and l.column_id = 'related_item'
          and t.state = 'active' and t.board_id in (select id from vb))
```
  The query compiler (08) always appends this predicate for such boards; search, export, counts, widgets, fan-out reuse the same helper (AC-K3-5).
- Mirror/formula visibility (D-012/D-015): `full_visibility(user, item, column)` = all contributing boards ⊆ visible boards → serve materialized value; else compute per viewer (08 §8.3).

### 7.2a Visibility rule table (AR-16) — every row-returning path
All row-returning SQL is built by one `VisibleItems(user)` CTE builder (board visibility ∧ row visibility ∧ state). Tests are generated from this table (like AC-K3-4).
| Path | Board visibility | Row visibility (D-020) | Hidden linked items (C18.2) | Computed values (D-015) |
|---|---|---|---|---|
| `POST /boards/{id}/query`, kanban lanes, counts, summaries | ✔ | ✔ | chips masked "Hidden item" | per-viewer if partial |
| `GET /items/{id}`, item page, `GET /items/{id}/links/{col}` | ✔ (404) | ✔ (404) | masked | per-viewer if partial |
| `GET /items/{id}/timeline` (L10) | source item ✔ | each activity ✔ | masked | — |
| `GET /boards/{id}/activity`, `/items/{id}/activity` | ✔ | ✔ per entry's item | before/after Connect values masked; mirror/formula entries omitted for partial viewers | — |
| `GET /search` | ✔ | ✔ | — | — |
| `POST /boards/{id}/exports` (job runs as requester) | ✔ | ✔ | masked | per-viewer |
| `POST /dashboards/{id}/data` | ✔ (hidden boards counted) | ✔ | — | per-viewer |
| Mirrors/C38 whose contributors are on a row-visibility board (Activities) | ✔ | ✔ per contributor (join path, never per-board fold) — FR-4 | — | per-viewer always |
| `GET /files/{id}/url` | file's item visible | ✔ | — | — |
| `POST /boards/{id}/changes` (sync) | ✔ | ✔ | masked | invalidations only |
| Real-time events (05) | ✔ at subscribe + epoch | ✔ per event (one SQL per event: visible subscriber ids) | link events masked per recipient | values only to full-visibility (D-018) |
| Notifications (A9.5, D-019) | ✔ | ✔ | — | rendered per recipient; email sender re-checks visibility at send time (SEC-20) |
| **Write references** (SEC-2): link targets, activity Related items, people, file ids, dashboard/widget board ids, automation target boards | every referenced id must pass `VisibleItems(actor)` / file binding (03 §3.5); failure → 404 for the whole request | ✔ | — | — |
| **WebSocket channels** (SEC-13) | `board`, `dashboard` visible; `item` incl. row visibility; `user` = caller; presence only on visible boards as self; unknown → deny | ✔ | — | — |
| Job results (exports/imports) (SEC-9) | `jobs.created_by = caller` (or audited Admin) | — | — | — |
| Search fallback (`ilike`) | ✔ | ✔ | — | — |

## 7.3 Data protection
- TLS everywhere (CloudFront TLS 1.2+, API GW, Data API). KMS CMKs for Aurora, S3, DynamoDB, SQS, logs.
- S3 files: block public access, objects keyed `files/<yyyy>/<uuid>` (no user-controlled names in keys), **presigned POST with `content-length-range`** and fixed `Content-Type` (AR-30); at `:complete` the service HEADs the object and sniffs the first 4 KB against an allow-list (magic bytes), rejecting executables and mismatches (C21.2, NFR-S4); GET URLs signed 15 min after authz and served from a **separate files domain** (`files.<domain>` CloudFront distribution, no cookies); `Content-Disposition: attachment` for everything except raster images and PDF (SVG/HTML always attachment); malware scan via GuardDuty Malware Protection for S3 (P2).
- XSS: rich text stored as structured JSON (ProseMirror doc), rendered via whitelisted node types; plain-text fields escaped by React; strict CSP (no inline scripts, `connect-src` own domains), `frame-ancestors 'none'`.
- Link column: only http/https (AC-C12-1); `rel="noopener noreferrer"`.
- SQL: only parameterized statements; the view query compiler builds SQL from whitelisted column ids/operators (column id must exist in board schema; value passed as parameter).
- Secrets: DB credentials in Secrets Manager (rotation 30 d); no secrets in the SPA.
- **Least privilege (SEC-11, NFR-S5)**: the auth proxy is a separate **`auth` λ** whose role alone holds the Cognito Admin actions it uses, scoped to the pool ARN. Postgres roles per function class, each with its own secret and `rds-data`/`secretsmanager:GetSecretValue` scoped to that secret: `api_rw` (DML on app tables, no DDL), `worker_forms` (INSERT/UPDATE grants only on the tables the item-create mutation touches: items, item_links, item_text, files binding, activity_log, board_changes, outbox, recompute_pending; SELECT on schema tables) — form submissions go through the **same Python domain service** as every other actor (FR-5), `reader` (SELECT only; search, dashboards, compiled formula queries), `worker_*` (table-scoped grants per worker), `audit_writer` (INSERT only on `audit_events`, append-only), `migrator` (DDL, used only by `migrate` λ). cdk-nag + IAM Access Analyzer policy validation in CI.
- **Logs & errors (SEC-14)**: credential fields use `SecretStr`; the error mapper never echoes input values; Powertools `log_event=False`; a redaction filter removes `authorization`, `cookie`, `x-tl-*`, `x-amzn-waf-*`, `password`, `code`, `secret`, `token` keys; CloudWatch Logs data-protection policies on all log groups; a test asserts no secrets in captured logs.
- **Rich text & email (SEC-17)**: ProseMirror JSON validated on the **write** path (node/mark allow-list, `href` limited to http/https/mailto); email templates HTML-escape all user content; response-headers policy (HSTS, `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`) on both CloudFront distributions.
- **File downloads (SEC-18)**: CloudFront **signed URLs** with a key group (private key in Secrets Manager, rotated); S3 reachable only through OAC; `response-content-type` set from the sniffed MIME + `nosniff`.
- **CSV/XLSX (SEC-9)**: exports escape cells starting with `= + - @ \t \r` by prefixing `'`; job outputs downloadable only by the creator via short-lived signed URL; imports parsed with defusedxml-backed openpyxl, zip-bomb / row / cell caps, in `job-worker` under its own role.
- Audit store (`tl.audit_events`) receives security events from P1 (A15.5).

## 7.4 Edge protection (revised after AR-6, AR-7)
- **WAF on CloudFront only** (WAF cannot attach to HTTP or WebSocket APIs). The HTTP API's default `execute-api` endpoint is **disabled**; CloudFront reaches it through a custom domain origin and adds a secret header `x-tl-origin: <secret from Secrets Manager, rotated>`; a middleware rejects requests without it (403). Origin request policy `AllViewerExceptHostHeader`, caching disabled for `/api/*` (forwards `Authorization`, cookies, `CloudFront-Viewer-Address`).
- WAF rules: AWS Managed Rules (Common, KnownBadInputs, AmazonIpReputation), rate-based rule per IP on `/api/*` (2,000 / 5 min), body size constraints, and for `/forms/*` the Challenge integration below.
- **Public form defenses (I7.1), authoritative in the app**: per (form, viewer IP) counters in DynamoDB (minute and day windows). Submissions 1–5/min pass; 6–10/min require proof of a solved WAF challenge; 11+/min → 429; > 100/day → 429. Challenge mechanics (SEC-7): the public form bundle includes the **AWS WAF JavaScript integration SDK**; a WAF rule matching the label `awswaf:managed:token:accepted` on `/forms/*` inserts a custom header — WAF prefixes it, so the Lambda checks **`x-amzn-waf-tl-chal`** whose value is a secret rotated with the origin secret; a **CloudFront Function strips any viewer-supplied `x-amzn-waf-*` and `x-tl-*` headers** before WAF/origin so they cannot be forged. Attempts 6–10 without the header → `challenge_required` → the SDK obtains a token and the client retries. Spike S-2 (Milestone 0) verifies the end-to-end behavior on a deployed stack. Requires WAF Bot Control (targeted) or the challenge token features — cost added to 10 §10.4. Honeypot field; client-generated `submission_id` for idempotent submission (AR-28).
- **WebSocket**: `ws.<domain>` is fronted by **CloudFront (WebSocket supported) with the same WAF rate rule** (SEC-19); stage throttling on `$connect`; `$connect` requires a valid single-use ticket (§7.1); per-user connection limit 10 and per-user `$connect` rate 10/min enforced in DynamoDB.
- **Public form mass assignment (SEC-8)**: the form service builds the item **only from the form definition**: unknown keys dropped; hidden-question defaults applied server-side and never sent to the client; Connect and People columns not allowed in public forms (P1); Files only from upload slots issued to this form + IP and bound on submit (SEC-1); `GET /forms/{token}` returns only visible questions' labels, types, required flags and options (no column ids, no board schema).
- **Account baseline (SEC-20)**: GuardDuty, Security Hub (AWS FSBP), AWS Config, organization CloudTrail enabled in every account; GitHub OIDC trust restricted to `repo:<org>/<repo>:environment:<stage>`; the fake-clock route is **excluded at CDK synth for prod** (synth test asserts it). P1 audit event kinds: admin override access, sign-in failures/lockouts, role & permission changes, exports, MFA changes/resets, user (de)activation, automation owner changes.

## 7.5 Threat model (STRIDE summary)
| Threat | Example | Mitigation |
|---|---|---|
| Spoofing | stolen access token | 60 min TTL, refresh revocation, MFA, WAF IP reputation |
| Tampering | client sends forged actor/automation ids | actor derived server-side only; automation actions only via runner role |
| Repudiation | "I didn't change that" | activity log + audit events with actor & IP |
| Information disclosure | mirrors/formulas/search/export/realtime leaking hidden boards; IDOR on items/files | single authz helper on every read path; 404 for no access; D-012/D-015/D-018/D-020 tests |
| DoS | form flooding, huge imports, expensive filters | WAF + app rate limits; import size caps; query timeouts (statement_timeout 10 s) and max 10 filter rules |
| Elevation | member edits structure under edit_content; viewer writes | capability matrix tests; Viewer ceiling |

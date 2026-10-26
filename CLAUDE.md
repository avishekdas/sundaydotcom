# Tasklane — working notes for Claude sessions

Self-hosted monday.com-style Work Management + CRM ("Tasklane") on AWS serverless. Owner: Avishek Das
(software architect, Python, extensive design experience — talk to him as a peer). This file is the hand-off
between sessions: **read it first, keep it current** (status at every milestone, learnings as they happen).

## Start of every session (checklist)
1. Read this file, then the plan's section for the current milestone (`docs/04-plan/implementation-plan.md`,
   status line + "Carried from the … review"), the tail of `docs/00-decision-log.md`, and the latest
   `docs/04-plan/milestone-reviews/<M>.md`.
2. Make sure the repo is attached **with push access** (`add_repo` access=push; the user has asked Claude to own
   pushing) and the cloud clone `/home/claude/sundaydotcom` is at `origin/main`.
3. Baseline the gates in the clone before changing anything (see "Gates"). Check CI with the public API (below).
4. State which story you are starting and what "done" means for it, tied to an AC and/or a north-star step.

## How the user wants work done (non-negotiable)
- **≥ 95 % confidence before every step.** If below, ask with AskUserQuestion (2–4 concrete options, the
  recommended one first with its trade-off) — never guess on scope, cost, security or anything external.
  Decisions with cost or external effect are the user's; record each as **D-xxx** in the decision log.
- **North-star alignment at every milestone** (plan §1.1, `contracts/north_star.yaml`): at kickoff the
  milestone's steps get tests first as strict expected failures (pytest `xfail(strict=True, raises=AssertionError)`,
  Playwright `test.fail()`); the milestone is done only when they pass in Tier A (in-process, chaos seeds) and
  Tier B (Playwright on dev). The contract test fails the build for untagged steps or missing tests.
- **TDD**: commit a red test first (`test(<area>): red — …`), then green. **Push the red commit on its own** and
  let CI record the red run before pushing the green one (CI runs only on the head of a push; TP-6).
- Milestone done = plan §1.3 checklist incl. an **independent review agent** (one that did not build it) writing
  `milestone-reviews/<M>.md`; blocking findings fixed before "done".
- Commits end with the Co-Authored-By / Claude-Session trailers; author email is the GitHub no-reply
  `5960956+avishekdas@users.noreply.github.com` (GitHub rejects pushes exposing the private email).
- Implementation plans follow the user's style: TDD, milestone-driven, system test at the end of each milestone.
- Keep replies short; don't recap steps; say plainly what failed.

## Git, CI and the user's copy
- Develop, test and commit in the **cloud clone** `/home/claude/sundaydotcom`; `git push origin main` from there.
  Then fast-forward the user's copy `~/tasklane` (Mac) through the device shell: `cd $HOME/mnt/tasklane &&
  git pull --ff-only`. The device VM **cannot run the Mac's `.venv`** (macOS binaries) and has **no GitHub
  credentials** (fetch/pull of the public repo works, push does not). Delete permission in `~/tasklane` is needed
  for git's lock files (request it once per session if a git command fails on a lock).
- CI status without `gh` (its token is invalid here): public API, e.g.
  `curl -sS "https://api.github.com/repos/avishekdas/sundaydotcom/actions/runs?per_page=8"`. Logs aren't readable
  through the proxy: rely on step results / annotations (`scripts/ci-run.sh` turns failures into annotations).
- Pipeline on push to `main`: ci → deploy-dev (data gate → network/data/migrate stacks → migrate λ → code stacks)
  → e2e-dev (Tier B, all `e2e/*.spec.ts`). The `dev` GitHub environment accepts deployments from `main` only.
  e2e-dev runs list `head_sha` as main's head at trigger time, not necessarily the deployed commit.

## Gates (= `scripts/check.sh` = CI)
In `backend/` (set `UV_SYSTEM_CERTS=1`, unset `UV_NATIVE_TLS`): `uv run ruff format --check . && uv run ruff
check . && uv run mypy src && uv run lint-imports && uv run pytest -q --cov=tasklane --cov-fail-under=90`.
`infra/`: ruff + pytest (CDK assertions). `web/`: `npx tsc -b && npx vitest run`. Integration tests use embedded
PostgreSQL 18.6 (~25 s for the whole backend suite). Import layers are enforced (arch 11): devserver → api|workers
→ collab|automation|insights|crm|forms → workmgmt → computed → schema → identity → platform.

## Where things are
- Plan: `docs/04-plan/implementation-plan.md` (M0a…M9; §1 how we work, §1.3 done checklist, §1.4 dev-only
  adaptation D-031, §2 milestone map, §4 load gates). AC ownership: `docs/04-plan/ac-ownership.md` (M1 owns 24).
- Requirements: `docs/02-requirements/` (north star in `README.md`; K1–K3/K7 in `09-permissions-admin.md`).
- Architecture: `docs/03-architecture/` — 07 security & permissions (§7.1 auth proxy, §7.2 authz, §7.2a
  visibility rule table), 03 data model, 04 API, 05 events/realtime, 02 deployment, ADRs in `adr.md`
  (Appendix A = spike outcomes). Spikes: `spikes/*/REPORT.md` (S-2b: `spikes/s2b/`).
- Code: `backend/` (Python 3.13, uv), `infra/` (CDK Python), `web/` (React+TS+Vite), `e2e/` (Playwright),
  `contracts/` (`north_star.yaml`, `events/`), `ops/` (runbooks, seed), `scripts/`.
- Key code: `platform/db.py` (Db port, `StrictDataApiFake`, `Json` params), `platform/mutation.py` (single-statement
  writable-CTE builder with guards), `identity/visibility.py` (VisibleItems CTEs), `api/app.py` (`route_inventory()`),
  `tests/system/test_north_star_m1.py` (`READ_ROUTES` — a new route is a write until declared a read).

## Environment facts
- AWS: single dev stage, account 920824005451, us-east-1 (D-031). Deploy via OIDC role `tasklane-gh-deploy-dev`
  (`infra/bootstrap/github-oidc.json`; it can assume CDK roles, invoke `tasklane-dev-migrate`, read
  `tasklane/dev/test-users/*`). Dev URL: CloudFront default domain (D-038), output `Url` of stack
  `tasklane-dev-edge`. Cognito pool `tasklane-dev` (us-east-1_BW2gyuWcc, MFA **OPTIONAL**, SPA client with
  `USER_PASSWORD_AUTH`, RemovalPolicy RETAIN). Test user secret `tasklane/dev/test-users/a` (hand-made, M0B-24).
  Alerts → SNS email (confirmed).
- Ad-hoc AWS work goes through the AWS MCP `run_script` sandbox: **no classes, no `logging`, no underscore
  attribute names, no async generator expressions**; failing boto calls flood stderr (keep runs small); runs over
  ~1 min become tasks — poll `get_tasks`, and parse large results from the saved file with python/jq.
- Spike IaC is committed as templates under `spikes/*/infra` and deployed as throwaway stacks; delete after.

## Gotchas and learnings (keep adding)
- **Desktop (Mac) sessions** have no `/home/claude` cloud clone: work, commit and `git push` directly in `~/tasklane`
  (push works with the Mac's git credentials). Gates locally need `JSII_RUNTIME_PACKAGE_CACHE=disabled` (jsii refuses
  the group-writable `~/Library/Caches`) and a one-off `npm ci` in `web/`. The AWS MCP connector can drop mid-session
  ("connection invalidated" → user reconnects it); the Mac has no AWS profile for account 920824005451.
- moto: `revoke_token` is not implemented and pools ignore `UsernameConfiguration.CaseSensitive` (CognitoIdp
  lower-cases emails itself); test revoke on the fake + Tier B.
- The user prefers questions **one at a time**, each with the context needed to answer (AskUserQuestion has failed in
  desktop sessions — ask in plain text with lettered options, recommendation first).
- **Data API** (enforced by `StrictDataApiFake`): no array params (sets travel as JSON text); ints arrive as bigint
  (cast `::int`); results: jsonb/json as text, numeric/uuid as strings, timestamps as UTC strings; `interval`,
  `xid8`, `citext` results unsupported (cast to text); 64 KB row / 1 MiB response / 45 s statement; one statement
  per call; commit/rollback take no `database`. Aurora 18.6 SLv2 min 0 ACU auto-pauses (first call may hit
  `DatabaseResuming`, M0B-15 still open).
- **Cognito (S-2b, measured)**: lockout is per user only (no per-caller/IP lock — the auth λ's shared egress IP is
  fine); lock after the n-th evaluated failure = 2^(n−5) s; during a lock every attempt (right password too) gets
  "Password attempts exceeded" and isn't counted; a success resets the counter. Under heavy parallel load locks
  once ran longer than the schedule → always retry with margin.
- **HTTP API integration limit 30 s**, api λ timeout 29 s → never wait > ~20 s in-request (D-043).
- MFA is **deferred to M9** (D-045): the dev pool stays OPTIONAL. If it is ever enabled: docs say `UpdateUserPool`
  cannot set `ON` but `SetUserPoolMfaConfig` can on an existing pool — unverified on AWS; probe a throwaway pool first.
- WAF runs **before** viewer-request CloudFront Functions (S-2a, D-029); WAF itself is deferred to M6 (D-041), so
  there is no CAPTCHA in M1–M5 (hence D-044).
- Mutation builder rules (arch 03 §3.5) are still regex heuristics — M0B-5 (structural checks, edit_assigned guard
  in `set_values`) is carried into M1.
- Generated tests over `route_inventory()` grow automatically; authorization must run **before** body validation.
- Dev workers run hourly 08:00–19:00 New York (D-037): a failed publish can take ~1 h to be swept on dev.
- `make dev` = embedded Postgres + real api handler + local WebSocket (works in the cloud clone, not the device VM).

## Status
- M0a done; M0b done (review `milestone-reviews/M0b.md`; Tier B run 40249155724).
- **M1 in progress** (head b7c5768, CI/deploy/Tier B green 2026-10-26):
  - done: S-2b (`spikes/s2b/REPORT.md`; D-043 retry contract, D-044 interim account closure); north-star
    contract + M1 kickoff (steps `1a.sign_in_create_workspace` Tier B `e2e/m1-sign-in-workspace.spec.ts` and
    `7.viewer_read_only` Tier A — both expected failures); VisibleItems builder + rule-table harness
    (15/15 builder mutants killed).
  - **auth slice decided (D-045…D-049, 2026-10-26)**: no MFA in M1 (AC-K7-1 → M9); sub-stories, each red/green with
    Tier B green between: (1) scripted test identities — dev-only custom resource, admin/member/viewer/outsider in one
    secret `tasklane/dev/test-users/all`, `tl.users` rows, refused for prod; then retire hand-made user `a`;
    (2) auth proxy `/api/auth/*` (07 §7.1 incl. D-043/D-044, SEC-5/SEC-6, refresh cookie 30 d), AC-K7-2 in Tier A via
    injected `CloudFront-Viewer-Address`; (3) SPA on the proxy (direct `USER_PASSWORD_AUTH` removed);
    (4) forgot/reset (Cognito default email) + revocation, AC-K7-3. Two-IP dev probe λ goes into the M1 system test.
  - **sub-story 1 done** (6055181; Tier B 40380217106 green as the scripted admin). Still open: retire user `a`
    (deactivate row, disable in Cognito, delete secret `tasklane/dev/test-users/a`) — needs AWS access.
  - **sub-story 2** (auth proxy backend) decided D-050 (origin secret in SSM), D-051 (proxy inside the api λ,
    Cognito actions limited to AdminInitiateAuth + AdminUserGlobalSignOut), D-052 (per-browser sign-out +
    `/api/v1/me/sign-out-everywhere`). Tier B `e2e/auth-proxy.spec.ts` uses a random unknown email per run for the
    lockout check so no test user is ever locked.
  - then: PermissionSnapshot + perm_epoch + tokens_valid_after, authz caps matrix (AC-K3-4) wired into every
    route via VisibleItems (flips step 7), bootstrap admin, users/invites/deactivate, roles, workspaces & members,
    board kinds & members, permission sets (no edit_assigned), audit events, left nav, profile/timezone;
    M0b carried items (M0B-5/6/8/10/12 nightly 500-seed + mutation job/14/16/17); D-042 role rotation.
  - not yet done from M0B-12: nightly 500-seed Tier A job and nightly mutation testing.

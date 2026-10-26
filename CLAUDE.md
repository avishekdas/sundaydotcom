# Tasklane — working notes for Claude sessions

Self-hosted monday.com-style Work Management + CRM ("Tasklane") on AWS serverless. **North star = replicate
monday.com features** (user, 2026-10-26); security extras that monday.com does not need (e.g. MFA) are deferred.
Owner: Avishek Das (software architect, Python, extensive design experience — talk to him as a peer). This file is
the hand-off between sessions: **read it first, keep it current** (status at every story, learnings as they happen).

## Start of every session (checklist)
1. Read this file, then the plan's section for the current milestone (`docs/04-plan/implementation-plan.md`),
   the tail of `docs/00-decision-log.md` (D-045…D-058 are this M1's decisions), the latest review
   `docs/04-plan/milestone-reviews/<M>.md`, and the requirement files the next story touches.
2. Where you run decides git: **Mac desktop session** → work, commit and `git push` directly in `~/tasklane`
   (push works). **Cloud session** → clone to `/home/claude/sundaydotcom` with push access, push from there, then
   the user fast-forwards `~/tasklane` (`git pull --ff-only`).
3. Baseline the gates before changing anything (see "Gates"); check CI and the last deploy (see "CI").
4. Before every story: restate it, its ACs and north-star steps, then ask questions until ≥ 95 % confident.

## How the user wants work done (non-negotiable)
- **≥ 95 % confidence before every step and story.** Ask **one question at a time**, in plain text with lettered
  options, the recommended one first with its trade-off and enough context to answer (AskUserQuestion failed in
  desktop sessions). Never guess on scope, cost, security or anything external. Decisions with cost or external
  effect are the user's; record each as **D-xxx** in the decision log.
- **TDD**: commit a red test first (`test(<area>): red — …`), **push it alone and let CI record the red run**, then
  the green. Strict-xfail north-star steps at milestone kickoff (pytest `xfail(strict=True, raises=AssertionError)`,
  Playwright `test.fail()`); a milestone is done when they pass in Tier A (in-process) and Tier B (Playwright on dev).
- Milestone done = plan §1.3 checklist incl. an **independent review agent** (one that did not build it) writing
  `docs/04-plan/milestone-reviews/<M>.md`; blocking findings fixed before "done".
- Commits: conventional type, end with `Co-Authored-By: Claude …`; author email is the GitHub no-reply
  `5960956+avishekdas@users.noreply.github.com`. Keep replies short; say plainly what failed.
- The user decides how big a story is; this M1 they chose bigger bundles (one story, one red/green) after the auth
  slice. Ask, don't assume.

## Gates (= `scripts/check.sh` = CI)
- backend: `UV_SYSTEM_CERTS=1`, unset `UV_NATIVE_TLS`; `uv run ruff format --check . && uv run ruff check . && uv run
  mypy src && uv run lint-imports && uv run pytest -q --cov=tasklane --cov-fail-under=90` (≈ 50 s, 405 tests, 94 %).
- infra: `JSII_RUNTIME_PACKAGE_CACHE=disabled JSII_SILENCE_WARNING_DEPRECATED_NODE_VERSION=1 uv run pytest -q` (65).
- web: `npx tsc -b && npx vitest run` (44). Use Node ≥ 22 for anything npm: `PATH=~/.nvm/versions/node/v22.23.4/bin:$PATH`.
- CI also runs squawk on migrations ≥ 0005: `npx -y squawk-cli@2.30.0 --exclude prefer-robust-stmts,prefer-identity,prefer-bigint-over-smallint,require-timeout-settings <files>`.
- Import layers (import-linter): devserver → api|workers → collab|automation|insights|crm|forms → workmgmt →
  computed → schema → identity → platform.

## CI, deploy and evidence
- CI status (gh token invalid): `curl -sS "https://api.github.com/repos/avishekdas/sundaydotcom/actions/runs?per_page=8"`.
  Logs are not readable; **failure details are in check-run annotations**:
  `curl …/commits/<sha>/check-runs` → `…/check-runs/<id>/annotations`. Every CI/deploy/e2e step that matters runs
  through `scripts/ci-run.sh`, which turns the last 40 log lines of a failure into an annotation (deploy failures
  show the CloudFormation events there).
- Pipeline on push to `main`: ci → deploy-dev (data gate → network/data/migrate stacks → **migrate λ** → code
  stacks) → e2e-dev (Tier B: all `e2e/*.spec.ts`, then `scripts/ac-k7-2-probe.sh`). e2e-dev records main's head
  sha at trigger time, not necessarily the deployed commit.
- **Never push while the previous push's `ci` is running** (it cancels in-progress runs; a green was once never
  deployed). Prefer also waiting for deploy-dev to finish: a new push queues another deploy.
- Migrations apply **before** code stacks: if a code stack then rolls back, dev runs old code on the new schema/grants.
- Watch a pipeline with a background loop over the runs API (poll every 60 s); don't sleep in the foreground.

## Environment facts
- AWS: single dev stage, account **920824005451**, us-east-1 (D-031). **Mac**: static profile `avishek` (IAM user
  `developer`): `export AWS_PROFILE=avishek AWS_REGION=us-east-1` (zsh doesn't word-split a `$P` flag variable).
  AWS CLI 2.38 (pkg installer, not Homebrew). The AWS MCP connector may drop ("connection invalidated").
- **Dev URL: https://d3qaglpzkbgmho.cloudfront.net** (output `Url` of `tasklane-dev-edge`, D-038).
- Cognito pool `tasklane-dev` (us-east-1_BW2gyuWcc, RETAIN, MFA OPTIONAL — deferred to M9, D-045); **only client
  `tasklane-dev-proxy`** (admin auth, 30-day refresh, revocation; D-048). Invite temp passwords valid 7 days.
- Users on dev: bootstrap Admin **avishekdas.cool@gmail.com** (active; D-055); scripted test users
  admin/member/viewer/outsider `tasklane-test-<name>@example.com` in secret `tasklane/dev/test-users/all` (D-049);
  the hand-made user `a` is retired (row deactivated, Cognito disabled, its secret deleted 2026-11-02).
- Deploy role `tasklane-gh-deploy-dev` = CloudFormation stack **`tasklane-github-oidc`** from
  `infra/bootstrap/github-oidc.json`; changes are applied **by the user**:
  `aws cloudformation deploy --template-file infra/bootstrap/github-oidc.json --stack-name tasklane-github-oidc --capabilities CAPABILITY_NAMED_IAM --profile avishek --region us-east-1`.
  It may invoke `tasklane-dev-migrate` and `tasklane-dev-ip-probe`.
- DB roles/secrets: `tasklane/dev/db/<role>` (tl_api_rw, tl_audit_writer, tl_reader, tl_worker*, tl_migrator).
  Data API read from the Mac: `aws rds-data execute-statement --resource-arn <tasklane-dev-data-cluster… ARN>
  --secret-arn <tl_api_rw ARN> --database tasklane --sql "…"`. The api role cannot read `tl.audit_events`.
- Origin secret SSM `/tasklane/dev/origin-secret` (D-050); counters table `tasklane-dev-counters`.
- Alarms email avishekdas.cool@gmail.com (D-040). Dev workers run hourly 08:00–19:00 New York (D-037).

## Where things are
- Plan `docs/04-plan/implementation-plan.md`; AC ownership `docs/04-plan/ac-ownership.md` (M1 owns 23 — AC-K7-1
  moved to M9); requirements `docs/02-requirements/`; architecture `docs/03-architecture/` (07 security, 03 data,
  04 API, 05 realtime, 02 deployment, `adr.md`); runbooks `ops/runbooks/` (incl. `bad-deploy.md`, `auth.md`, `cognito.md`).
- Backend key modules: `platform/db.py` (`StrictDataApiFake(uri, role=…)`), `platform/mutation.py` (writable-CTE
  builder: structural rules 2–4, `EPOCH_GUARD`, `ASSIGN_GUARD`), `platform/migrations.py` (lease, SCRAM),
  `platform/counters.py`; `identity/` — `authz.py` (K1/K3 caps as data), `snapshot.py` (PermissionSnapshot),
  `visibility.py` (VisibleItems + snapshot SQL), `auth_proxy.py`, `auth_backend.py` (Cognito + `FakeAuthBackend`
  that is also a fake IdP), `users.py`, `account.py`, `audit.py`, `profile.py`, `bootstrap.py`, `test_identities.py`,
  `viewer_ip.py`; `workmgmt/` — `workspaces.py`, `board_access.py`, `positions.py`, `boards.py`; `api/app.py`
  (routes, `route_inventory()`, `_permissions_changed()`); `workers/` — `predeploy_hook.py`, `ip_probe.py`,
  `bootstrap.py`, `test_identities.py`, `migrate.py`.
- Tests that must grow with every new route: `tests/system/test_north_star_m1.py` (step 7: `READ_ROUTES`/`BODIES`)
  and `tests/integration/identity/test_permissions_api.py` (AC-K3-4: every route declares its capability). The
  grant table for `tl_api_rw` is `tests/integration/migrations/test_0007_api_grants.py` — new tables need a
  migration grant **and** an entry there. Shared integration world: `tests/integration/world.py` (runs as
  `tl_api_rw` / `tl_audit_writer`).
- SPA: `web/src/auth.ts`, `api.ts`, `format.ts`, `ui/` (`App`, `LeftNav`, `UsersAdmin`, `AccountSettings`,
  `Profile`, `BoardAccess`, `BoardView`), `sync/` (store/engine).
- Nightly: `.github/workflows/nightly.yml` (500 rotating Tier A seeds, mutmut on authz/viewer_ip/positions ≥ 70 %
  — 75 % now, Stryker on `sync/store.ts` ≥ 70 % — 93 % now; Stryker is installed per run, not in the lockfile).

## Gotchas and learnings (keep adding)
- **Run tests as the deployed role.** The integration world runs as `tl_api_rw`; that caught `INSERT … RETURNING`
  needing SELECT (tl.outbox). Superuser tests hide missing grants.
- **Hand-built Lambda events must go through the real handler in a test** (the pre-traffic hook lacked
  `requestContext.stage`; Powertools raised; the gate blocked a good deploy).
- **CodeDeploy hooks**: the `live` alias update starts the deployment, so it must depend on the deployment group's
  role (CodeDeploy's right to invoke the hook) — else "Internal error occurred".
- **CDK cross-stack refs are CloudFormation exports**: deleting a resource another stack imports takes two deploys
  (move consumers, then delete; a strict xfail guards the second step).
- **npm lockfiles**: verify with `npm ci --cache <empty dir>`; a lockfile local npm accepts can still fail on the
  runners ("Missing … from lock file"). Keep heavy tooling (Stryker) out of the app lockfile.
- **IPv6**: CloudFront sends `CloudFront-Viewer-Address` without brackets (`2001:db8::7:443`); GitHub runners are
  IPv4-only, so probe with `curl -6` from the Mac after auth changes.
- **Snapshot cache** is per `Deps` instance, ≤ 30 s; routes that change permissions call `_permissions_changed()`;
  writes are epoch-guarded and re-authorize once. `perm_epoch` moves only via `select tl.bump_perm_epoch()`.
- **Auth proxy** lives in the api λ (D-051); `/api/auth/*` has no JWT authorizer, everything needs `x-tl-origin`.
  Lockout counters: `signin#<email>#<ip>` (5/15 min) and `signin#<email>` (10/15 min → closed, Sev2); unknown emails
  behave like wrong passwords. Tier B lockout checks use a random unknown email; the two-IP check uses `outsider`
  and clears its counters through `tasklane-dev-ip-probe`.
- **Data API** (enforced by `StrictDataApiFake`): no array params (JSON text), ints as bigint (cast `::int`), jsonb
  results as text, 64 KB row / 1 MiB response / 45 s statement, one statement per call; `make_interval(days =>
  :d::int)`. Dev Aurora auto-pauses (first call may hit `DatabaseResuming`).
- **Cognito**: lockout per user only, lock 2^(n−5) s; moto lacks `revoke_token` and ignores case-insensitive
  usernames (CognitoIdp lower-cases emails). HTTP API integration limit 30 s → never wait > ~20 s in-request.
- **Mac disk**: test fixtures now drop each DB and remove the embedded-PG dir; if the disk fills again, look for
  `$TMPDIR/tl-pg-*` (the user deletes them — the classifier blocks agent sweeps of shared temp).
- Lint: `ruff` S608 flags SQL built by `+`/f-strings — build from constants with `.replace("__X__", CONST)`.
- Local gates on the Mac need `JSII_RUNTIME_PACKAGE_CACHE=disabled`; `web/` needs one `npm ci` per checkout.

## Status
- M0a done; M0b done (`milestone-reviews/M0b.md`).
- **M1 — code complete, close pending** (2026-10-26). Owned ACs: 23 (all have tagged tests; AC-K1-1 partial —
  create board/export/automation routes come in M2/M5; AC-F7-5 server side — live UI switch needs the M3
  `permission.changed` event). North star: step 7 passes in Tier A; step 1a passes in Tier B (b24d1d0, run 40396216643).
  Delivered (each red → green, Tier B green unless noted):
  - auth slice: scripted test identities (6055181), auth proxy (84e5fba), SPA on proxy (f30caa3), forgot/reset
    (524196e), old web client removed (4e72e4f); IPv6 fix (31a227d)
  - permission framework + step 7 (3daa63f); workspaces + left nav + step 1a (b24d1d0); users/invites/roles
    (e048f14) + bootstrap admin (f71d1b0); account settings + audit (ab676f3); board access + profile (97a3ffe)
  - hardening bundle (d1bd4b7 + fixes 866ac9f, 4148c99, 2dbfe0a; D-057/D-058): migration 0007 grants, SCRAM
    passwords, leased no-tx migrations, Mutation builder rules, pre-traffic hook, dashboard, bad-deploy runbook,
    nightly; two-IP AC-K7-2 probe (9c3cc55); Cognito runbook + M0B-29 (7fcc738).
  - **Dev is current and green on 2dbfe0a**: deploy-dev 40421710943, e2e-dev 40423088711 (Tier B incl.
    `AC-K7-2 on dev: IP A 5×401 then 429; IP B 200 in 2.14s`); `live` = api version 20; sign-in OK over IPv4 + IPv6.
    The two earlier attempts rolled back (alias/policy race 866ac9f; hook event bug 4148c99) — both fixed test-first.
- **Next steps (in order):**
  1. Check the first nightly run (`nightly` workflow, 06:00 UTC): 500 seeds, mutmut ≥ 70 %, Stryker ≥ 70 %; fix
     test-first if red (a failing seed goes into `FIXED_SEEDS`).
  2. Confirm the last push (hand-off docs) deployed green as well.
  3. M1 close (plan §1.3): write `docs/04-plan/system-tests/M1.md` (evidence: run ids above, step 1a/7, AC list,
     two-IP result, partial ACs), update the plan's M1 status line, then spawn an **independent review agent** to
     write `docs/04-plan/milestone-reviews/M1.md`; fix blocking findings (red → green), get the user's approval.
  4. Then M2 (boards, items, columns, table & views; 57 ACs): kickoff = strict-xfail steps `4a.assign_owner` and
     `4b.deal_value_close_date`, then stories per plan §3 M2 — ask the user how to slice it.
- Deferred (decided): MFA + AC-K7-1 → M9 (D-045); breached-password check → M9; D-042 secret rotation → P-launch
  (D-057); WAF/CAPTCHA → M6 (D-041); a people directory for non-admin board owners → with the People column (M2).

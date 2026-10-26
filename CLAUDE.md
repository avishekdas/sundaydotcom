# Tasklane — working notes for Claude sessions

Self-hosted monday.com-style Work Management + CRM ("Tasklane") on AWS serverless. Owner: Avishek Das
(software architect, Python). This file is the hand-off between sessions: read it first, keep it current at the
end of every milestone.

## Where things are
- Plan (source of truth for what to build next): `docs/04-plan/implementation-plan.md` — milestones M0a…M9,
  each with a status line and "Carried from the … review" items. AC ownership: `docs/04-plan/ac-ownership.md`.
- Decisions: `docs/00-decision-log.md` (D-001 …). Requirements: `docs/02-requirements/`. Architecture:
  `docs/03-architecture/` (ADRs in `adr.md`). Milestone reviews: `docs/04-plan/milestone-reviews/`.
- Code: `backend/` (Python 3.13, uv), `infra/` (CDK Python), `web/` (React+TS+Vite), `e2e/` (Playwright),
  `contracts/`, `ops/` (runbooks, seed), `scripts/check.sh` (= CI gates).

## How the user wants work done
- TDD: commit a red test first ("test(...): red — ..."), then green. Milestone-driven; each milestone ends with its
  north-star system test (Tier A in-process with chaos + Tier B Playwright on dev) **and an independent review
  agent** writing `milestone-reviews/<M>.md`; blocking findings fixed before "done".
- Be ≥ 95 % confident before proceeding; otherwise ask (AskUserQuestion). Decisions with cost or external effect
  are the user's (record them as D-xxx).
- Commits end with the Co-Authored-By / Claude-Session trailers; author email is the GitHub no-reply
  `5960956+avishekdas@users.noreply.github.com` (GitHub blocks pushes exposing the private email).

## Environment facts
- Repo `github.com/avishekdas/sundaydotcom` (public), branch `main` only; the `dev` GitHub environment accepts
  deployments from `main` only. Pipeline: ci → deploy-dev (data gate → data/migrate stacks → migrate λ → code
  stacks) → e2e-dev (Tier B). Logs aren't readable through the proxy: use step results / annotations
  (`scripts/ci-run.sh` surfaces failures as annotations).
- AWS: single dev stage, account 920824005451, us-east-1 (D-031). Deploy via OIDC role `tasklane-gh-deploy-dev`
  (template `infra/bootstrap/github-oidc.json`). Dev URL: CloudFront default domain (D-038), output `Url` of
  stack `tasklane-dev-edge`. Test user secret `tasklane/dev/test-users/a`. Alerts → SNS email (confirmed).
- Aurora PostgreSQL 18.6 Serverless v2, min 0 ACU (auto-pause), reached only through the RDS Data API. Data API
  gotchas (enforced by `StrictDataApiFake`): no array params; ints arrive as bigint (cast `::int` for int
  functions); results: jsonb/json as text, numeric/uuid as strings, timestamps as UTC strings; `interval`, `xid8`,
  `citext` results are unsupported (cast to text); 64 KB row / 1 MiB response / 45 s statement; one statement per
  call; commit/rollback take no `database`.
- Dev workers (outbox sweeper, scheduler-tick) run hourly 08:00–19:00 New York time (D-037).
- Local: `make dev` (embedded Postgres + real api handler + local WebSocket), `make check`.
- The user's working copy is `~/tasklane` on their Mac. **Claude handles `git push`** (user request 2026-10-26).
  Claude develops in the cloud clone `/home/claude/sundaydotcom` (repo attached with push access; the Mac's
  `.venv` is macOS-only and can't run in the device VM), runs `make check`-equivalent gates there, pushes `main`,
  then fast-forwards the Mac copy with `git pull --ff-only` through the device shell (fetch works without
  credentials). A new session may need the user to approve push access again (add_repo with push).

## Status (update at each milestone)
- M0a done (review fixes applied). M0b done (review `milestone-reviews/M0b.md`; final Tier B run 40249155724).
- M1 in progress: S-2b done (D-043 retry contract, D-044 interim account closure). Next M1 stories: test-identity
  fixtures (PE-17), VisibleItems builder + harness, auth λ / proxy, then the rest of the plan's M1 list and the
  "Carried from the M0b review" items.
- AWS MCP sandbox for ad-hoc AWS work: no classes, no `logging`, no underscore attributes; runs > ~1 min become
  tasks (poll get_tasks; parse large results from the saved file).

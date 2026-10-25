# 11 — Repository Structure

```
monday-clone/                         (git root; product name "Tasklane")
  docs/                               requirements, architecture, plan (this folder)
  backend/
    pyproject.toml                    uv-managed; ruff, mypy, pytest, import-linter config
    src/tasklane/
      platform/                       config, db port (DataApiDb, PsycopgDb, StrictDataApiFake), sql builders (JSON-array params, writable-CTE mutation builder, VisibleItems CTE), unit_of_work, outbox, event bus port (EventBridgeBus, InProcessBus), idempotency, ids, errors, clock/tz (fakeable), logging
      identity/                       users, roles, authz (pure), permission snapshot, audit
      schema/                         column types/<type>.py codecs, settings models, QuerySpec, board schema read model (shared kernel)
      workmgmt/                       workspaces, boards, groups, columns service, items, links, views, query compiler, trash, import/export
      computed/                       formula (lexer, parser, evaluator, functions), mirror, dependency graph, recompute worker
      collab/                         updates, subscriptions, notifications, files, activity log, presence
      automation/                     catalog (triggers/, conditions/, actions/), dispatcher, runner, variables, scheduler
      insights/                       dashboards, widgets/<type>.py compilers, search
      crm/                            template (L1-spec as data), timeline, activities
      forms/                          public form service, throttling
      api/                            `api` λ entry (routers per context: workmgmt, collab, automation, insights, crm, identity incl. auth proxy), `forms_public` λ entry; Powertools resolvers, Pydantic schemas
      workers/                        fanout.py, dispatcher.py, automation_runner.py, recompute.py, notifier.py, indexer.py, job_worker.py, outbox_acker.py, outbox_sweeper.py, scheduler_tick.py, ws_handlers.py, migrate.py
    migrations/                       0001_init.sql …
    tests/
      unit/                           mirrors src tree; pure logic (authz, codecs, formula, query plan, triggers, variables)
      integration/                    real Postgres (docker) + moto for AWS clients; service-level tests per AC
      contract/                       OpenAPI conformance; permission matrix (AC-K3-4)
  web/                                pnpm workspace: apps/app (SPA), apps/forms (public form), packages/shared (tokens, formatters, generated clients)
  contracts/                          openapi.json, ws-messages.json, column JSON Schemas, column-display golden fixture, queryspec golden corpus, north_star.yaml
  backend/src/tasklane/devserver/     Starlette shim: HTTP → Powertools events, local WS endpoint, dev identity provider
  e2e/                                Playwright: north-star.spec.ts, per-feature specs; k6 load scripts
  infra/                              AWS CDK (Python)
    app.py
    stacks/ network.py data.py identity.py messaging.py api.py realtime.py workers.py edge.py observability.py
    constructs/ python_function.py (Powertools layer, SnapStart, alarms), fifo_with_dlq.py
    tests/                            CDK assertions + cdk-nag
  ops/                                runbooks, redrive, restore drill scripts
  .github/workflows/                  ci.yml, deploy.yml
```
**Layered module contract (import-linter, no cycles) — DX-6:**
```
platform  →  identity  →  schema  →  computed  →  workmgmt  →  {collab, automation, insights, crm, forms}  →  api / workers / devserver
```
- `schema` (shared kernel): column types & codecs, settings models, QuerySpec, board-schema read model.
- `computed`: pure formula/mirror engine + SQL emitters (no DB access of its own).
- `workmgmt`: services, query compiler (uses `computed` SQL emitters), `VisibleItems` builder (from `identity`).
- Cross-context writes inside one statement use the **`Mutation` builder** in `platform`: a mutation is a list of named CTE fragments; other contexts contribute fragments via `uow.add(fragment)` (activity log, board_changes, outbox, automation step row). Tables are owned by one context, but fragments let them be written atomically.

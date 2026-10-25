# 09 — Frontend (SPA) (ADR-010)

## 9.1 Stack
React 19 + TypeScript (strict) + Vite; routing: TanStack Router; server state: **entity store** (Zustand, §9.3a) for items + TanStack Query for non-item resources and query metadata; client UI state: Zustand; virtualization: TanStack Virtual (rows and columns); drag & drop: dnd-kit; rich text: Tiptap (ProseMirror JSON stored as-is); charts: Apache ECharts; forms: React Hook Form + Zod schemas generated from OpenAPI; i18n: FormatJS with extracted catalog (AC-O5-1 lint); styling: CSS variables design tokens + CSS Modules, light theme (dark P2); tests: Vitest + Testing Library (components), Playwright (e2e, also at 768 px, AC-O1-1), MSW for API mocking.

## 9.2 Structure
```
web/src/
  app/            routes, layout (left rail, nav tree, top bar)
  api/            generated OpenAPI client, query keys, websocket client
  realtime/       socket manager, channel subscriptions, version reconciliation, presence
  features/
    boards/       board page, toolbar (search/person/filter/sort/group/hide), view tabs
    table/        virtualized grid, group sections, footers, keyboard nav
    kanban/
    columns/      one folder per column type: Cell, Editor, FilterInput, (formatters)
    item/         item page, field panel, updates, activity log, subitems
    automations/  center (create/manage/history), sentence builder
    dashboards/   canvas (react-grid-layout), widgets
    forms/        form builder; public form app is a separate Vite entry (no auth code)
    crm/          timeline, activity composer, C38 cell
    admin/        account, users, invites
    search/       ⌘K palette
  design/         tokens, primitives (Button, Popover, Menu, Avatar, Chip, Toast)
```

## 9.3 Data flow
- Board page loads `GET /boards/{id}/schema` + first page of `POST /boards/{id}/query`; subscribes `board:{id}`.
- **Optimistic edits**: mutation updates the cached row immediately, sends PATCH; on success records returned `version`; on error rolls back + toast (AC-B6-6).
- **Auth**: sign-in UI talks only to `/api/auth/*`; access token kept in memory, refresh via HttpOnly cookie (`/api/auth/refresh`) on load and before expiry; WebSocket connects with a single-use ticket from `/realtime/ticket`.
- **Real-time reconcile (AR-2)**: per item, separate counters for `version` and `computed_version`: `≤ cached` drop, `= cached+1` apply, `> cached+1` apply and refetch the row; `board.bulk_changed` → re-query page; reconnect → `/changes {since_seq}`; `invalidate` triggers targeted refetch; membership-changing edits (value used by current filter/group) trigger a debounced re-query of the current page (8.1).
- Computed columns show a subtle pending shimmer when `computed_pending` until the event arrives.
- Permissions: `GET /boards/{id}/schema` returns caller capabilities; UI hides disallowed controls (server remains the authority).

## 9.4 Performance
- Code-split per route and per heavy feature (dashboards/ECharts, automations, rich text).
- Grid renders only visible cells; column renderers are memoized pure components; 5,000 rows render ≤ 2.5 s p95 (AC-D1-1) — measured in Playwright perf test with a seeded board.

## 9.3a Entity store & reconciler (DX-1, DX-2, DX-3, DX-19)
- **One copy per item**: `items[id] = {base: {name, values, group, position}, version, computed, computed_version, pending: Op[]}`. Table pages, kanban lanes, search results and the item page hold only **ordered id lists + aggregates**; they render from the entity store. WS events, `/changes`, `items:fetch` and mutation responses write only to the store.
- **Confirmed base + pending-ops overlay**: displayed value = `base` with `pending` ops applied in order. An op is `{mutation_id, item, column, kind: set|add|remove|move, payload}`.
  - Remote event: updates `base` (by the version rules in 05 §5.3) — never touches `pending`.
  - Mutation response: sets `base` to the returned values/version, removes that op.
  - Mutation error: removes that op (no snapshot restore) + toast (AC-B6-6).
  - **Own echo**: every PATCH carries a client `mutation_id`; the server stores it in the outbox payload and echoes it in the WS envelope; the reconciler drops the echo if the response already arrived (or applies it as the confirmation if the event arrives first).
  - Multi-value cells keep `add/remove` ops, so remote adds and local adds compose (AC-B6-7).
  - A property-based Vitest suite interleaves ops, events and responses in random orders and asserts convergence to the server state.
- **Subscribe-then-load**: on board open the client subscribes to `board:{id}` **first** and buffers events, then calls `GET /schema` and `POST /query`, both returning `as_of_seq`; buffered events are replayed through the version rules (stale ones drop automatically). `GET /schema`/`POST /query` also return `as_of_xmin`, which is the initial reconnect cursor; each `/changes` response advances it (DX-3, FR-1).
- **Batched refetch (DX-4)**: gaps, `invalidate`, `/changes` and membership changes enqueue ids into a 100 ms microbatch → `POST /boards/{id}/items:fetch {ids ≤ 200, columns}`.
- **Optimistic aggregates (DX-18)**: on optimistic edits/moves the client adjusts group/lane counts and sums by the old→new contribution; server aggregates replace them on the next query response (AC-D5-1, AC-B12-1).
- **Permission events (DX-19)**: `permission.changed` → refetch `/schema` capabilities; `access_revoked` → drop pending ops for that board, show "You no longer have access", unsubscribe (AC-F7-2); capability downgrade switches cells to read-only (AC-F7-5). Vitest cases for both.

## 9.3b Virtualized grid data loading (DX-11)
The first `POST /query` response returns, for the current view: group headers with counts and summaries, and the **ordered id list** for the whole filtered result (ids only; chunked ≤ 20,000 ids per response to stay under 1 MiB; more chunks fetched immediately). Rows are hydrated by visible window via `items:fetch`. This makes scroll positions index-addressable with collapsed groups. Prototype and Playwright perf test (5k rows) in Milestone 1.

## 9.3c Column registry & contracts (DX-12, DX-13, DX-16)
- Client `columnRegistry[type] = {Cell, Editor, FilterInput, format, parse, applyOp, operators}`; value/settings TS types are **generated** from per-type JSON Schemas exported by the Python codecs (`ColumnValue` discriminated union).
- A shared golden fixture `contracts/column-display.json` (value + settings + tz → display text) is asserted by pytest and Vitest.
- Server→client WebSocket messages are Pydantic models exported as `contracts/ws-messages.json` (JSON Schema) and codegen'd to TS; CI fails on drift of `openapi.json` / `ws-messages.json` and on breaking changes (`oasdiff`).
- View and widget settings (form questions, kanban, chart, number…) are Pydantic models exported the same way.
- `web/packages/shared` (design tokens, formatters, API client) is the only code the public form bundle imports; a bundle check asserts no auth code in it.

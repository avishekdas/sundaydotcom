# 08 — View Queries, Computed Values, Search, Dashboards

## 8.1 View query compiler
`POST /boards/{id}/query` body: `{view_id?, filter, sort, group_by, search, person, columns[], cursor, limit, include_summaries}`.
Pipeline: validate against board schema → build a **query plan** (pure Python, unit-tested) → render to parameterized SQL → execute via Data API → shape rows.
- Each column type codec provides `sql_filter(op, value) -> (sql, params)`, `sql_sort_key()`, `sql_aggregate(fn)`. Example numbers `>`: `(i.values->>:col)::numeric > :v`; status `is any of`: `(i.values->'c'->>'l')::int = any(:labels)`; people contains: `i.values->'c'->'p' @> :jsonb_arr`; connect contains: `exists (select 1 from tl.item_links …)`; formula/mirror: on `i.computed` (full-visibility viewers) or per-viewer path (8.3).
- Filters are AND/OR groups (≤ 10 rules), compiled to nested boolean SQL. Visibility predicate (07 §7.2) always ANDed for `row_visibility='related'` boards.
- Search (D2.1) compiled as `items.name ilike` + text-ish values `ilike` over visible column ids, plus subitem match returning parent.
- Grouping: groups (default) → order by group position; group-by column → `case`/bucket expression; buckets ordered per D2.5.
- **Summaries** (B12) computed by a second statement: `select group_key, <aggregates per visible column> from (filtered set) group by rollup(group_key)`; status distributions via `jsonb_object_agg` of counts.
- **Paging**: keyset on `(group_order, position, id)`; first response returns counts per group and summaries; subsequent pages rows only.
- **Same results client vs server (D2.7)**: P1 decision — the server always evaluates filters (single implementation); the client only applies optimistic edits locally and re-queries when a local edit may change membership (debounced). This removes the dual-implementation risk entirely.
- Guard rails: `statement_timeout = 10s`, row-width-aware page size (03 §3.9).

**Performance budget (NFR-P1/P2)** at 5,000 items: board scan via `items_board_list` (~5k rows × JSONB) + filter/sort ≈ 30–80 ms in Postgres at ≥ 1 ACU; Data API ≈ 30–60 ms per call (≤ 2 calls); Lambda ≈ 20–50 ms warm → ≈ 150–300 ms first page.
- Status/People/Dropdown filters compile to containment (`values @> :json`) so the composite GIN index can apply (AR-20, PERF-18); numeric/date range and text filters use `->>` casts on the board-scoped scan.
- **S-1 outcome (2026-10-25, `spikes/s1/REPORT.md`)**: composite GIN kept; single-pass extraction measured **slower** than direct operators and is NOT used; `item_sort_keys` not needed; 100k first page ≈ 0.5 s at 1 ACU.
- ~~**Single-pass extraction (PERF-9)**~~ (rejected by S-1): the compiler extracts all needed columns once per row with `cross join lateral jsonb_to_record(i.values) as r("deal_value" text, "deal_stage" jsonb, …)` (identifiers are validated column ids, quoted), then filters/sorts/projects on `r.*`; avoids one TOAST decompression per expression. `values`/`computed` use lz4 compression; long text lives in `item_text` so documents usually stay inline (< 2 KB).
- **Board search (PERF-14)** uses `search_documents` filtered by `board_id` (trigram GIN on title/body), merged with a live `ilike` over the current page only to cover indexing lag.
- At 100k items (rows partly TOASTed) sort/summaries/search are the risk. **Spike S-1 (Milestone 0, gating)**: 100k and 20k items × 60 columns at 0.5/2/4 ACU, cold and warm cache, through the real Data API; measures **side by side** (PERF-10): baseline JSONB scan, single-pass extraction + lz4 + item_text, `item_sort_keys` table, composite GIN on/off (write p95 too), min ACU 1/2. Target proposed to the user (pending decision): NFR-P1 800 ms first page holds up to 20k items; at 100k items first page ≤ 3 s with summaries delivered by a separate cached call. Pre-agreed fallbacks: (1) narrow `tl.item_sort_keys(board_id, column_id, num numeric, txt text, ts timestamptz, item_id)` maintained in the same write statement for columns used by saved views' sort/group (no runtime DDL); (2) summaries cached per (view, `boards.data_version`); (3) higher min ACU; (4) RDS Proxy + psycopg (ADR-002 fallback). Read replicas do **not** help (Data API is writer-only, AR-5).

## 8.2 Computed values (ADR-009) — revised after OPS-1, PERF-5/6/7/8
Three execution modes, one formula AST (Python evaluator and SQL compiler, both checked against `contracts/formula-golden.json`):
1. **Inline (same item)**: formulas whose inputs are only the item's own columns are evaluated inside the mutation statement (03 §3.5) → no async lag (AC-C17-1).
2. **Async (cross item)**: mirrors and formulas over mirrors. The mutation statement upserts the **dirty set** `tl.recompute_pending(item_id, requested_seq)` for the changed item; the `dispatcher` λ (on `item.*` events; 02 §2.7) resolves **dependents** — items linking to the changed item (reverse links) — and upserts them into `recompute_pending`, then sends a nudge to `recompute.fifo` (group `comp:{itemId}`, dedup id `comp:{itemId}:{requested_seq}` — never time buckets). The recompute λ **claims with a lease** (FR-2): `update tl.recompute_pending set claimed_until = now() + interval '60 s' where item_id = :id and (claimed_until is null or claimed_until < now()) returning requested_seq`, reads current state, computes, and **in the same statement that writes** `computed`, `computed_version`, `computed_source_seq` deletes the dirty row only `where requested_seq = :claimed_seq` (a newer request keeps it). A crash leaves the row with an expiring lease; the 1-minute reaper re-nudges rows whose lease expired. Nothing is lost (OPS-1, PERF-5, FR-2); fault-injection test kills the worker between compute and write. A burst of N changes collapses to ≤ 2 evaluations.
3. **Set-based (bulk)**: formula column created/edited, mirror settings changed, nightly TODAY() refresh, bulk operations and imports run as chunked SQL `update tl.items set computed = computed || <compiled expressions> where board_id = :b and id between :lo and :hi` (≈ 5k rows per statement) from `job-worker`; mirrors as grouped joins `update … from (select from_item_id, <agg> … group by 1)`. A 100k board recomputes in ≈ 20 statements instead of 100k messages (AC-C17-5 by 00:15) (PERF-6).
- **Depth-2 mirrors (PERF-7)**: computed from the **leaf set** with `DISTINCT` leaf items via a 2-hop join (no "sum of sums" double counting; averages over leaves). Second-hop targets are put into the dirty set directly by the recompute λ, so N first-hop changes collapse into one target evaluation. `item.computed_changed` events for hop ≥ 1 are `realtime:false`; one coalesced `board.bulk_changed`/invalidate per board per second is sent instead.
- **Decomposable partial aggregates (PERF-8)**: for sum/count/min/max/avg/earliest/latest, `computed[col]` stores `{"v": total, "by": {"<board_id>[/<hop2_board_id>]": {"s":…, "n":…, "min":…, "max":…}}}`. A partial-visibility viewer's value = fold over the keys of boards they can see (pure JSON, no joins), and `partial` = some key not visible. Only `distinct` and `median` fall back to the per-viewer join path — **and any contributor board with `row_visibility='related'` (Activities)**, which is never folded per board because its rows are visible individually (D-020, FR-4); such contributors always use the per-viewer join through `VisibleItems`.
- **Drift checker** (OPS-1): every 15 min, 200 sampled items recomputed and compared; mismatches repaired; `computed.drift` alarm.
- **Archived/trashed** contributors excluded (A11.7); restore marks dependents dirty.

## 8.3 Per-viewer computation (D-012, D-015) — revised
- Mirrors: fold of `computed[col].by` over visible board keys (PERF-8); `distinct`/`median` use the join path `(select … from tl.item_links l join tl.items t on t.id = l.to_item_id where l.from_item_id = i.id and l.column_id = :rel and l.to_board_id in (select … from jsonb_array_elements_text(:visible::jsonb)))` using `to_board_id` (PERF-20).
- Formulas over mirrors: the formula SQL compiler takes the per-viewer mirror expression as input, so filter/sort/paging happen in Postgres (AR-15).
- Perf test: 20k items, partial viewer, filter + sort on formula over mirror ≤ 2 s p95.
- **Formula → SQL safety (SEC-10)**: the compiler emits only allow-listed function templates; every literal becomes a named bind parameter; column references are validated against the board schema and passed as parameters (`values ->> :p1`); compiled queries run with `statement_timeout` under a read-only DB role; fuzz/property tests with a malicious-literal corpus.

## 8.4 Search (ADR-007)
- `search_documents` maintained by the indexer from item/board/dashboard events (≤ 5 s freshness, A7.4). Item body = display text of text-like columns.
- Query: `websearch_to_tsquery('simple', q)` match OR trigram similarity on title (fuzzy, A7.3), ranked `ts_rank` + exact/prefix boosts + recently-visited boost (from a small per-user `recent_items` table), limited to `board_id = any(visible_boards)` and row-visibility predicate; max 50 results grouped by type. Target ≤ 500 ms p95 server time.

## 8.5 Dashboards
- `POST /dashboards/{id}/data` computes all widgets for the caller in one Lambda invocation (parallel SQL statements via thread pool, Data API is HTTP).
- Each widget type has a compiler to SQL aggregates over the union of connected boards (column ids per board from widget settings), applying widget filter ∧ dashboard filter ∧ visibility (H7). Periods/buckets in account tz (D-017) via `date_trunc(..., ts at time zone :acct_tz)`.
- Widgets referencing missing columns → `needs_attention` (G1.15a). Hidden boards reported as count (AC-H7-1).
- **Widget result cache (PERF-12)**: results cached (DynamoDB, TTL 10 min) keyed by `(widget id, settings hash, visible-board-set hash, max board_changes.seq of each source board)` — viewers with the same visibility share entries; a write only invalidates by advancing seq (no hot counter row).
- Real-time: `dashboard:{id}` channel receives `invalidate` (debounced 5 s) when any connected board changes; clients refetch with 0–2 s jitter and only while the dashboard tab is visible.
- Funnel: current-stage counts, conversion n/(n−1) (H4). Leaderboard: full credit per person.

## 8.6 Formula semantics (golden table seed, DX-15)
| Case | Result |
|---|---|
| empty numeric input in arithmetic | treated as 0 in `+ - * /`, ignored by SUM/AVERAGE/MIN/MAX |
| `x / 0` | error `#DIV/0` (cell "!"), does not propagate as 0 |
| text in arithmetic | numeric parse if parseable (`"12"`) else error `#TYPE` |
| comparison of mixed types | text comparison of display values |
| ROUND(x, n) | half away from zero (Python `Decimal.quantize(ROUND_HALF_UP)`, SQL `round(numeric)`) |
| decimals | `numeric`/`Decimal`, never float |
| dates | `DAYS(a,b)` = calendar days b−a; `TODAY()` = account-tz date; `ADD_DAYS` returns date; `WORKDAYS` excludes Sat/Sun (holidays P2) |
| booleans | checkbox → TRUE/FALSE; IF condition with empty → FALSE |
| status/dropdown | label text (dropdown labels joined ", ") |
| errors inside IF branches | only the evaluated branch can error |
Delivery: Python evaluator with the formulas milestone; formula→SQL compiler with the per-viewer visibility milestone. Both are checked against `contracts/formula-golden.json`.

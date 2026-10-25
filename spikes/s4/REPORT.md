# Spike S-4 — Recompute & per-viewer visibility

**Date:** 2026-10-25 · **Path:** Lambda (python3.13 arm64) → Data API → Aurora PG 18.6 Serverless v2 (0.5–2 ACU), us-east-1.
**Data:** 20,000 contacts (board 30); 40,000 deals on board 40 (visible to the test viewer, 75 %) and board 50 (hidden, 25 %), every contact linked to 2 deals; 2,000 accounts (board 60) each linked to 10 contacts.
**Design under test (arch 08 §8.2–8.3):** decomposable partial aggregates in `computed` (`{"v": total, "by": {board: {s, n}}}`), set-based recompute, dirty set with lease claim (FR-2), depth-2 mirror from the DISTINCT leaf set (PERF-7), per-viewer value = fold over visible board keys (PERF-8).
**Correctness checked locally first** (`test_bench4_sql.py`): fold path == join path for a partial viewer (same rows, same order); depth-2 account totals == distinct-leaf reference; drift = 0 after bulk edit + recompute.

| Measure | Result | Threshold |
|---|---|---|
| Set-based full recompute, 20,000 contacts (4 chunks of 5k) | **822 ms** | — |
| Depth-2 recompute, 2,000 accounts via 20,000 contacts / 40,000 deals | **266 ms** | — |
| Per-viewer filter + sort, partial viewer, fold path (12,000 rows) | 179 p50 / **227 p95 ms** | ≤ 2 s p95 |
| Per-viewer filter + sort, join path (reference) | 258 p50 / 293 p95 ms | — |
| Full-visibility viewer on materialized value | 80 p50 / 97 p95 ms | — |
| Bulk: 1,000 deal edits (one statement, dirties affected contacts) | **57 ms** | — |
| Incremental recompute of the 1,000 dirty contacts (3 lease-claim rounds) | **160 ms** | ≤ 2 min |
| Drift (stored vs fresh), after full recompute and after bulk | **0 / 20,000** | 0 |

## Verdict: **PASS** — no fallback needed
- The partial-aggregate fold is ~25 % faster than the join path and returns identical results → keep both as designed (fold by default; join for distinct/median and row-visibility contributors, FR-4).
- Set-based recompute makes bulk, nightly and structural recomputes cheap (a 100k board ≈ 4–5 s), confirming PERF-6; per-item async recompute is only for single edits.
- Lease-claim dirty set works in one statement per round via the Data API (FR-2).

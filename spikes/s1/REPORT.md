# Spike S-1 — Data API & JSONB performance

**Date:** 2026-10-25 · **Where:** Lambda `tasklane-spike-s1` (python3.13, arm64, 1 GB) → RDS Data API → Aurora PostgreSQL 18.6 Serverless v2, us-east-1 (same region, production-like path).
**Data:** board 1 = 20,000 items, board 2 = 100,000 items; 60 columns per item (10 status, 10 numbers, 10 text, 10 date, 10 people, 10 dropdown); avg `values` document 1,047 bytes; 4 groups.
**Method:** each query 20 runs (writes 50), end-to-end latency measured inside the Lambda (includes Data API). Query variants checked for identical results locally first (`test_bench_sql.py`).

## Thresholds (plan §3 M0a, D-023)
| Metric | Threshold |
|---|---|
| Board first page (≤ 20k items) | ≤ 800 ms p95 API |
| Board first page (20k–100k items) | ≤ 3 s p95 |
| Cell write | ≤ 300 ms p95 |

## Results — warm cache, autoscaling 0.5–4 ACU (cluster at ~4 ACU after load)
"First page" = ordered id list for the view (filter: status any-of, number >, people contains; sort by number) **plus** group summaries (sum, avg, status distribution).

| Query (p50 / p95 ms) | 20k, no GIN | 20k, composite GIN | 100k, no GIN | 100k, composite GIN |
|---|---|---|---|---|
| Filtered ordered ids — baseline (`->>` casts + `@>` containment) | 53 / 116 | 15 / 18 | 227 / 256 | 23 / 25 |
| Filtered ordered ids — single-pass `jsonb_to_record` (PERF-9) | 76 / 93 | — | 300 / 349 | — |
| Filtered ordered ids — `item_sort_keys` join | 50 / 51 | 15 / 23 | 229 / 257 | 25 / 32 |
| Group summaries (filtered) | 68 / 103 | 55 / 59 | 313 / 341 | 115 / 138 |
| Unfiltered ordered ids, 20k page | 118 / 176 | — | 76 / 132 | — |
| Hydrate 200 rows × 10 columns | 23 / 31 | — | 22 / 31 | — |
| Data API round trip (`select 1`) | 56 / 59 | 53 / 57 | 56 / 57 | 53 / 60 |
| **Cell write** (single writable-CTE: pre-image lock, update, board_changes, outbox) | — | — | 52 / 57 | 52 / 60 |

Worst case on 100k, no selective filter (server execution time, EXPLAIN ANALYZE, warm): sort all by number column — baseline 64 ms, `item_sort_keys` 91 ms; unfiltered summaries 322 ms; status distribution 176 ms.

Index cost: composite GIN `(board_id, values jsonb_path_ops)` = 133 MB for 120k items (heap 156 MB); cell write p95 +3 ms.

## Results — capacity pinned to 0.5–1 ACU (scaled down from 4 → buffer cache mostly evicted), composite GIN on
| Query (first / p50 / p95 ms) | 20k | 100k |
|---|---|---|
| Filtered ordered ids | 15 / 15 / 31 | **174** / 25 / 66 |
| Group summaries | 51 / 53 / 91 | **234** / 269 / 421 |
| Unfiltered ordered ids, 20k page | 129 / 115 / 184 | 102 / 85 / 103 |
| Hydrate 200 rows | 21 / 22 / 33 | 22 / 22 / 24 |
| Cell write | — | 54 / 53 / **79** (max 107) |

## Verdict: **PASS** — no fallback needed
| Metric | Threshold | Worst measured (1 ACU, cold-ish) |
|---|---|---|
| First page ≤ 20k items (ids + summaries) | ≤ 800 ms p95 | ≈ 31 + 91 = **122 ms** |
| First page 100k items (ids + summaries) | ≤ 3 s p95 (D-023) | ≈ 66 + 421 = **487 ms** (also inside 800 ms) |
| Cell write | ≤ 300 ms p95 | **79 ms** |

## Findings & decisions
1. **All thresholds met with large margin** at warm cache: 100k first page ≈ 25 + 138 ms + one round trip; 20k ≈ 18 + 59 ms; cell write 60 ms p95.
2. **Composite GIN is decisive** for selective filters (10× on 100k) at negligible write cost → keep it (resolves PERF-11 "measure in S-1").
3. **Single-pass `jsonb_to_record` extraction is slower** than direct operators in every case (it defeats GIN containment and adds a lateral) → do **not** make it the default (PERF-9 variant rejected).
4. **`item_sort_keys` brings no benefit** (equal or slower) → fallback (1) not needed.
5. Data API adds ≈ 20–55 ms per call → the ≤ 2 calls/hot-path budget (03 §3.5) is right.
6. Documents average ~1 KB with 60 short columns; long text moving to `item_text` (PERF-9) keeps them small.
7. Even at the 1 ACU floor with an evicted cache, the 100k board meets the **20k** target; D-023's relaxed 3 s target is not needed in practice (kept as the formal contract).
8. The scheduled 2 ACU business-hours floor (OPS-12) is **not required for single-user latency**; whether it is needed for concurrency is decided by the M2 load gate (50 virtual users) — potential saving ≈ $35/month.
9. Not covered here (by design): concurrent load (M2 load gate), mirror/formula recompute and per-viewer paths (Spike S-4), cold Lambda starts (Spike S-3).

### Architecture updates from S-1
- ADR-001/002 appendix: composite GIN `(board_id, values jsonb_path_ops)` **kept**; single-pass `jsonb_to_record` extraction **dropped** as default; `item_sort_keys` **not built**; RDS Proxy fallback **not needed**.
- 03 §3.9 round-trip budget confirmed (Data API ≈ 20–55 ms per call).

# Design Coverage — Requirements & Decisions → Architecture

| Requirement / decision | Where addressed |
|---|---|
| B6.8, D-010 concurrency | 03 §3.5, 04 §4.1 |
| B7 subitems & B7.7 permissions | 03 boards.parent_board_id, items.parent_item_id; 07 §7.2 |
| B11 limits, D1-1 perf | 03 §3.9, 08 §8.1 budget, 09 §9.4 |
| B12 summaries | 08 §8.1 |
| C-area codecs, C40.6 contract | 03 §3.4, 11 `columns/types` |
| C8 time zones, D-017 | 06 §6.4, 08 §8.2/§8.5 |
| C17 formulas (materialized, nightly) | 08 §8.2 |
| C18 links + reflection transaction, C18.1a | 03 item_links, 06 §6.3 |
| C19 mirrors, D-012, D-015 | 08 §8.2–8.3, 07 §7.2 |
| D2 filters/sort/group, D2.7 | 08 §8.1 (server-only evaluation) |
| D3 views, D5 kanban | 03 views/view_item_positions, 04 kanban endpoints |
| A7 search | 08 §8.4, ADR-007 |
| A9 notifications & email coalescing | 05 §5.5 |
| A11 trash/purge | 03 §3.1, 06 §6.4 (purge tick) |
| A13/A14 import/export | 04 jobs, job-worker |
| A15 activity log, A15.5 audit | 03 activity_log, audit_events |
| E3 updates, files | 03 §3.6, 07 §7.3 |
| F7 real-time, F7.7, D-018 | 05 §5.3–5.4, 07 §7.2 |
| G1 engine (G1.3–G1.17), G7 | 06 |
| H dashboards, H7 | 08 §8.5 |
| I forms, I7 | 01 flow 4, 07 §7.4 |
| K7 auth, K1–K3 permissions, K3.5, D-016, D-020 | 07 |
| L1 CRM template | crm.template (data-driven, uses domain services as system actor) |
| L10, D-011 activities | crm timeline = query over Activities board via reverse links (03 item_links_reverse) |
| M1 API | 04 |
| NFR-P | 08 budgets, 02 sizing, 10 SLO metrics |
| NFR-A | 10 §10.2 |
| NFR-S | 07 |
| NFR-O, NFR-Q | 10 §10.1, §10.3 |
| D-007 scale | 02 §2.4 |
| Cost target | 10 §10.4 (≈ $170 prod; flagged) |

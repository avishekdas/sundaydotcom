# Plan Review Log

## Round 1 — plan council (3 independent reviewers, 2026-10-25)
| Reviewer | Verdict | Findings |
|---|---|---|
| Test architect (TDD) | 55 % ready | 4 Blockers (TP-1…4), 10 Major, 4 Minor |
| Delivery & risk lead | ~60 % ready | 2 Blockers (DL-1, DL-2), 10 Major, 8 Minor |
| Principal engineer | ~60 % ready | 1 Blocker (PE-1), 12 Major, 5 Minor |

| Theme | Findings | Resolution in plan v1.0 |
|---|---|---|
| Realistic effort | DL-1, PE-12 | 41–51 weeks + 15 % buffer, ranges per milestone, re-baseline after M1; M4 split into M4a/M4b |
| Earlier usable releases | DL-2 | R1 dogfood after M3, R2 CRM alpha after M7, R3 = P1 |
| Spikes gate the code they shape | DL-3, PE-1, PE-2, TP-10 | M0a scaffold + schema + spikes with thresholds & fallbacks before Mutation builder; S-2 split (S-2a M0a, S-2b first story of M1); S-4 recompute spike |
| System tests only use delivered features | TP-1…4, DL-6, DL-7, TP-13 | L1-spec-core fixtures; export out of M4; M6 after M5; AC-G6-1 split; sub-steps 1a/1b, 4a/4b tagged with driver; generated step 7 |
| Every AC owned exactly once | TP-5, TP-18, DL-14, DL-15 | `ac-ownership.md` generated and checked: 194/194, no duplicates; K6 in M8; L3/L2 button in M7 template story |
| TDD enforced, not stated | TP-6, TP-7, TP-15, TP-16 | red-run evidence check, AC-coverage gate, xfail(strict) kickoff steps, differential + metamorphic tests, frontend layers, mutation testing |
| Deterministic, fast tests | TP-8, TP-11, TP-12, TP-17, DL-17 | Tier A asserts order/outcome only; fixed chaos seeds on PR, 500 nightly; flake policy; CI time tracking |
| Gates measurable | TP-9, TP-14 | per-milestone load/NFR table; 14-day SLO burn; cost gate ±10 % |
| Dependencies corrected | DL-5, DL-10, DL-11, DL-13, DL-16 | edit_assigned → M2, reassignment → M5; state model in 0001; search → M3, Number widget → M4b; single parallel lane; files → M3.5 |
| Platform obligations scheduled early | PE-3…PE-11, PE-13, PE-16…18, DL-8, DL-9 | 3 accounts + baseline + all stacks in M0b; migrate λ & long DDL; durable publish; deploy safety; DB roles in 0001; VisibleItems in M1; job framework M2; bulk shaping M2; restore drills at R1/R2/R3; polling & search fallbacks; Tier B test identities; staging-only steps; lead-time checklist |
| Ops readiness per milestone | PE-7, DL-19 | DoD: alarms + runbook + panel + DLQ policy per new component; risk register with owners/triggers/burn-down |
| Customer decisions & reviews | DL-12, DL-20, PE-18 | decision calendar; 2-day review time-box |
| Gold-plating | DL-18 | breached-password check etc. labelled hardening → M9 |
| Template atomicity | PE-15 | resumable manifest job with compensation |
| Cold start re-checks | PE-14 | Power Tuning at M3 and M8 |

## Round 2 — confirmation pass (test architect, 2026-10-25)
Verdict: 82 % ready; no Blockers; TP-2, TP-5 partial; 3 Majors.
| ID | Resolution |
|---|---|
| NB-1 | AC-L1-1 → M8, AC-K3-5 → M9, AC-A13-3 → M5; AC-C17-6 split 6a (M4b) / 6b (M9); AC-G6-1 split 1a (M5) / 1b (M7); `requires` table + CI rule (owner ≥ required milestones) |
| NB-2 | R1 declared after M3.5 (includes files + CSV import-lite) |
| NB-3 | M3.5 system test added (file upload/download, 2,000-row import) |
| Minor | red runs tracked by test id + branch, CI on every push; Cognito test user in M0b; arch 10 §10.3 seeds aligned |
Projected readiness after fixes: ≈ 90 %+. Plan v1.1 is approved for execution subject to the user's decisions D-022…D-024.

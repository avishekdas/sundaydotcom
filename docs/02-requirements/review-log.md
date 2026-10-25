# Requirements Review Log

## Round 1 — independent Product Owner review (2026-10-24)
Verdict: not ready (55%). 4 Blockers, 21 Majors, 10 Minors.

| ID | Sev | Resolution |
|---|---|---|
| PO-1 | Blocker | D-010; B6.8 rewritten; AC-B6-7; M1.2 + AC-M1-2; C18.8 |
| PO-2 | Blocker | G1.3 step outputs `{step[n].item}`, G1.17; automation 2 rewritten; AC-L4-3 |
| PO-3 | Blocker | D-011 activity = Activities-board item; L10.4/4a/4b; automation 6 retired; AC-L10-4/5 |
| PO-4 | Blocker | D-012; C19.5, C17.7; AC-C19-2 |
| PO-5 | Major | Owner←lead_owner in automation 2; north-star step 4b; exact numbers in step 6 |
| PO-6 | Major | North-star step 2 and AC-I1-1: visible ≤ 2 s, status ≤ 5 s |
| PO-7 | Major | G1.3 trigger/step variables, empty-variable rule, G1.3a; automation 5 uses activity start |
| PO-8 | Major | G3 is empty/not empty incl. Connect; G1.13 serialization; AC-G1-7 |
| PO-9 | Major | G1.14 ordering; AC-G1-8 |
| PO-10 | Major | F1.5 reassignment on deactivation; G1.16; AC-F1-3 |
| PO-11 | Major | D-013; A11 Duplicate item P1; A9/A10 marked P1 per D-013 |
| PO-12 | Major | AC-L1-1 exact manifest (7 boards, 3 subitem boards, 1 dashboard, 14 automations); #8 split 8a–c |
| PO-13 | Major | B6.5a–e; AC-B6-8 |
| PO-14 | Major | G1.15 "Needs attention"; AC-G1-6 |
| PO-15 | Major | A11.5–A11.8; AC-A11-4/5 |
| PO-16 | Major | C8.1–C8.4; AC-C8-1..3; A16 AC |
| PO-17 | Major | C17.5 materialization + nightly; AC-C17-4/5 |
| PO-18 | Major | F7.2 computed-value event; AC-C19-1 extended |
| PO-19 | Major | F7.7 ≤ 60 s, identity-only tokens; AC-F7-5 |
| PO-20 | Major | B7.7 subitem board inheritance; AC-B7-4 |
| PO-21 | Major | K3 activity column + K3.4; AC-L10-3 rewritten |
| PO-22 | Major | K2.1 board invite grants access; AC-K2-1/2 |
| PO-23 | Major | C18.6 replace on single side, C18.7 no reflection for multi-board; AC-C18-3 |
| PO-24 | Major | A10 skip/dedupe/no-op on empty; automation 9b on email change |
| PO-25 | Major | T2 excludes computed columns; reflection changes fire T2 |
| PO-26 | Minor | B7.6 reworded |
| PO-27 | Minor | C7.3 teams rejected in P1 |
| PO-28 | Minor | C4 min/max setting; AC-C4-2 |
| PO-29 | Minor | I3.1 presigned uploads; I7.1 explicit challenge-then-429 order; I7.3 limits |
| PO-30 | Minor | B9.4 rewritten; AC-B9-3 |
| PO-31 | Minor | H4 funnel current-stage; leaderboard full credit |
| PO-32 | Minor | ACs added to all P1 items; traceability.md created (190 ACs) |
| PO-33 | Minor | A15.5 structure + P1 audit event list |
| PO-34 | Minor | D5.6/D5.7; AC-D5-3 |
| PO-35 | Minor | K7.1 per account+IP lockout; AC-K7-2 rewritten |
| note | — | Qualified not done (D-014); lead_contacts marked deliberate (D-014) |

## Round 2 — confirmation pass (2026-10-24)
Verdict: 78%. 28 Yes / 7 Partly / 0 No; 13 new issues (NEW-1 Blocker, NEW-2…7 Major, NEW-8…13 Minor).

| ID | Resolution |
|---|---|
| NEW-1 | D-015; C17.7 rewritten; AC-C17-6 |
| NEW-2 | G1.8 resume-from-step, per-step idempotency, no rollback; AC-G1-9 |
| NEW-3 | L10.5 rewritten (all Related items; T7 per linked board) |
| NEW-4 | D-016; L10.4b; K3.4; AC-L10-6 |
| NEW-5 | C18.1 link + reflection in one transaction; C18.1a |
| NEW-6 | D-017; C8.3/C8.4 split; north-star step 3 "today in account tz"; dashboard periods by Expected Close Date |
| NEW-7 | C18.1a; 9a/9b condition "Contacts is empty"; AC-L4-3 extended |
| NEW-8 | automation 5 condition (never moves backwards) |
| NEW-9 | G1.14 narrowed |
| NEW-10 | G1.15 deactivated recipients skipped |
| NEW-11 | C19.5 per-viewer target ≤ 2 s p95 @ 20k; visibility at every hop |
| NEW-12 | I7.2 slots counted and purged after 24 h |
| NEW-13 | A1 notification grouping |
| Partly: PO-5 | north-star step 4a; dashboard date column named |
| Partly: PO-12 | G6 count fixed to 14 |
| Partly: PO-13 | B6.5c permission rule |
| Partly: PO-14 | G1.15a for widgets/views/kanban/forms; AC-G1-10 |
| Partly: PO-19 | F1.3 deactivation ≤ 60 s |
| Partly: PO-22 | K3.2 "except as granted by K2.1" |
| Partly: PO-10 | AC-G1-3 rewritten (owner loses access) |
| PO-32 note | traceability regenerated with area mapping |

## Round 3 — final check (2026-10-24)
Verdict: 88%, no Blockers. All NEW and Partly items resolved except NEW-8 (Partly). Four Majors:
| ID | Resolution |
|---|---|
| A | D-018; F7.2a; AC-F7-6 |
| B | D-019; G1.3b; AC-G1-11 |
| C | D-020; K3.5; AC-K3-5 |
| D / NEW-8 | G3 date-vs-variable and OR-with-empty conditions (automation 5 now catalog-expressible) |

Reviewer's projected readiness after these fixes: ~93% (≥ 90% gate met). Requirements frozen at v1.0; further changes go through the decision log.

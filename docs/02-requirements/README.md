# Requirements — Index & Conventions

**Version:** 1.0 — approved for architecture (3 PO review rounds; see review-log.md) · **Source scope:** `../01-features/feature-inventory.md` v1.0 · **Decisions:** `../00-decision-log.md`

Working name for the product in docs and code: **Tasklane** (original name; no monday.com branding — D-009).

## North star

> One organization of up to 500 people runs its whole sales pipeline — lead captured → qualified → contact + deal → won → client project — and its everyday team work on boards, collaborating in real time, on a serverless AWS deployment it owns, with no dependency on monday.com.

**North-star scenario (used as the end-to-end acceptance test at every milestone, growing as features land):**
1. Admin signs in, creates the CRM workspace from the CRM template (L1).
2. A prospect submits the public lead form (L3) → the Lead appears for every viewer of the Leads board within 2 s (F7) and its Status becomes *New Lead* within 5 s (automation 3).
3. A rep logs a call (dated now) on the lead's timeline (L10) → it is stored as an Activities-board item linked to the lead (D-011) and *Last interaction* = today in the account timezone (automation 5, D-017).
4a. Rep assigns himself as the lead's Owner.
4. Rep (now lead Owner) sets Status = *Qualified* → lead moves to *Qualified leads* (automation 1); a Contact (linked to the lead) and a Deal (linked to that Contact, Owner = lead Owner) are created (automation 2).
4b. Rep sets the Deal's Deal Value = 40,000 and Expected Close Date = today.
5. Rep drags the deal across Pipeline Kanban stages (L9) to *Won* → deal moves to *Closed Won* (automation 8), subscribers are notified (automation 10), a Client Project is created and linked (automation 11).
6. Sales Dashboard (L24), starting from the template's sample data plus this deal: Annual Target *Actual* increases by exactly 40,000; the current month's bar in *Actual revenue by month* increases by 40,000; the rep's Leaderboard total increases by 40,000; the Funnel *Won* count increases by 1.
7. A Viewer-role user can see all of this but cannot edit (K1/K3).

**North-star metrics (targets for P1 release):**
| Metric | Target |
|---|---|
| Scenario above passes end-to-end in CI against a deployed stage | 100% |
| Board with 5,000 items: first meaningful paint of table view | ≤ 2.5 s p95 |
| Cell edit → persisted + visible to other viewers | ≤ 1 s p95 save, ≤ 2 s p95 fan-out |
| Automation trigger → action applied | ≤ 5 s p95 |
| Availability (monthly) | ≥ 99.9% |
| Monthly AWS cost at 100 active users, idle-heavy | target ≤ US$150 (estimated in Step 3) |

## Personas
| Persona | Role | Main jobs |
|---|---|---|
| Ada — Admin | Account admin | users, roles, workspaces, templates, security |
| Raj — Sales rep | Member | work leads, log activities, move deals |
| Mia — Sales manager | Member, board owner | pipeline review, dashboards, automations |
| Paul — Project manager | Member | client projects, timelines, subitems |
| Vic — Viewer | Viewer | read-only reporting |
| Gina — Guest | Guest | collaborate on a shareable board (P2) |
| Prospect | anonymous | submits the lead form |

## Conventions
- Requirement IDs extend inventory IDs: `B6.3` = 3rd rule of feature B6. Acceptance criteria are `AC-B6-1`, `AC-B6-2`…
- Every **AC** is written Given/When/Then and is directly testable; each becomes at least one automated test in Step 5.
- **P1** features: full stories, rules, ACs, edge cases. **P2/P3**: summary + key rules only (D-005); they are detailed before their milestone starts.
- "Board member" = anyone who can open the board under K2/K3. "Owner" = board owner.
- All timestamps stored UTC, displayed in the user's timezone (A16).
- "Real-time" = change pushed to connected clients without reload (F7).

## Cross-coverage
Some inventory IDs are verified by ACs of the area that implements them: D9 → AC-I1-*, AC-I3-*; L3 → AC-I1-1, AC-I7-*; L4 (and L2 flow) → AC-L4-*; F2 → AC-K3-*, AC-K1 via 09 table; F5 → AC-E3-1; C37 → AC-B7-*; L1-spec schemas → AC-L1-1, AC-L2-1.

## Files
| File | Inventory areas |
|---|---|
| `01-platform.md` | A — platform & navigation |
| `02-boards-items.md` | B — boards, groups, items, subitems |
| `03-columns.md` | C — column types |
| `04-views.md` | D — board views |
| `05-item-page-collaboration.md` | E, F — item page, updates, users, notifications, real-time |
| `06-automations.md` | G — automations |
| `07-dashboards.md` | H — dashboards & widgets |
| `08-forms.md` | I — forms |
| `09-permissions-admin.md` | K — auth, roles, permissions, admin |
| `10-crm.md` | L — CRM |
| `11-api-nfr.md` | M, O — API, non-functional requirements |
| `traceability.md` | inventory ID → requirement file → AC count (filled after review) |

## Glossary
**Workspace** container of boards/dashboards · **Board** table of items with typed columns · **Group** named, colored section of a board · **Item** a row · **Subitem** child row with its own column set · **Column** typed field · **View** saved presentation of a board (table, kanban…) · **Update** comment thread entry on an item · **Automation** trigger→conditions→actions rule · **Dashboard** collection of widgets over one or more boards · **Timeline (CRM)** chronological list of emails/activities on a CRM item.

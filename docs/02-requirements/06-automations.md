# 06 — Automations (Area G)

## G1 Engine — P1
**Story:** As Mia, I create "When Stage changes to Won, notify subscribers" without code.
**Rules**
- G1.1 An automation = board, name (auto-generated sentence, editable), trigger (type + params), conditions (0–5, AND), actions (1–5, executed in order), active flag, created_by, owner.
- G1.2 Authoring UI: sentence template with fill-in blanks (e.g. "When **Stage** changes to **Won**, notify **subscribers** with **message**"); each blank opens a picker constrained by board schema (columns of the right type, labels of that column, groups, boards, people, mapping).
- G1.3 Variables, inserted via picker; unknown variables rejected at save:
  - Item: `{item.name}`, `{item.<column_id>}` (display text in text fields; typed value when mapped to a column of compatible type), `{item.url}`, `{item.id}`.
  - Context: `{board.name}`, `{user.name}` (the user whose action triggered the run; "Automation" when chained), `{today}` (account tz).
  - Trigger-scoped: `{trigger.old_value}`, `{trigger.new_value}`; for T7 `{trigger.activity.type|title|owner|start|end|status}`.
  - Step outputs: `{step[n].item}` (the item created or found by action n of the same automation) and `{step[n].item.<column_id>}`.
  - An empty variable resolves to empty: in text it becomes "", when mapped to a column it clears/leaves empty that column; it never fails the run.
- G1.3b (D-019) Visibility-sensitive values (Mirror, Formula over Mirror) are resolved as the automation owner sees them; in notification text they are additionally resolved per recipient.
- AC-G1-11 Given Vic is a recipient of "Deal total {item.contact_deals_value}" and cannot see one contributing deal, then Vic's notification shows his visible total while Mia's shows the full total.
- G1.3a Any column type may receive a value from a compatible variable (e.g. a Date column from `{trigger.activity.start}` or `{item.<date_col>}`).
- G1.4 Field mapping (create/move item across boards): per target column choose source column, static value, or variable text; type compatibility enforced (same rules as A13 parsing).
- G1.5 Execution is asynchronous: trigger event → queued → evaluated against item state at execution time for conditions → actions applied as the automation's **actor** = "Automation: <name> (on behalf of <owner>)". Actions are authorized against the owner's permissions; if the owner lost permission, the run fails with "owner no longer has permission".
- G1.6 Changes made by automations emit normal change events (they can trigger other automations — chaining) but a run chain is limited to depth 5 and the same automation cannot fire twice for the same item within one chain (loop prevention). Exceeding → run marked "stopped: loop limit".
- G1.7 Idempotency: each trigger event has an id; an automation processes an event at most once (retries are safe).
- G1.8 Retries: transient failures retried 3× with backoff (1 s, 10 s, 60 s), then failed with error in run history (G7). A retry resumes at the first unapplied action; each action carries its own idempotency key (event id + automation id + step n), so completed actions are never repeated. A permanently failed run leaves completed actions in place and lists them in run history; there is no rollback.
- G1.9 Automations are skipped for archived/trashed items and for imports unless opted in (A13.6).
- G1.10 Who can create/edit: board owners (P1); account permission matrix later (K1 P2). Members can view the list.
- G1.11 Header "Automate / N" shows active automation count.
- G1.12 Latency target: trigger → action visible ≤ 5 s p95.
- G1.13 Runs of the **same automation for the same item** are serialized (never concurrent); later runs see the effects of earlier ones.
- G1.14 Ordering: different automations triggered by one event run independently, in no guaranteed order; each evaluates its conditions against the item state at its own execution time. Recipes must not depend on the order among automations triggered by the same event (chaining via G1.6 is allowed).
- G1.15 Broken references: on save and on each run, referenced columns, labels, groups and boards are validated (deactivated users named as notify/assign targets are skipped with a warning in run history, not treated as broken). A missing reference sets the automation to "Needs attention" (inactive), notifies its owner and board owners, and it stays inactive until someone fixes and re-activates it (also after a restore).
- G1.15a The same broken-reference rule applies to dashboard widgets, saved-view filters/sort/group-by, Kanban lane/card fields and form questions: the referencing element shows "Needs attention" (widget/question hidden from public form; view falls back to no filter on that rule) and owners are notified; restoring the entity heals it automatically for these (unlike automations).
- AC-G1-10 Given a form question mapped to a deleted column, then the public form omits the question and still accepts submissions; on column restore the question returns.
- G1.16 Ownership: board owners and Admins can change an automation's owner; deactivation requires reassignment (F1.5).
- G1.17 A6's "connect" target may be the triggering item or `{step[n].item}`; it links via a Connect column on either side.
**AC**
- AC-G1-1 Given "When Stage changes to Won, move item to group Closed Won", when Raj sets Won, then within 5 s the item is in Closed Won and the activity log actor is the automation.
- AC-G1-2 Given automation X (status A → set status B) and Y (status B → set status A), when status set to A, then the chain stops at depth limit with no infinite loop and the run is logged as "stopped: loop limit".
- AC-G1-3 Given the automation owner loses access to the board, when it triggers, then the run fails with "owner no longer has permission" and an in-app notification is sent to board owners.
- AC-G1-4 Given the same trigger event delivered twice, then the action is applied once.
- AC-G1-6 Given an automation "Stage → Won ⇒ move to group Closed Won", when the group is deleted, then the automation becomes "Needs attention", its owner is notified, and setting Won no longer moves anything.
- AC-G1-7 Given automation 2 (L1), when Status is set Qualified twice within 1 s, then exactly one Contact and one Deal exist (G1.13 + condition "Contacts is empty").
- AC-G1-9 Given automation 2 with a transient fault injected at step 2, then after retry exactly one Contact and one Deal exist and the Deal is linked to that Contact; with a permanent fault, the Contact exists, no Deal exists, and the run history shows step 1 done / step 2 failed.
- AC-G1-8 Given automations 8 and 11 both fire on Won, then the project is created and the deal moved regardless of which runs first.
- AC-G1-5 Given a condition "only if Owner is me(Mia)" and the item owner changed to Raj before execution, then the actions do not run (evaluated at execution time).

## G2 Triggers — P1 subset
| Trigger | Params | Fires when |
|---|---|---|
| T1 Item created | (optional) in group | item created in board by any source (UI, form, API, automation; not import unless opted in) |
| T2 Column changes | column (any type except Formula, Mirror, Creation log, Last updated, Item ID, C38) | value of that column changes (old ≠ new); for Connect columns this includes changes made on this side by reflection |
| T3 Status changes to | status column, one or more labels ("any of") or "anything" | status column changes to label (from any or a specific "from" label — P2) |
| T4 Date arrives | date column, offset (−30…+30 days), time of day | daily scheduler at chosen time in account tz evaluates items whose date + offset = today (per item once per date value) |
| T5 Button clicked | button column | user clicks the button on an item |
| T6 Item moved to group | group | item enters group (by drag, menu or automation) |
| T7 Timeline activity created (CRM) | activity type (any or specific) | activity added on an item of this board (L10.4) — P1 |
| P2 | — | subitem created, update created, person assigned, every time period (recurring), item moved to board, email received/opened (with L11) |

## G3 Conditions — P1
- "only if <column> is <value>" for Status/Dropdown/People/Checkbox/Numbers (=,>,<)/Date (before/after today, or before/after a date variable such as `{trigger.activity.start}`); a condition "is empty" may be OR-combined with one other condition on the same column; "only if <any column> is empty / is not empty" (including Connect and Email); "only if item is in group X". Combined with AND (max 5).

## G4 Actions — P1 subset
| Action | Params | Behavior |
|---|---|---|
| A1 Notify | recipients (me / specific users / People column / board subscribers / item subscribers), message with variables | creates in-app notification (+ email per user settings) to recipients who can see the item; > 5 notifications from the same automation to the same recipient within 1 min are grouped into one ("and 37 more") |
| A2 Set column value | column, value (static / variable / "today" / "today + N" for dates / increment for numbers) | sets value |
| A3 Clear column | column | sets empty |
| A4 Move to group | group | moves item |
| A5 Move to board | board, group, column mapping | moves item (B6.5 semantics) |
| A6 Create item in board & connect | target board, group, field mapping, relation column (on source or target) | creates new item, links it to the triggering item |
| A7 Create subitem | name template, field values | creates subitem under triggering item |
| A8 Archive item | — | archives |
| A11 Duplicate item | with/without updates & subitems | duplicates in same group |
| A9 Assign person (P1 per D-013) | People column, person (static / actor / creator / from a People column) | adds person |
| A10 Connect items where column matches (P1 per D-013) | relation column, source column, target board + column, match logic (first match \| all matches) | finds target items with equal value (case-insensitive for email/text) and links them; skips if already linked; no-op if source value empty |
| P2 | — | delete item, push date by N days, create update with text, send email (L11), create item in board (no connect) |

## G5 Cross-board automations — P1
A5, A6, A10 operate across boards; the owner must have edit rights on the target board at creation and at execution.

## G6 Recipe catalog — P1
- Curated templates grouped by category: Status change, Item creation, Notifications, Due dates, Move item, Cross-board, CRM. Each template = prefilled sentence. Users can also "Create custom" from any trigger + conditions + actions.
- The 14 seeded CRM automations (L1-automations) must be expressible as catalog recipes (no hidden special cases); T7 is a normal catalog trigger.

## G7 Run history — P1
- G7.1 Per automation and per board: list of runs (time, item, trigger event, status success|failed|skipped (conditions false)|stopped, duration, actions applied, error message).
- G7.2 Retention 30 days; filters by status/automation/date.
- G7.3 Failed runs notify the automation owner (deduplicated: max 1 notification per automation per hour).
- AC-G7-1 Given an action fails permanently, then the run shows "failed" with the error text and the owner gets a notification.

## G8–G10 — P2/P3
Multi-step workflow builder with branching (P3), account automation hub & action quotas (P3, quotas not needed for single org), integration recipes (P3; CRM email in L11 P2).

## Additional ACs
- AC-G3-1 Given condition "only if Owner is empty", when an item with an owner triggers, then the run is recorded as "skipped (conditions false)" and no action is applied.
- AC-G5-1 Given an automation that creates an item on board B2, when its owner loses edit access to B2, then the next run fails with "owner no longer has permission on B2".
- AC-G6-1 Given the recipe catalog, then each of the 14 seeded CRM automations can be recreated from catalog templates alone and the recreated automations pass the same tests (golden test).

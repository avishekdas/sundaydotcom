# 03 — Column Types (Area C)

## Common rules for every column (C40) — P1
- C40.1 Column fields: id (stable, board-unique slug, immutable), title (1–60, unique per board case-insensitive), type, description (≤ 500, shown on header "i"), settings (type-specific JSON), position, width (per view), hidden (per view).
- C40.2 Operations: add (header "+" with type picker, or right of a column), rename inline, edit description, reorder by drag, resize, hide in view, duplicate (with or without values), delete (→ Trash 30 days with values), change settings.
- C40.3 Change type (P1, limited): Text ↔ Long text, Text → Email/Phone/Link/Number (values that fail parsing become empty, with preview count), Status ↔ Dropdown (labels kept). Other conversions are rejected.
- C40.4 Column permissions (who can view/edit a column) are P2 (K4).
- C40.5 Every value change is validated server-side against the type's value schema; invalid → 400 with field-level message.
- C40.6 Every type defines: value schema, settings schema, empty value, display text (used by search, CSV, notifications, formulas), sort key, filter operators, summary functions (B12), CSV import parser and export formatter. This table is the contract tested per type.
- AC-C40-1 Given a column renamed, then formulas, mirrors, automations, filters and dashboard widgets referencing it keep working (they reference id, not title).
- AC-C40-2 Given a column deleted and restored within 30 days, then its values on all items are restored.
- AC-C40-3 Given a Text column converted to Number with 10 values of which 2 are non-numeric, then the preview says "2 values will be cleared" and after confirming 8 numbers remain.

## P1 column catalog

| ID | Type | Value (stored) | Settings | Edit UX | Filter operators | Sort | Summary |
|---|---|---|---|---|---|---|---|
| C1 | Name | string 1–255 | — | inline text | contains, not contains, is, is empty | alpha | count |
| C2 | Text | string ≤ 2,000 | — | inline | contains, not contains, is, is not, empty, not empty | alpha | count non-empty |
| C3 | Long text | string ≤ 20,000, plain with line breaks | — | popover editor | contains, empty, not empty | alpha | — |
| C4 | Numbers | decimal (18,6) or null | unit {symbol, custom, direction}, decimals 0–6, footer function, optional min/max (enforced on write) | inline numeric | =, ≠, >, ≥, <, ≤, between, empty, not empty | numeric | sum/avg/median/min/max/count |
| C5 | Status | label id or null | labels[{id, text ≤ 40, color, position, is_done, deactivated}] max 40 labels; default label | dropdown of labels; "Edit labels" for owners | is any of, is not any of, empty | label position | distribution bar |
| C6 | Dropdown | label id[] | labels[{id, text, deactivated}] ≤ 500, limit_select (1 = single) | multi-select chips with type-ahead; create label on the fly if permitted | contains any, contains all, not contains, empty | first label alpha | distribution |
| C7 | People | [{type: user\|team, id}] | max_people (0 = unlimited) | picker with search; "assign me" | contains any person/team, is me, empty | first name alpha | count |
| C8 | Date | {date: YYYY-MM-DD, time?: HH:MM} UTC-normalized when time set | include_time, reminder (P2) | date picker; quick keys Today/Tomorrow | is, before, after, between, today, this week, overdue (before today & item not done), empty | chronological | earliest–latest |
| C9 | Timeline | {from, to} dates, to ≥ from | milestone allowed | range picker; drag on Gantt (P2) | overlaps range, starts/ends before/after, current, empty | by from | span |
| C10 | Email | {email, text?} RFC 5322 basic | — | inline; click → compose (L11) or mailto | contains, is, empty | alpha | count |
| C11 | Phone | {e164, country_code} | default country | inline with country flag; validated via libphonenumber | contains, empty | alpha | count |
| C12 | Link | {url (http/https), text?} | — | inline; opens new tab | contains, empty | alpha | count |
| C13 | Checkbox | boolean | — | click toggles | checked, unchecked | false<true | x/y checked |
| C17 | Formula | computed (number\|string\|date\|bool) | expression | read-only cell; editor for owners with column picker & live preview | as result type | as result type | as Numbers when numeric |
| C18 | Connect boards | item id[] (ordered) | target board ids (1–5), allow multiple items (bool), create reflected column on target (bool), display fields | chip picker searching target boards; "+ create new <term>" inline | contains item, empty | first linked name | count |
| C19 | Mirror | computed from C18 | relation column id, target column ids per board, aggregation (none\|sum\|avg\|min\|max\|count\|earliest\|latest\|distinct) | read-only (P1); edit-through P2 | as mirrored type | as mirrored type | as mirrored type |
| C21 | Files | [{file id, name, size, mime, uploaded_by/at}] | — | upload (drag/drop, ≤ 100 MB each), preview images/PDF, download, delete | has files, empty | count | count |
| C22 | Button | — (no value) | text, color, linked automation id | click runs automation for that item | — | — | — |
| C24 | Item ID | item id (read-only) | — | copy | is | numeric | — |
| C25 | Creation log | {user, at} read-only | mode (person+date \| person \| date) | — | created by, created between | chrono | — |
| C26 | Last updated | {user, at} read-only, updated on any column/name change | mode | — | updated by, updated between | chrono | — |
| C37 | Subitems | managed by B7 | subitem board id | expander + count | has subitems | count | count |
| C38 | Activities timeline (CRM) | computed from L10 | — | mini bar of last 12 weeks colored by activity type; "+" quick add | last activity before/after | last activity date | — |

## Detailed rules for complex types

### C5 Status — P1
- C5.1 Default new status column labels: Working on it (orange), Done (green, is_done), Stuck (red), plus empty.
- C5.2 Deleting a label in use requires choosing a replacement label (or empty) for affected items; deactivating keeps existing values but hides it from the picker.
- C5.3 `is_done` drives: B12 progress, D5 done lanes, A9 "overdue" exclusion, H3 battery.
- AC-C5-1 Given a label "Lost" used by 3 deals, when deleted with replacement "empty", then those 3 items have empty status and 3 log entries exist.

### C8 Date & time zones — P1
- C8.1 Date-only values are calendar dates with no timezone and never shift when viewed from another zone.
- C8.2 Values with time are stored as UTC instants and displayed in the viewer's timezone (A16).
- C8.3 Interactive relative filters in table/kanban/search ("today", "this week", "overdue") use the **viewer's** timezone and the account week start.
- C8.4 (D-017) Dashboard widget periods and date bucketing (Gauge, Leaderboard, chart by month…), automations (T4, A2 "today", `{today}`, date parts of trigger variables), and materialized formulas using TODAY() use the **account** timezone. T4 runs at the configured local wall-clock time, so its UTC time shifts with DST.
- AC-C8-1 Given date-only 2026-11-02 entered by a user in New York, when viewed by a user in Kolkata, then it shows 2 Nov 2026.
- AC-C8-2 Given account tz America/New_York and a T4 rule at 09:00, then it runs at 13:00Z before 1 Nov 2026 and 14:00Z after the DST change.
- AC-C8-3 Given a viewer in Kolkata at 2026-10-25T20:00Z (26 Oct local), when filtering "today", then items dated 26 Oct match and 25 Oct do not.

### C7 People — P1
- C7.1 Assigning triggers A9 assignment notification to newly added users (and members of newly added teams, P2) except self.
- C7.2 Deactivated users remain displayed (greyed) and are excluded from the picker.
- C7.3 The value schema allows `type: team` for P2, but the P1 API rejects team values (Teams are P2, F3).
- AC-C7-1 Given Mia assigns Raj, then Raj receives an assignment notification (A9) and the cell shows his avatar; given a request with a team value, then 400.

### C17 Formula — P1
- C17.1 Syntax: `{column_id}` references, numeric literals, strings in double quotes, operators `+ - * / % ^ & = <> < > <= >=`, parentheses.
- C17.2 Functions P1: IF, AND, OR, NOT, SUM, AVERAGE, MIN, MAX, ROUND, ROUNDUP, ROUNDDOWN, ABS, CONCATENATE, LEFT, RIGHT, LEN, UPPER, LOWER, TODAY, DAYS, WORKDAYS, FORMAT_DATE, ADD_DAYS, SWITCH, ISBLANK. (Full Excel-like library is P2.)
- C17.3 Inputs allowed: Numbers, Text, Status (label text), Dropdown (labels joined), Date, Timeline (start/end via TIMELINE_START/END), Checkbox, People (names), Mirror (aggregated value), other Formula (no cycles), Item ID, Creation/Last updated.
- C17.4 Errors (div by zero, type mismatch, cycle) render "!" with tooltip; never block saving other columns.
- C17.5 Formula results are **materialized** (stored) when any input changes (including mirrored inputs, ≤ 5 s) and, for formulas using TODAY()/DAYS()/WORKDAYS(), recomputed nightly at 00:05 account time (C8.4). Views, filters, sorts, exports, dashboards and automations read the materialized value.
- C17.6 Formula results can be filtered/sorted (P1) and used as automation conditions (P2).
- C17.7 (D-015) A formula whose inputs include a Mirror is materialized from the full linked set, but that stored value is served only to viewers who can see every contributing board. For any other viewer, display, filter, sort, export, dashboard widgets and API reads compute the formula per viewer over visible contributors only, with a "partial" marker. Automations use the stored value (they run as their owner, G1.5).
- AC-C17-6 Given Robert's deals 100,000 (visible to Vic) and 55,000 (hidden from Vic), and a formula `{contact_deals_value} * 0.1`, when Vic filters formula > 12,000, then Robert is not returned (Vic's value is 10,000); Vic's export and a Number widget also show 10,000; Mia sees 15,500.
- AC-C17-1 Given Deal Value 100,000 and Close Probability 40 with formula `{deal_value}*{deal_close_probability}/100`, then the cell shows 40,000.
- AC-C17-2 Given formula A references B and B is edited to reference A, then saving B is rejected with "circular reference".
- AC-C17-3 Given a referenced column is deleted, then the formula shows "!" "Missing column" until fixed or the column is restored.
- AC-C17-4 Given 3,000 deals and filter Forecast Value > 20,000, then exactly the deals whose materialized value exceeds 20,000 are returned, sorted correctly by Forecast Value desc.
- AC-C17-5 Given formula `DAYS(TODAY(), {expected_close})`, when the date changes at account midnight, then the value updates by 00:15 without any edit.
- *Note:* the observed monday template uses `{deal_value}*{deal_close_probability}` without /100 — our CRM template uses the corrected formula (see L8).

### C18 Connect boards — P1
- C18.1 Linking A→B stores the link on A's column. If "reflected column" is enabled, B gets a Connect column whose values are kept in sync (bidirectional): a link and its reflection are written in the **same transaction**; only real-time fan-out to other clients takes up to 2 s.
- C18.1a An item created with a link (A6, "+ Create new", form) is committed together with its link and reflection, so T1 on the new item already sees the link.
- C18.2 Picker searches target board items the user can see; items the user cannot see are shown as "Hidden item" chips (count only).
- C18.3 Inline "+ Create new" creates an item on the target board (top group) and links it.
- C18.4 Max 500 linked items per cell.
- C18.5 Deleting/archiving linked item hides the chip (A11.3).
- C18.6 If a reflection write would exceed the other side's single-item setting, the other side's previous link is replaced and an activity log entry records it.
- C18.7 Connect columns pointing at more than one board do not support reflection in P1 (e.g. Activities.Related item); the linked item's timeline (L10) reads the relation in reverse instead.
- C18.8 Link/unlink are deltas (D-010); concurrent links from two users both persist.
- AC-C18-3 Given Robert is linked to Amazon (Contacts.Accounts is single), when Raj adds Robert to Google's Contacts column, then Robert's Accounts becomes Google and Amazon's Contacts no longer lists Robert.
- AC-C18-1 Given Contacts.Accounts linked to Accounts with reflection, when Raj links Robert → Amazon, then Amazon's Contacts column shows Robert within 2 s.
- AC-C18-2 Given Raj unlinks on Amazon's side, then Robert's Accounts cell becomes empty.

### C19 Mirror — P1
- C19.1 Displays chosen column(s) of all items linked via the relation column, possibly across multiple target boards.
- C19.2 Aggregation per mirror setting (e.g. Contacts."Deals value" = sum of Deals.Deal Value).
- C19.3 Recomputed when the relation changes or any mirrored source value changes (≤ 5 s p95). Mirrors of mirrors (one hop of indirection, e.g. Deals.Accounts = mirror of Contacts.Accounts) supported to depth 2.
- C19.4 Filter/sort/summary on mirror uses aggregated value.
- C19.5 Visibility (D-012): display and aggregation include only linked items the viewer can see; if any contributor is hidden, the cell shows the visible-only value with a "partial" marker and tooltip "Some linked items are hidden". Server-side filter/sort on mirror columns use the full materialized value only for viewers who can see all linked boards (D-015); otherwise filtering on that column is evaluated per viewer (slower path, ≤ 2 s p95 at 20,000 items). Visibility is checked at every hop of a mirror-of-mirror (C19.3).
- C19.6 Archived/trashed linked items are excluded (A11.7).
- AC-C19-1 Given contact Robert linked to deals 100,000 and 55,000 and mirror aggregation sum, then "Deals value" = 155,000; when a deal value changes to 60,000, then it shows 160,000 within 5 s for all viewers (F7 computed-value event).
- AC-C19-2 Given the 55,000 deal is on a board Vic cannot see, then Vic sees 100,000 with a "partial" marker while Mia sees 155,000.

### C21 Files — P1
- C21.1 Stored in object storage; download via short-lived signed URL (≤ 15 min) after permission check.
- C21.2 Malware scanning before availability (P2; P1 blocks executable mime types).
- C21.3 Max 100 MB per file, 50 files per cell.

### C22 Button — P1
- C22.1 Clicking requires edit permission on the item; runs the linked automation synchronously-queued; button shows spinner until the run completes or 10 s.
- AC-C22-1 Given the Leads "Move to Contacts" button, when clicked, then a Contact with the lead's name, phone, email exists and the lead is removed from Leads (automation 4).

## P2/P3 columns (summary)
- **P2:** Tags (C14, account-wide tag list), Rating (C15, 1–5), Progress (C16, % of done statuses across selected status columns), Dependency (C20, FS/SS/FF/SF with lag, drives Gantt), Auto number (C23, prefix + sequence), Hour (C27), Country (C30), Team (C35).
- **P3:** Week, World clock, Location (+ map view), Color picker, Vote, Time tracking, Doc, Managed account-level columns (C41), CRM Active sequences (C39).
- **OUT:** AI columns (C42).

## ACs for simple P1 types (C10–C13, C24–C26)
- AC-C10-1 Given "jane@acme" (no TLD) entered in Email, then 400 "Invalid email"; "jane@acme.com" saves and renders as a link.
- AC-C11-1 Given phone "734 844 2393" with default country US, then it is stored as +17348442393 and shows the US flag.
- AC-C12-1 Given link "javascript:alert(1)", then 400; "https://acme.com" with text "Acme" renders "Acme" opening in a new tab with rel=noopener.
- AC-C13-1 Given 3 of 5 items checked, then the group footer shows 3/5.
- AC-C24-1 Given any item, then Item ID equals the item's ID and cannot be edited (400 on write).
- AC-C25-1 Given an item created by a form, then Creation log shows "Form: <title>" and the creation time.
- AC-C26-1 Given Mia edits a Status, then Last updated shows Mia and the edit time; given an automation edits it, then it shows the automation.

## ACs for remaining P1 types
- AC-C1-1 Given a name of 256 characters, then 400; given "  Acme  ", then stored as "Acme".
- AC-C2-1 Given filter Text contains "ama" (case-insensitive), then "Amazon" matches and "Google" does not.
- AC-C3-1 Given 20,001 characters in Long text, then 400; 20,000 saves and line breaks are preserved.
- AC-C4-1 Given Numbers with unit "$" left and 2 decimals, when 1234.5 is entered, then "$1,234.50" displays and 1234.5 is stored; "12a" is rejected.
- AC-C4-2 Given Close Probability min 0 max 100, when 120 is entered, then 400 "Must be between 0 and 100".
- AC-C6-1 Given a Dropdown with limit_select 1, when two labels are sent, then 400; with limit 0, both save and filter "contains all [A,B]" matches the item.
- AC-C9-1 Given a Timeline with to < from, then 400; given 1–10 Nov, then filter "overlaps 5–6 Nov" matches it.
- AC-C21-1 Given a 101 MB upload, then rejected; a 2 MB PDF uploads, previews, and its download URL expires after 15 min.
- AC-C21-2 Given an .exe upload, then rejected with "File type not allowed".
- AC-C38-1 Given activities logged in weeks −1 (Meeting) and −5 (Call summary), then the Activities timeline cell shows ticks at those weeks colored by type, and hovering the latest shows its title and date.
- AC-C37-1 Covered by AC-B7-1…4.

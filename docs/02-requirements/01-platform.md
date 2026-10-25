# 01 — Platform & Navigation (Area A)

## A1 Account settings — P1
**Story:** As Ada, I set the organization name, logo, default timezone and allowed sign-up email domains so the app reflects my company.
**Rules**
- A1.1 Exactly one account exists; created by the bootstrap process (first admin from deployment config).
- A1.2 Editable by Admins only: name (1–80 chars), logo (PNG/SVG/JPG ≤ 1 MB), default timezone (IANA), date format (DD/MM/YYYY | MM/DD/YYYY | YYYY-MM-DD), week start (Sun|Mon), allowed email domains for invites (optional list).
- A1.3 Logo shown in top bar and on public forms (I5).
**AC**
- AC-A1-1 Given an Admin, when they save a new account name, then all users see it in the top bar on next navigation and an audit entry is written.
- AC-A1-2 Given a Member, when they open account settings, then the page is not reachable (HTTP 403 from API; no menu entry in UI).
- AC-A1-3 Given allowed domains = [acme.com], when an Admin invites bob@other.com, then the invite is rejected with a clear message.

## A2 Workspaces — P1
**Story:** As Mia, I group boards for a team in a workspace and control who sees it.
**Rules**
- A2.1 Fields: name (1–60), description, icon/color, kind = Open (all account members can see & join) | Closed (only members see it).
- A2.2 Roles: workspace owner(s), members. Creator is owner. At least one owner always.
- A2.3 A default workspace "Main workspace" exists and cannot be deleted.
- A2.4 Deleting a workspace moves it and all contents to Trash (A11); restore restores everything.
- A2.5 Boards/dashboards belong to exactly one workspace; can be moved between workspaces by owners of both.
**AC**
- AC-A2-1 Given a Closed workspace, when a non-member Member searches or browses, then neither the workspace nor its boards appear.
- AC-A2-2 Given the last owner, when they try to leave or be demoted, then the action is rejected.
- AC-A2-3 Given a workspace with 3 boards, when it is deleted and then restored within 30 days, then all 3 boards and their items are back unchanged.

## A3 Folders — P2
Folders (and sub-folders, max depth 3) inside a workspace to organize boards/dashboards; color; drag to reorder; deleting a folder moves contents up one level.

## A4 Left navigation — P1
**Rules**
- A4.1 Shows workspace switcher, then a tree of boards and dashboards (folders in P2) the user can access, ordered by user-defined position.
- A4.2 Drag-and-drop reorder within workspace (owners/members with create rights).
- A4.3 Filter box narrows the tree by name (client-side, case-insensitive).
- A4.4 "+" menu: New board, New dashboard, New form-backed board, Import (A13), From template (P2).
- A4.5 Collapsible; state remembered per user.
**AC**
- AC-A4-1 Given a user without access to a Private board, when the tree loads, then the board is absent.
- AC-A4-2 Given the user drags board X above board Y, then the order persists after reload and is the same for all users of the workspace.

## A5 My Work — P2
Cross-board list of items where a People column contains me, grouped Overdue/Today/This week/Next week/Later/No date by the first Date/Timeline column; inline status edit.

## A6 Favorites — P2
Star boards/dashboards; personal ordered list in a left-rail section.

## A7 Global search — P1 (items & boards), P2 (updates, people, files)
**Story:** As Raj, I press ⌘/Ctrl+K and type part of a contact's name to jump to it.
**Rules**
- A7.1 Searches item names, text/long-text/email/phone column values, board names, dashboard names.
- A7.2 Results respect permissions (K-area): never return an item the user cannot open.
- A7.3 Prefix and fuzzy match (1 typo for terms ≥ 5 chars); ranked: exact name > prefix > fuzzy; recently visited boosted.
- A7.4 Index freshness: change searchable within 5 s p95.
- A7.5 Max 50 results, grouped by type; Enter opens; Esc closes.
**AC**
- AC-A7-1 Given item "Robert Thompson" on Contacts, when Raj types "thomp", then the item appears in the first 5 results within 500 ms p95 (server time).
- AC-A7-2 Given a Private board Raj is not invited to, when he searches a term that only matches items there, then zero results are returned.
- AC-A7-3 Given an item renamed, when searched 5 s later by the new name, then it is found and not by the old name.

## A8 Inbox — P2
Feed of updates on items I'm subscribed to or mentioned in; mark read/unread; filter "mentions only".

## A9 Notifications — P1 (in-app, email); P3 (desktop push)
**Story:** As Raj, I am told when I'm assigned, mentioned, or an automation notifies me.
**Rules**
- A9.1 Notification types P1: assigned to item (People column), mentioned in update, reply to my update, update on item I subscribe to, automation "notify" action, invite to board/workspace.
- A9.2 In-app bell with unread count, real-time (F7); list newest first; click navigates to item/update; mark one/all read.
- A9.3 Email channel: per-type on/off in user settings; default ON for assigned/mentioned/automation, OFF for subscribed updates. Batched: max 1 email per item per 5 min.
- A9.4 Per-board mute (all / only mentions & assignments) per user; board owner can mute for all (P2).
- A9.5 Never notify a user about their own action. Never notify about items the user cannot see.
- A9.6 Retention: 90 days.
**AC**
- AC-A9-1 Given Raj is assigned in a People column by Mia, then Raj's bell count increments within 2 s and an email is sent within 5 min.
- AC-A9-2 Given Raj assigns himself, then no notification is created.
- AC-A9-3 Given Raj muted board B, when he is subscribed-updated on B, then no notification; when he is mentioned on B, then he is notified (mute level "only mentions & assignments").
- AC-A9-4 Given 10 updates on the same item within 5 min, then Raj gets at most 1 email for that item in that window.

## A10 Templates — P2 (board), P3 (workspace)
Save board as template (structure, views, automations, optionally items); create board from template; built-in templates include the CRM set (L1 is P1 and implemented as a built-in workspace template regardless).

## A11 Archive & Trash — P1
**Rules**
- A11.1 Archive (boards, groups, items, dashboards): hidden from normal UI, searchable in "Archive", restorable any time, not counted in views/dashboards/automations.
- A11.2 Delete: moves to Trash; restorable for 30 days by owner or Admin; then hard-deleted by a scheduled purge (including files).
- A11.3 Automations never fire on archived/trashed items; linked board_relation values to trashed items are hidden, restored on restore.
- A11.4 Only Admins can empty Trash immediately (permanent delete).
- A11.5 Who may restore: the board owner(s), the user who deleted it, or an Admin.
- A11.6 Restoring an item whose group no longer exists places it in the board's top group; restoring an item whose board is in Trash requires restoring the board first (UI offers it).
- A11.7 Mirrors, formulas, summaries and widgets exclude archived and trashed items and recompute ≤ 5 s after archive/delete/restore. Reflected Connect values are hidden (not removed) while the linked item is archived/trashed and reappear on restore.
- A11.8 Purge of a board/group/item removes its relation values on the other side.
**AC**
- AC-A11-4 Given an item whose group was deleted and purged, when the item is restored, then it lands in the board's top group with values intact.
- AC-A11-5 Given a deal (value 55,000) linked to a contact is trashed, then the contact's *Deals value* mirror drops by 55,000 within 5 s and returns on restore.
- AC-A11-1 Given an item deleted on day 0, when restored on day 29, then all column values, updates, files and relations are intact.
- AC-A11-2 Given an item deleted on day 0, then on day 31 it is not restorable and its files are gone from storage.
- AC-A11-3 Given a deal linked to a contact is archived, when the contact is opened, then the deal chip is hidden; after restore it reappears.

## A12 Undo — P2
Undo the last destructive/bulk action within 30 s via toast (delete, archive, bulk set, move).

## A13 Import CSV — P1 (CSV), P2 (XLSX)
**Story:** As Mia, I import 2,000 contacts from a CSV into the Contacts board.
**Rules**
- A13.1 Upload ≤ 20 MB, ≤ 20,000 rows, UTF-8 (BOM tolerated), comma/semicolon auto-detect.
- A13.2 Mapping screen: each CSV column → existing column / new column (type chosen) / skip; first column defaults to Name.
- A13.3 Per-type parsing (dates ISO + account date format, numbers with locale separators, status/dropdown labels: unknown labels optionally created, people by email).
- A13.4 Target group selectable; optional "update existing items where column X matches" (dedupe key, P2).
- A13.5 Runs async; progress shown; result report with row-level errors downloadable as CSV.
- A13.6 Import does NOT trigger "item created" automations unless the user ticks "run automations" (default off).
**AC**
- AC-A13-1 Given a valid 2,000-row CSV, when imported, then 2,000 items exist within 60 s and the report shows 0 errors.
- AC-A13-2 Given a row with an invalid date, then that cell is left empty, the row is imported, and the report lists row number, column and reason.
- AC-A13-3 Given "run automations" unticked, then no automation run is recorded for imported items.

## A14 Export — P1
CSV (P1) and XLSX (P2) export of a board or of the current view (respecting filters, visible columns, sort). Includes subitems as indented rows (option). Async for > 5,000 items with download link valid 24 h. Requires export permission (K1).
- AC-A14-1 Given a view filtered to 12 items with 5 visible columns, when exported, then the file has 12 data rows and 5 columns in view order.
- AC-A14-2 Given a Viewer without export permission, then the export action is hidden and the API returns 403.

## A15 Activity log — P1
**Rules**
- A15.1 Every change to an item (create, rename, column value old→new, move group/board, archive, delete, restore, subitem add) is recorded: actor (user | automation id | form | import), timestamp, entity, before, after.
- A15.2 Board activity log: filter by person, column, date range, item; paginated.
- A15.3 Item activity log tab (E4) shows the item's entries.
- A15.4 Retention: 1 year (P1).
- A15.5 Board-structure events are also recorded in P1 (column/group/view create-update-delete, permission-set and board-kind changes, owner changes, automation create/update/activate/deactivate/delete, form activate/deactivate). Account-level security events (sign-in, role change, user deactivation, export, settings) are recorded in the audit store in P1 (UI is K9, P2) — this is the P1 audit event list for NFR-S6.
**AC**
- AC-A15-1 Given Raj changes Stage from Proposal to Won, then the log shows "Raj · Stage · Proposal → Won" with timestamp.
- AC-A15-2 Given an automation moves the item to Closed Won, then the entry's actor is "Automation: <name>".

## A16 User profile — P1 (basic), P2 (out-of-office)
Name, photo, title, phone, timezone (default account tz), language (English only, O5). P2: out-of-office with date range shown on avatar.
- AC-A16-1 Given Raj sets timezone Asia/Kolkata, when he views an activity stored at 2026-10-24T18:00Z, then it shows 24 Oct 2026, 11:30 pm.

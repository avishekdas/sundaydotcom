# 02 — Boards, Groups, Items, Subitems (Area B)

## B1 Board CRUD — P1
**Story:** As Mia, I create a "Deals" board, name its items "Deal", and add columns.
**Rules**
- B1.1 Fields: name (1–120), description (≤ 5,000, plain text with links), item terminology (singular label, default "Item"), workspace, kind (B2), position.
- B1.2 New blank board starts with one group "Group Title", columns Name, Person (People), Status (default labels Working on it / Done / Stuck, Done = is_done), Date; one Table view "Main table".
- B1.3 Rename inline in header; description via header menu.
- B1.4 Board header shows: name, description toggle, owner avatars, member count, Invite, Automate (count of active automations), Integrate (P3), activity log, views tabs.
- B1.5 Max 200 columns per board, 500 groups, 100,000 items (B11).
**AC**
- AC-B1-1 Given Mia creates a blank board, then it contains exactly the defaults of B1.2 and she is its owner.
- AC-B1-2 Given item terminology "Deal", then the "New Deal" button, empty states and counts ("5 Deals") use it.
- AC-B1-3 Given a board with 200 columns, when a 201st is added, then it is rejected with a limit message.

## B2 Board kinds — P1 (Main, Private), P2 (Shareable)
- B2.1 Main: visible to every member of the workspace (open workspace → all account members).
- B2.2 Private: visible only to explicitly invited users/teams and Admins.
- B2.3 Shareable (P2): like Private plus Guests can be invited.
- B2.4 Changing kind is owner-only; Private→Main asks for confirmation.
- AC-B2-1 Given a Private board, when a non-invited Member opens its URL, then they see "no access" and the API returns 404 (no existence leak).

## B3 Owners & subscribers — P1
- B3.1 Owners: full control (structure, permissions, automations, delete). Creator is first owner; ≥ 1 owner always (Admins can always act as owner).
- B3.2 Subscribers (board members): receive board-level notifications per A9; owners can add/remove; users can unsubscribe themselves.
- AC-B3-1 Given the last owner tries to remove themselves, then it is rejected.

## B4 Duplicate board — P2
Options: structure only / structure + items / structure + items + updates. Automations duplicated inactive. Relations to other boards kept; self-relations remapped.

## B5 Groups — P1
**Rules**
- B5.1 Fields: title (1–255), color (from 20-color palette), position, collapsed state (per user per view).
- B5.2 Operations: add (top or bottom), rename inline, change color, collapse/expand (one / all), reorder by drag, duplicate (with items), move group to another board (P2), archive, delete (→ Trash with its items).
- B5.3 A board always has ≥ 1 group; deleting the last group is rejected.
- B5.4 "Top group" = where new items go by default (first group unless configured).
- B5.5 Group footer shows per-column summaries (B12).
**AC**
- AC-B5-1 Given a group with 3 items, when duplicated, then a new group "<title> (copy)" with 3 new items (new IDs, same values, no updates) is placed below it.
- AC-B5-2 Given two users viewing the board, when one reorders groups, then the other sees the new order within 2 s (F7).
- AC-B5-3 Given the only group, when delete is attempted, then it is rejected.

## B6 Items — P1
**Story:** As Raj, I add a lead, edit its fields inline, move it between groups, and archive it when done.
**Rules**
- B6.1 Create: inline "+ Add <term>" row at bottom of each group; header "New <term>" button (adds to top group, opens item page); via form (I1); via automation; via import; via API.
- B6.2 Name required, 1–255 chars, trimmed; empty name rejected.
- B6.3 Every item has immutable ID (numeric, globally unique), created_at/by, updated_at/by.
- B6.4 Position within group is user-ordered (drag); new inline items append at the end of the group; "New <term>" inserts at top.
- B6.5 Move to group (drag or menu), move to board (menu: target board + group, column mapping by title+type with preview; unmatched values dropped with warning).
  - B6.5a The item ID is preserved (links pointing to it stay valid).
  - B6.5b Updates, files, activity log and CRM timeline activities (D-011) move with the item.
  - B6.5c Subitems move; their values map by title+type onto the target's subitem board; unmatched subitem values dropped with warning; if the target has no subitems column one is created (allowed because the mover must have edit rights on the target board; if the target's permission set forbids structure changes for the mover, subitems are dropped with a warning instead).
  - B6.5d Connect values are kept only if the target board has a Connect column (matched by title+type) to the same target board(s); otherwise dropped and their reflections on the other side removed.
  - B6.5e Activity log records "moved from board X" on the item.
- B6.6 Duplicate: same values, "(copy)" suffix optional, with/without updates and subitems.
- B6.7 Archive / delete per A11.
- B6.8 Concurrency (D-010): scalar cells are last-write-wins per cell, never per item; the server assigns each accepted write a monotonically increasing per-item `version`. Multi-value cells (People, Dropdown, Connect, Files) are written as add/remove deltas so concurrent adds both survive. The activity log shows every write.
- B6.9 Optimistic UI with rollback on server rejection and toast.
**AC**
- AC-B6-1 Given Raj types a name in "+ Add lead" and presses Enter, then the item is saved, appears at the end of the group, the input stays focused for the next item.
- AC-B6-2 Given empty name + Enter, then nothing is created.
- AC-B6-3 Given Raj and Mia edit different columns of the same item simultaneously, then both values persist.
- AC-B6-4 Given they edit the same cell, then the later server write wins and both clients converge to it within 2 s.
- AC-B6-5 Given an item moved to a board lacking a matching column for "Priority", then the move preview warns "Priority will be lost" and after confirmation the item exists on the target without it, and is gone from the source.
- AC-B6-6 Given the server rejects an edit (permission), then the UI reverts the cell and shows the reason.
- AC-B6-7 Given Raj adds himself and Mia adds Paul to the same People cell at the same time, then the cell contains both Raj and Paul.
- AC-B6-8 Given a lead with 2 updates, 1 file and 1 timeline activity is moved to Contacts, then the contact has the same item ID, the 2 updates, the file and the activity, and the Activities item's Related item still resolves to it.

## B7 Subitems — P1
**Rules**
- B7.1 Each board may have one subitems column; subitems live in a hidden linked "Subitems of <board>" board with its own columns (default Name, Owner, Status, Date) and settings.
- B7.2 Subitems are created from the parent row expander or item page; ordered; support all column types except Subitems itself (one level only in P1; multi-level is B8 P3).
- B7.3 Parent row shows subitem count; expanding shows a nested table with its own column header.
- B7.4 Subitem column summaries can roll up into a parent column (P2: "show summary on parent" for numbers/status/timeline).
- B7.5 Deleting/archiving a parent cascades to its subitems; restore restores them.
- B7.6 P1: automation action A7 "create subitem"; P2: "subitem created" trigger.
- B7.7 Subitem boards inherit the parent board's kind, members, owners, permission set, search visibility, export and real-time channel; they never appear in navigation. Under "Only edit assigned items", a user may edit a subitem if assigned on the subitem's own People column OR on the parent's assignment column.
- AC-B7-4 Given "Only edit assigned items" on Owner and Raj owns deal D, when Raj edits a subitem of D with no owner, then it succeeds; on a subitem of Mia's deal with no owner, then 403.
**AC**
- AC-B7-1 Given a Deal with 2 subitem tasks, when the deal row is expanded, then both appear with Owner/Status/Date columns.
- AC-B7-2 Given a subitem column "Hours" is added, then it appears on all subitems of that board and not on the parent board.
- AC-B7-3 Given the parent is deleted and restored, then its subitems are restored with values.

## B8 Multi-level boards — P3
Up to 5 levels sharing parent columns. Not designed for in P1 data model beyond not precluding it.

## B9 Bulk actions — P1
- B9.1 Multi-select via row checkbox, shift-click range, group checkbox, "select all in view".
- B9.2 Floating action bar: Duplicate, Export (selected), Archive, Delete, Move to group, Move to board, Set column value (pick column → value), Convert to subitems (P2).
- B9.3 Max 1,000 items per bulk operation (larger → async job with progress).
- B9.4 Bulk ops write one activity entry per item and always fire automations per item in P1; automation runs are queued and throttled to the NFR rate (50 runs/s), so large bulk operations complete eventually.
- AC-B9-3 Given 1,000 deals bulk-set to Won, then all 1,000 Stage values are saved within 30 s and 1,000 Client Projects exist within 2 min with no failed runs.
- AC-B9-1 Given 50 selected items, when "Set Status = Done" is applied, then all 50 show Done within 3 s and 50 log entries exist.
- AC-B9-2 Given a mix of items the user can and cannot edit (assigned-only permission), then only permitted items change and the bar reports "38 updated, 12 skipped (no permission)".

## B10 Required columns & validation — P2
Owner marks columns required (for creation via UI/form/API) and simple rules (number range, regex for text, date not in past). Violations block save with message.

## B11 Limits & pagination — P1 (design constraint)
- 100,000 items per board; table virtualized; API pages of ≤ 500 items with cursor; views load first page < 2.5 s p95 for 5,000 items (north-star metric).
- AC-B11-1 Given a board with 100,000 items, when one more is created, then 409 "Board item limit reached".
- AC-B11-2 Given a 1,200-item board, when paged with limit 500, then 3 pages return all 1,200 items exactly once in view order even while 10 items are edited concurrently.

## B12 Group/column summaries — P1
- B12.1 Footer per group and for board total (when grouped by a column, per group-by bucket).
- B12.2 Numbers: sum (default) | avg | median | min | max | count | none (per column setting). Status/Dropdown: stacked color distribution bar with counts on hover. Date: earliest–latest. Timeline: overall span. People: avatars count. Checkbox: x/y checked. Formula (numeric result): as Numbers.
- B12.3 Summaries respect current view filters.
- AC-B12-1 Given Deal Value 70,000 and 55,000 in group Active Deals, then footer sum shows $125,000 (unit and direction per column setting).
- AC-B12-2 Given a filter hiding one deal, then the footer recomputes to the visible items only.

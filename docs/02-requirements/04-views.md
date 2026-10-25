# 04 — Board Views (Area D)

## D3 Saved views (framework for all views) — P1
**Story:** As Mia, I keep a "Main table", a "My deals" filtered table and a "Pipeline" kanban on the Deals board.
**Rules**
- D3.1 A board has 1–50 views shown as tabs; each view: id, name (1–50), type, settings (type-specific), filter, sort, group-by, hidden columns, column order & widths, position, pinned default.
- D3.2 The first view ("Main table") cannot be deleted; it is the default for new visitors.
- D3.3 Add view ("+" tab → type menu), rename, duplicate, delete, reorder tabs.
- D3.4 Unsaved changes: changing filter/sort/group/columns in a view is temporary for the user and shows a "Save to this view" button; saving updates the view for everyone (requires view-edit right: owners in P1; K5 P2).
- D3.5 Views never change data access: a filtered view is not a permission boundary.
- D3.6 URL: `/boards/{boardId}/views/{viewId}`; deep-linkable.
**AC**
- AC-D3-1 Given Raj applies a filter on Main table without saving, when Mia opens the board, then she sees no filter.
- AC-D3-2 Given an owner saves the filter, then all users see it on next load (and live, F7).
- AC-D3-3 Given the Main table view, when delete is attempted, then the option is disabled.

## D1 Table view — P1
**Rules**
- D1.1 Groups as collapsible sections with colored left border; group header shows title, item count; sticky group header and column header while scrolling.
- D1.2 Columns rendered per type (03-columns), inline editing, keyboard navigation (arrows, Enter edit, Esc cancel, Tab next cell), copy/paste single cells and ranges within the same column types (P1 single cell, range P2).
- D1.3 Row virtualization: smooth scroll at 5,000+ items; horizontal virtualization at 50+ columns.
- D1.4 Row expanders for subitems; item name click opens item page (E1); update-count bubble per row.
- D1.5 Drag to reorder items within/between groups (disabled when sorted, with tooltip).
- D1.6 Row height: compact/default/tall (per view).
- D1.7 Empty board/group states with call to action.
**AC**
- AC-D1-1 Given a 5,000-item board, when Main table loads, then first rows render ≤ 2.5 s p95 and scrolling stays ≥ 50 fps on reference hardware (MacBook Air M1, Chrome).
- AC-D1-2 Given a sort is active, when Raj tries to drag a row, then dragging is disabled and a tooltip explains why.

## D2 Table toolbar: search, person filter, filter, sort, group by, hide — P1
**Rules**
- D2.1 Search: free text across visible columns' display text, highlights matches, applies immediately (debounce 250 ms), also matches subitems (shows parent).
- D2.2 Person filter: pick one person (or "me") → items where any People column contains them.
- D2.3 Advanced filter: rule = column + operator + value(s) from 03-columns; rules combined in groups with AND/OR; max 10 rules; "Group" pseudo-column filter (in groups X, Y). Quick filter chips for status/people/dropdown values with counts.
- D2.4 Sort: up to 3 keys asc/desc; empty values last.
- D2.5 Group by: Group (default) or any Status/Dropdown/People/Date (by day/week/month)/Checkbox/Board-relation column; buckets ordered by label order/chronologically; drag between buckets sets the value (where writable).
- D2.6 Hide columns: checklist with search; "show all".
- D2.7 Filter/sort/group evaluation happens server-side for boards > 2,000 items, client-side otherwise; results identical (shared test corpus).
**AC**
- AC-D2-1 Given filter Stage is any of [Proposal, Negotiation] AND Owner contains me, then exactly items matching both are shown and group counts/footers reflect them.
- AC-D2-2 Given group-by Stage, when Raj drags an item from "Proposal" bucket to "Won", then its Stage becomes Won and automations fire.
- AC-D2-3 Same filter on a 1,500-item and a 3,000-item copy of the same dataset return the same ordered IDs.

## D5 Kanban — P1
**Story:** As Raj, I drag deals across the Pipeline stages.
**Rules**
- D5.1 Settings: lane column (Status, Dropdown single-select, or Group), card fields (up to 6 columns shown on card), lane order (label order), hide empty lanes, collapse lanes, lane summary (count and sum of one Numbers column).
- D5.2 Drag card between lanes sets the lane column value; within lane reorders (position stored per view).
- D5.3 Click card opens item page; "+ Add" at lane top creates item with that lane value.
- D5.4 Respects view filters/search/person filter.
- D5.5 Subitems not shown on cards in P1 (count badge only).
- D5.6 Large boards: each lane loads 50 cards and paginates on scroll; lane counts and sums are computed server-side over the full filtered set.
- D5.7 Card order within a lane is stored per view; new cards (via "+ Add" or arriving by value change) go to the top of their lane.
- AC-D5-3 Given 3,000 deals in Proposal, then the lane shows 50 cards, count 3,000 and the correct sum, and loads more on scroll.
**AC**
- AC-D5-1 Given Pipeline lanes by Stage with sum of Deal Value, when a $70,000 deal moves Discovery→Proposal, then Discovery sum decreases and Proposal sum increases by 70,000 immediately (optimistic) and persists.
- AC-D5-2 Given a deal moved to Won, then automations 8, 10, 11 run (see 06-automations).

## D9 Form view — P1
See 08-forms.md; a Form is a board view type.

## D6 Calendar — P2
Month/week/day; items placed by selected Date/Timeline columns; drag to reschedule; color by status/group/person; create item by clicking a day.

## D7 Gantt — P2
Timeline bars per item from Timeline (or two Date) columns; group/color/label by; today line; zoom day/week/month/quarter; drag/resize updates dates; dependency arrows (C20) with auto-shift option; milestones; baseline (P3).

## D8 Chart view — P2
Same chart engine as dashboard Chart widget (H3) scoped to the board.

## D12 Dashboard view on a board — P2
Embeds a widget canvas scoped to the board.

## D13 Activity analytics (CRM) — P2
Counts of timeline activities by type, owner and week/month over a date range; drill-down list.

## D14 Forecasting (CRM) — P2
Per period (month/quarter by Expected Close Date): sum of Deal Value and Forecast Value, split by Forecast category (Commit/Best case/Pipeline) and owner; won vs target.

## D10, D11, D15 — P3; D16 — OUT
File gallery; Doc view; Map/Workload/Cards; AI app view excluded.

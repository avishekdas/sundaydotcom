# 07 — Dashboards & Widgets (Area H)

## H1 Dashboard CRUD — P1
- H1.1 Fields: name, description, workspace, kind Main | Private, connected boards (1–50 in P1), owners, subscribers.
- H1.2 Created from "+ New dashboard" in a workspace; appears in left nav.
- H1.3 Dashboard-level settings: connected boards (add/remove), default date range (optional), auto-refresh in real time (F7: widgets refresh when underlying items change, debounced 5 s).
- AC-H1-1 Given a Private dashboard, when a non-invited Member opens it, then 404.

## H2 Layout — P1
12-column responsive grid; widgets added via "Add widget" (type picker), moved by drag, resized by handle (min 2×2), deleted, duplicated, renamed; layout saved for everyone (owners only can change).
- AC-H2-1 Given Mia (owner) moves and resizes a widget, then after reload all users see the new layout; given Raj (non-owner), then drag handles are absent and the layout API returns 403.

## H3 Widgets — P1: Number, Chart, Battery, Table; P2: Calendar, Gantt, Text/Notes, Listview
Each widget: title, data source = subset of dashboard boards (default all), widget filter (same rule model as D2.3), and type settings:

| Widget | Settings | Output |
|---|---|---|
| Number | calculation count \| column (Numbers/Formula/Mirror numeric); function sum/avg/median/min/max; include subitems; unit/prefix/suffix; format number/%/currency | single big number |
| Chart | graph type pie/donut/column/bar/line/area/stacked variants; X axis = Status/Dropdown/People/Group/Board/Date (by day/week/month/quarter/year)/Checkbox; Y = count or numeric column with function; Z (stack) for stacked types; sort; show values/legend | chart with tooltips; click a segment → list of items (drill-down) |
| Battery | status columns per board; optional numeric weight column | % done (items with is_done labels) bar with per-label segments |
| Table | boards, visible columns, filter, sort, group by | read-only table, item click opens item page |

**AC**
- AC-H3-1 Given 5 deals across 2 groups with Deal Value 70k, 55k, 30k, 10k, 0, then a Number widget sum = 165,000 and avg = 33,000.
- AC-H3-2 Given a column chart X = Expected Close Date by month, Y = sum Deal Value, then each month bar equals the sum for that month (items without date in "No date" bar, hideable).
- AC-H3-3 Given a pie by Stage, when the "Won" slice is clicked, then a list of exactly the Won deals opens.

## H4 CRM widgets — P1: Gauge, Funnel, Leaderboard; P2: Goal bar, Deal stages, Deal insights, Products, Activity tracker
| Widget | Settings | Output |
|---|---|---|
| Gauge (target) | numeric column + function, target value (static), period (this month/quarter/year/all by a date column), optional "done only" (is_done status) | semicircle gauge actual vs target with labels "Actual" / "Target" |
| Funnel | status column; ordered stages (label order, excluding chosen labels e.g. Lost); value = count or sum of numeric column | funnel bars of **current-stage** counts/sums with conversion % = stage n / stage n−1 |
| Leaderboard | People column, metric = count or sum of numeric column, filter (e.g. Stage = Won), period | ranked list with avatars, top 10; an item with several people credits the full value to each |

- AC-H4-1 Given 3 Won deals totaling 85,000 this year and target 100,000, then the Gauge shows Actual 85K / Target 100K.
- AC-H4-2 Given deals by stage New 10, Discovery 6, Proposal 3, Negotiation 2, Won 1, then the funnel shows those counts and conversion Discovery/New = 60%.

## H5 Dashboard filters — P1
- Free-text filter, person filter and advanced filter at dashboard level, applied on top of each widget's own filter; per-user temporary unless owner saves.
- AC-H5-1 Given person filter = Raj, then every widget recomputes using only items where any People column contains Raj.

- AC-H1-2 Given Sales Dashboard is connected to Deals, when Mia adds the Contacts board, then widgets can select Contacts columns.

## H6 Export dashboard — P3 (PDF/PNG).

## H7 Permission-aware data — P1
- H7.1 Widgets compute only over items the **viewing user** can see; a dashboard never reveals items/values from boards the viewer cannot access (those boards are listed as "1 board hidden").
- AC-H7-1 Given a dashboard connected to a Private board Vic can't access, when Vic views it, then totals exclude that board and a notice says "Some boards are hidden".

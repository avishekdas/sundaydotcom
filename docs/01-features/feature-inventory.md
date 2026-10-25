# Feature Inventory — monday.com Work Management + CRM

**Status:** v1.0 — approved scope (Step 1 of 5) · **Date:** 2026-10-24 · **Scope:** Work Management core + CRM, single organization
**Evidence:** trial account `avishekdascools-team-company` (monday CRM, workspace "CRM"), monday GraphQL schema, board/automation configs read via API, monday help-center articles.

Legend for proposed priority: **P1** = first release (MVP) · **P2** = second release · **P3** = later · **OUT** = excluded from this build.
Every ID below becomes a requirements section in Step 2.

---

## A. Platform & navigation

| ID | Feature | Observed / evidence | Prio |
|---|---|---|---|
| A1 | Account (single org), account settings, branding (name, logo) | Admin menu, top bar | P1 |
| A2 | Workspaces: create/rename/delete, open vs closed, members & owners, default workspace | Workspace "CRM" (open, default) | P1 |
| A3 | Folders inside workspaces (nesting, color, reorder) | API `create_folder/update_folder` | P2 |
| A4 | Left nav: workspace tree of boards/dashboards/docs, collapse, search within workspace | Left pane | P1 |
| A5 | Home / "My work" (items assigned to me across boards, due dates) | Home rail icon | P2 |
| A6 | Favorites (star boards/dashboards/docs, reorder) | Favorites rail, API `create_favorite` | P2 |
| A7 | Global search (Cmd+K) across items, boards, docs, updates, people | "Search for anything…" | P1 (items/boards), P2 (updates/docs) |
| A8 | Inbox (updates where I'm mentioned/subscribed) | Inbox icon with badge | P2 |
| A9 | Notifications bell (in-app), desktop/push/email channels, per-board mute, notification settings | Bell icon; API `update_mute_board_settings`, `update_notification_setting` | P1 in-app + email; P3 desktop push |
| A10 | Templates: board/workspace templates, "use template", save as template | API `use_template`, `save_workspace_as_template` | P2 (board), P3 (workspace) |
| A11 | Archive & trash with restore (30-day recovery), permanent delete | API `archive_*`, `delete_object` (30 days) | P1 |
| A12 | Undo last action | API `undo_action` | P2 |
| A13 | Import from Excel/CSV with column mapping; CRM import | "Import" button | P1 (CSV), P2 (XLSX) |
| A14 | Export board to Excel/CSV | API `create_board_export` | P1 |
| A15 | Activity log (board-level and item-level change history) | Item page "Activity Log" tab; API `activity_logs` | P1 |
| A16 | User profile (name, photo, title, timezone, working status/out-of-office) | API `OutOfOffice`, `UserUpdateInput` | P1 basic, P2 OOO |

## B. Boards, groups, items

| ID | Feature | Observed / evidence | Prio |
|---|---|---|---|
| B1 | Board CRUD; description; item terminology ("Contact", "Deal") | Every CRM board has `item_terminology` | P1 |
| B2 | Board kinds: Main (everyone), Private (invited), Shareable (guests) | `board_kind` public/private/share | P1 main+private, P2 shareable |
| B3 | Board owners & subscribers | `owners`, `add_users_to_board` | P1 |
| B4 | Duplicate board (structure only / with items / with updates) | `duplicate_board` | P2 |
| B5 | Groups: create, rename, color, collapse, reorder, duplicate, archive, delete, move items between groups | Contacts: Active/Inactive groups | P1 |
| B6 | Items: create (inline/"New contact" button/form), rename, duplicate, move to group, move to another board, archive, delete, drag-reorder | Table view | P1 |
| B7 | Subitems with their own column set (stored as a linked "Subitems of X" board) | `Subitems of Contacts/Deals/...` boards | P1 |
| B8 | Multi-level boards (nested subitems up to 5 levels, shared columns) | `hierarchy_type: multi_level` | P3 |
| B9 | Bulk actions on multi-selected items: duplicate, export, archive, delete, move, set column value | Row checkboxes | P1 |
| B10 | Required columns & validation rules on items | API `add_required_column`, `create_validation_rule` | P2 |
| B11 | Item limit per board (100k) and pagination | `items_limit: 100000` | P1 (design constraint) |
| B12 | Board-level column summaries in group footer (sum, avg, count, status distribution) | Group footer under each group | P1 |

## C. Column types

All column types exposed by the API. Each needs: value schema, settings schema, renderer, editor, filter operators, sort, aggregation, CSV mapping.

| ID | Column | Notes | Prio |
|---|---|---|---|
| C1 | Name (item title) | mandatory first column | P1 |
| C2 | Text | | P1 |
| C3 | Long text | | P1 |
| C4 | Numbers | unit symbol, left/right, footer sum/avg/min/max/median | P1 |
| C5 | Status | labels with colors, `is_done` flag, label order, deactivate label | P1 |
| C6 | Dropdown | multi-select labels | P1 |
| C7 | People | users and teams, max people setting | P1 |
| C8 | Date | date + optional time, reminders | P1 |
| C9 | Timeline | start–end range, milestone flag | P1 |
| C10 | Email | mailto, used by CRM email sync | P1 |
| C11 | Phone | country prefix/flag | P1 |
| C12 | Link | URL + display text | P1 |
| C13 | Checkbox | | P1 |
| C14 | Tags | account-wide tags | P2 |
| C15 | Rating | 1–5 stars | P2 |
| C16 | Progress / battery | rolls up status columns | P2 |
| C17 | Formula | expression over other columns (e.g. `{deal_value}*{deal_close_probability}`) | P1 |
| C18 | Connect boards (board_relation) | links items across one or more boards, display layout config, optional reflection column on target | P1 |
| C19 | Mirror | shows a column of linked items via a board_relation, with aggregation | P1 |
| C20 | Dependency | item → item predecessor links, used by Gantt | P2 |
| C21 | Files | upload, preview, versions | P1 |
| C22 | Button | triggers an automation | P1 (CRM "Move to Contacts") |
| C23 | Auto number | sequential per board | P2 |
| C24 | Item ID | read-only | P1 |
| C25 | Creation log | created by + created at | P1 |
| C26 | Last updated | updated by + updated at | P1 |
| C27 | Hour | time of day | P2 |
| C28 | Week | week picker | P3 |
| C29 | World clock / timezone | | P3 |
| C30 | Country | | P2 |
| C31 | Location | address + geocode | P3 |
| C32 | Color picker | | P3 |
| C33 | Vote | | P3 |
| C34 | Time tracking | start/stop timer, history | P3 |
| C35 | Team | | P2 |
| C36 | Doc / direct doc | item-attached document | P3 |
| C37 | Subitems column | P1 (with B7) |
| C38 | CRM "Activities timeline" column | mini-timeline of activities + quick add | P1 (with L5) |
| C39 | CRM "Active sequences" column | P3 (with L9) |
| C40 | Column operations: add, rename, describe, reorder, resize, hide per view, duplicate, delete, change type (where safe), column permissions | | P1 (perm: P2) |
| C41 | Managed (account-level) status/dropdown columns shared across boards | API `create_status_managed_column` | P3 |
| C42 | AI columns (summarize, categorize, translate, extract, write) | API `configure_*_ai_column` | OUT |

## D. Board views

Observed in "Add view" menu: Table, Activity analytics, Forecasting, Gantt, Chart, Calendar, Kanban, Doc, File gallery, Form, Dashboard, Build with Vibe, Apps.

| ID | View | Notes | Prio |
|---|---|---|---|
| D1 | Table (main) | inline edit, column resize/reorder, sticky header, group collapse, subitems expand | P1 |
| D2 | Table toolbar: Search, Person filter, Filter (AND/OR rule groups per column type), Sort (multi-key), Group by (any column), Hide columns, row height | toolbar on Contacts | P1 |
| D3 | Saved views: multiple named views per board, each with own filter/sort/columns; default view; rename/duplicate/delete; view permissions | Quotes/Invoices views are filtered tables | P1 |
| D4 | Conditional formatting (color rows/cells by rule) | API `ConditionalFormattingRuleInput` | P2 |
| D5 | Kanban | group lanes by status column, lane sums, card fields customizable, drag between lanes updates status | Deals "Pipeline" | P1 |
| D6 | Calendar | date/timeline columns; month/week/day; color by | P2 |
| D7 | Gantt / Timeline | timeline/date columns, group/color/label by, today line, dependencies, baselines | Client Projects "Gantt" | P2 |
| D8 | Chart view | pie/donut/column/bar/line/area/stacked; X/Y/Z axes; aggregation | Deals "Sales report" | P2 |
| D9 | Form view | see section I | Leads "Lead submission form" | P1 |
| D10 | File gallery | all files on board | P3 |
| D11 | Doc view | doc attached to board | P3 |
| D12 | Dashboard view (embedded dashboard on a board) | Products "Dashboard" | P2 |
| D13 | Activity analytics view (CRM) | activity counts by type/owner/period | P2 |
| D14 | Forecasting view (CRM) | weighted pipeline by period and forecast category | P2 |
| D15 | Map, Workload, Cards, other marketplace views | via Apps | P3 |
| D16 | "Build with Vibe" custom AI app view | | OUT |

## E. Item page (item card)

Observed tabs: Overview (Emails & Activities timeline + field panel), Updates, Quotes & Invoices, More → Activity Log; "+" adds Item Card, Activity analytics, Vibe app, Emails & Activities, Item description, File gallery, Chart, Dashboard, Quotes & Invoices.

| ID | Feature | Prio |
|---|---|---|
| E1 | Item page modal / full page with deep link URL (`/boards/{b}/pulses/{i}`), prev/next navigation | P1 |
| E2 | Field panel: all columns editable in a vertical form | P1 |
| E3 | Updates feed: rich text, @mentions (user/team), replies, likes, pin to top, edit/delete, attach files, watchers | P1 |
| E4 | Activity log per item | P1 |
| E5 | Item description (rich doc) | P2 |
| E6 | Configurable item tabs (add/remove/reorder item views) | P2 |
| E7 | Item-level file gallery | P3 |
| E8 | AI "Summarize" / Sidekick on item | OUT |

## F. Collaboration, users, teams

| ID | Feature | Prio |
|---|---|---|
| F1 | Invite users by email; activate/deactivate users | P1 |
| F2 | User types: Admin, Member, Viewer, Guest | P1 |
| F3 | Teams (create, members, owners) and Departments | P2 (teams), P3 (departments) |
| F4 | Subscribe/unsubscribe to board/item | P1 |
| F5 | Mentions in updates and docs trigger notifications | P1 |
| F6 | Email notifications digest | P2 |
| F7 | Real-time collaboration: live updates of board changes to all viewers, presence avatars | P1 |

## G. Automations

Model observed: **trigger → optional condition(s) → one or more actions**, sentence templates with placeholders, per-board automation center (Create / Manage / Run history), active toggle, account-wide "autopilot hub", monthly action quota. Newer "workflows" are multi-step block graphs (seen on Leads board: status→create item & connect→create item).

| ID | Feature | Prio |
|---|---|---|
| G1 | Automation engine: trigger/condition/action, variable interpolation (`{pulse.name}`, `{pulse.deal_value}`), field mapping between boards | P1 |
| G2 | Triggers: item created; column changes; status changes to X; date arrives / X days before; button clicked; item moved to group; subitem created; update posted; person assigned; every time period (recurring) | P1 (first 6), P2 (rest) |
| G3 | Conditions: only if column = value; only if person; and-combinations | P1 |
| G4 | Actions: notify (me/user/people column/subscribers/team); set column value; clear column; move to group; move to board; create item in board & connect; create subitem; duplicate; archive; delete; assign person; push date; create update; send email | P1 (first 9), P2 (rest) |
| G5 | Cross-board automations (create & connect items, mirror on match) | P1 (CRM conversion depends on it) |
| G6 | Recipe catalog with categories (Status change, Item creation, Notifications, Due dates, Move item…) | P1 (curated list) |
| G7 | Run history / logs per automation with errors | P1 |
| G8 | Multi-step workflow builder (block graph, branching) | P3 |
| G9 | Action usage quota & account automation hub | P3 |
| G10 | Integration recipes (Gmail/Outlook/Slack/Zoom/etc.) | P3 (CRM email is L11) |

**Seeded CRM automations observed (must ship as defaults):**
1. Leads: when Status → *Qualified*, move to group *Qualified leads*.
2. Leads: when Status → *Qualified*, create Contact (name, email, phone, Type=Qualified Lead) connected via *Leads* column, then create Deal (name "{company} Deal", stage *New*, main contact email, last interaction).
3. Leads: when item created, set Status to *New Lead*.
4. Leads: when "Move to Contacts" button clicked, move item to Contacts (map name/phone/email).
5. Leads/Contacts/Deals: when an email/activity is created, set *Last interaction* = today.
6. Leads/Contacts/Deals: when activity created in Emails & Activities, create item in Activities board and connect via *Related item*.
7. Leads/Contacts/Deals: notify subscribers when email is opened / new email arrives.
8. Deals: when Stage changes to Negotiation/New/Discovery → move to *Active Deals*; Won → move to *Closed Won*.
9. Deals: when item created, connect to Contact where *Main contact email* matches Contact *Email*.
10. Deals: when Stage → Won, notify board subscribers "Congratulations! {name} worth ${deal_value} has been won!".
11. Deals: when Stage → Won, create Client Project "{deal} - New project" (owner = deal owner) connected via *Deals*.

## H. Dashboards

Observed "Sales Dashboard": Annual Target (gauge), Monthly Target (goal bar), Average deal (number), Active deals value (number), Deal status distribution (pie), Actual revenue by month (column). Toolbar: Add widget, connected boards, filter, people filter, export, invite.

| ID | Feature | Prio |
|---|---|---|
| H1 | Dashboard CRUD, Main/Private, connect up to N boards | P1 |
| H2 | Grid layout: add/resize/move widgets | P1 |
| H3 | Widgets: Number (sum/avg/median/min/max/count), Chart (all graph types, X/Y/Z, group by date), Battery, Table/List, Calendar, Gantt, Text/Notes | P1 (Number, Chart, Battery, Table), P2 (others) |
| H4 | CRM widgets: Gauge (target vs actual), Goal/target bar, Funnel, Deal stages, Deal insights, Leaderboard, Sales gauge, Products, Activity tracker | P1 (Gauge, Funnel, Leaderboard), P2 (rest) |
| H5 | Dashboard-level filter and person filter applied to all widgets | P1 |
| H6 | Export dashboard (PDF/image) | P3 |
| H7 | Respect source-board permissions in widgets | P1 |

## I. Forms (WorkForms)

| ID | Feature | Prio |
|---|---|---|
| I1 | Form bound to a board; each question maps to a column; submission creates an item in a chosen group | P1 |
| I2 | Public share link (no login), optional require-login, password | P1 link, P2 password/login |
| I3 | Question types per column type, required flag, description, ordering, page blocks | P1 |
| I4 | Conditional (show-if) logic | P2 |
| I5 | Appearance: logo, colors, background, layout, submit button text, after-submit message/redirect | P2 |
| I6 | Close date, response limit, prefill via URL params, UTM tags | P3 |
| I7 | Spam protection (captcha/rate limit) | P1 (security need, not observed) |

## J. Docs

| ID | Feature | Prio |
|---|---|---|
| J1 | Workspace docs: rich blocks (text, headings, lists, tables, images, code, notice box, divider) | P3 |
| J2 | Real-time co-editing, mentions, comments, version history | P3 |
| J3 | Embed board/item in doc | P3 |

## K. Permissions & administration

| ID | Feature | Prio |
|---|---|---|
| K1 | Account roles Admin/Member/Viewer/Guest and account permission matrix (who can create boards, invite guests, export, create automations, generate API tokens) | P1 roles, P2 matrix |
| K2 | Workspace roles: owner / member / non-member; workspace permissions | P1 |
| K3 | Board permission sets: Edit everything / Only edit content / Only edit assigned items / View and comment | P1 |
| K4 | Column permissions (restrict view/edit per column) | P2 |
| K5 | View permissions (who can edit a saved view) | P2 |
| K6 | Dashboard permissions (main/private, owners vs viewers) | P1 |
| K7 | Authentication: email+password, email verification, password reset, MFA, Google SSO | P1 (email+pw, reset, MFA), P2 (Google SSO), P3 (SAML) |
| K8 | Session management, login history | P2 |
| K9 | Audit log (admin) | P2 |
| K10 | API tokens per user; service users | P2 |
| K11 | Billing / plans / seats | OUT (single org, self-hosted) |

## L. CRM

Seeded boards observed: **Leads, Contacts, Accounts, Deals, Activities, Quotes & Invoices, Products & Services, Client Projects**, plus **Sales Dashboard**. Relations: Contact↔Account, Contact↔Deal, Deal→Account (mirror via Contact), Contact↔Lead, Activity→{Lead, Contact, Account, Deal}, Project↔{Deal, Contact, Account}, Quote line item→{Product, Deal, Contact}.

| ID | Feature | Detail observed | Prio |
|---|---|---|---|
| L1 | CRM workspace template | creates all boards, columns, relations, views, automations, dashboard above | P1 |
| L2 | Leads | Status (New Lead, Attempted to contact, Contacted, Qualified, Unqualified), Company, Title, Email, Phone, Lead Source, Owner, Last interaction, "Move to Contacts" button, Active sequences; groups New / Qualified | P1 |
| L3 | Lead capture form | public form on Leads board | P1 |
| L4 | Lead → Contact + Deal conversion | via automations 1–4 | P1 |
| L5 | Contacts | Email, Accounts, Deals, Deals value (mirror sum), Phone, Title, Type (Lead/Qualified Lead/Customer/Vendor/Partner), Priority, Comments, Leads link; Active/Inactive groups | P1 |
| L6 | Accounts | Domain, Contacts, Deals (mirror), Industry (47-value dropdown), Description, Employees, HQ, Company profile | P1 |
| L7 | Account auto-enrichment from domain (Crunchbase) | | OUT |
| L8 | Deals | Stage (New, Discovery, Proposal, Negotiation, Won, Lost), Owner, Deal Value ($), Contacts, Accounts (mirror), Expected close date, Close probability %, Forecast value (formula), Last interaction, Quotes & Invoices, Main contact email, Forecast category (Best case/Pipeline/Commit), Tasks (subitems); groups Active / Closed Won | P1 |
| L9 | Pipeline Kanban with stage value sums | Deals "Pipeline" view | P1 |
| L10 | Emails & Activities timeline on Lead/Contact/Account/Deal | New email, Call, Add activity (Meeting, Call summary, Phone call, Note, custom), timeline grouped by month, filters, search, reactions on entries | P1 (activities), see L11 for email |
| L11 | CRM email via Amazon SES (D-006): send from item, replies to a tracking address matched to the item and threaded on its timeline, open tracking | | P2 |
| L12 | Email templates (personal + shared) with merge fields | P2 |
| L13 | Custom activity types (name, icon, color) | P2 |
| L14 | Activities board auto-populated from timeline | P1 |
| L15 | Products & Services catalog | Description, Price, SKU, Type (Service/Inventory) | P1 |
| L16 | Quotes & Invoices | Type, Amount, Recipient, File, Status (Working on it, Approved, Sent to client, Paid, Cancelled), Issue date, Owner; line items as subitems: product, description, unit price, qty, multipliers, base price, discount %/value, fee %/value, tax %/value, total, currency; Quotes/Invoices filtered views | P2 |
| L17 | Quote/invoice PDF generation and send to client | P2 |
| L18 | Client Projects (post-sale) | Owner, Priority, Timeline, Status, Deals, Contact, Accounts, Phone, Email, File; Gantt view | P1 |
| L19 | Manage duplicates (detect by column match, merge items) | P2 |
| L20 | Round-robin assignment automation | P2 |
| L21 | Sequences (multi-step scheduled emails, enrol items, stop on reply, analytics) | P3 |
| L22 | Mass emails / campaigns with tracking | P3 |
| L23 | Shared team inbox | P3 |
| L24 | Sales Dashboard + CRM widgets | see H4 | P1 |
| L25 | Forecasting & Activity analytics views | see D13/D14 | P2 |
| L26 | Meeting notetaker, AI lead/sales agents, AI email composer, AI summaries | | OUT |

## M. Integrations & developer platform

| ID | Feature | Prio |
|---|---|---|
| M1 | Public API for all entities (monday uses GraphQL) | P1 (internal API used by our UI), P2 (documented public API + tokens) |
| M2 | Outbound webhooks on board events | P2 |
| M3 | Integrations marketplace & third-party apps (Slack, Zoom, Teams, Jira…) | OUT (revisit later) |
| M4 | App framework (custom board/item views, custom automation blocks) | OUT |

## N. AI features (catalogued, excluded per scope)

Sidekick assistant, "Ask, create, analyze" bar, AI Agents, Vibe app builder, Notetaker, AI columns, AI summaries, AI email composer, CRM AI Lead/Sales agents, AI board builder. **All OUT.**

## O. Clients & non-functional (not observed in UI, needed for parity)

| ID | Item | Prio |
|---|---|---|
| O1 | Responsive web app (desktop-first; usable on tablet) | P1 |
| O2 | Native iOS/Android apps | OUT |
| O3 | Keyboard shortcuts | P2 |
| O4 | Light/dark theme | P2 |
| O5 | i18n (English only first) | P1 English |
| O6 | Accessibility (WCAG 2.1 AA target) | P2 |

---

## Counts

| Priority | Approx. features |
|---|---|
| P1 | ~95 |
| P2 | ~55 |
| P3 | ~30 |
| OUT | ~15 groups |

## Open questions to reach 95% confidence before Step 2

Resolved — see `../00-decision-log.md` (D-001 … D-009).

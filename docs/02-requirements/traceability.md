# Traceability — Inventory → Requirements → Acceptance Criteria

Requirement file = the area file that specifies the feature. # ACs = ACs whose ID starts with `AC-<id>-`. Step 4 adds test files; Step 5 fills status.

| Inv. ID | Feature | Priority | Requirement file | # ACs | Also covered by |
|---|---|---|---|---|---|
| A1 | Account (single org), account settings, branding (name, logo | P1 | 01-platform.md | 3 |  |
| A2 | Workspaces: create/rename/delete, open vs closed, members &  | P1 | 01-platform.md | 3 |  |
| A3 | Folders inside workspaces (nesting, color, reorder) | P2 | 01-platform.md | 0 |  |
| A4 | Left nav: workspace tree of boards/dashboards/docs, collapse | P1 | 01-platform.md | 2 |  |
| A5 | Home / "My work" (items assigned to me across boards, due da | P2 | 01-platform.md | 0 |  |
| A6 | Favorites (star boards/dashboards/docs, reorder) | P2 | 01-platform.md | 0 |  |
| A7 | Global search (Cmd+K) across items, boards, docs, updates, p | P1/P2 | 01-platform.md | 3 |  |
| A8 | Inbox (updates where I'm mentioned/subscribed) | P2 | 01-platform.md | 0 |  |
| A9 | Notifications bell (in-app), desktop/push/email channels, pe | P1/P3 | 01-platform.md | 4 |  |
| A10 | Templates: board/workspace templates, "use template", save a | P2/P3 | 01-platform.md | 0 |  |
| A11 | Archive & trash with restore (30-day recovery), permanent de | P1 | 01-platform.md | 5 |  |
| A12 | Undo last action | P2 | 01-platform.md | 0 |  |
| A13 | Import from Excel/CSV with column mapping; CRM import | P1/P2 | 01-platform.md | 3 |  |
| A14 | Export board to Excel/CSV | P1 | 01-platform.md | 2 |  |
| A15 | Activity log (board-level and item-level change history) | P1 | 01-platform.md | 2 |  |
| A16 | User profile (name, photo, title, timezone, working status/o | P1/P2 | 01-platform.md | 1 |  |
| B1 | Board CRUD; description; item terminology ("Contact", "Deal" | P1 | 02-boards-items.md | 3 |  |
| B2 | Board kinds: Main (everyone), Private (invited), Shareable ( | P1/P2 | 02-boards-items.md | 1 |  |
| B3 | Board owners & subscribers | P1 | 02-boards-items.md | 1 |  |
| B4 | Duplicate board (structure only / with items / with updates) | P2 | 02-boards-items.md | 0 |  |
| B5 | Groups: create, rename, color, collapse, reorder, duplicate, | P1 | 02-boards-items.md | 3 |  |
| B6 | Items: create (inline/"New contact" button/form), rename, du | P1 | 02-boards-items.md | 8 |  |
| B7 | Subitems with their own column set (stored as a linked "Subi | P1 | 02-boards-items.md | 4 |  |
| B8 | Multi-level boards (nested subitems up to 5 levels, shared c | P3 | 02-boards-items.md | 0 |  |
| B9 | Bulk actions on multi-selected items: duplicate, export, arc | P1 | 02-boards-items.md | 3 |  |
| B10 | Required columns & validation rules on items | P2 | 02-boards-items.md | 0 |  |
| B11 | Item limit per board (100k) and pagination | P1 | 02-boards-items.md | 2 |  |
| B12 | Board-level column summaries in group footer (sum, avg, coun | P1 | 02-boards-items.md | 2 |  |
| C1 | Name (item title) | P1 | 03-columns.md | 1 |  |
| C2 | Text | P1 | 03-columns.md | 1 |  |
| C3 | Long text | P1 | 03-columns.md | 1 |  |
| C4 | Numbers | P1 | 03-columns.md | 2 |  |
| C5 | Status | P1 | 03-columns.md | 1 |  |
| C6 | Dropdown | P1 | 03-columns.md | 1 |  |
| C7 | People | P1 | 03-columns.md | 1 |  |
| C8 | Date | P1 | 03-columns.md | 3 |  |
| C9 | Timeline | P1 | 03-columns.md | 1 |  |
| C10 | Email | P1 | 03-columns.md | 1 |  |
| C11 | Phone | P1 | 03-columns.md | 1 |  |
| C12 | Link | P1 | 03-columns.md | 1 |  |
| C13 | Checkbox | P1 | 03-columns.md | 1 |  |
| C14 | Tags | P2 | 03-columns.md | 0 |  |
| C15 | Rating | P2 | 03-columns.md | 0 |  |
| C16 | Progress / battery | P2 | 03-columns.md | 0 |  |
| C17 | Formula | P1 | 03-columns.md | 6 |  |
| C18 | Connect boards (board_relation) | P1 | 03-columns.md | 3 |  |
| C19 | Mirror | P1 | 03-columns.md | 2 |  |
| C20 | Dependency | P2 | 03-columns.md | 0 |  |
| C21 | Files | P1 | 03-columns.md | 2 |  |
| C22 | Button | P1 | 03-columns.md | 1 |  |
| C23 | Auto number | P2 | 03-columns.md | 0 |  |
| C24 | Item ID | P1 | 03-columns.md | 1 |  |
| C25 | Creation log | P1 | 03-columns.md | 1 |  |
| C26 | Last updated | P1 | 03-columns.md | 1 |  |
| C27 | Hour | P2 | 03-columns.md | 0 |  |
| C28 | Week | P3 | 03-columns.md | 0 |  |
| C29 | World clock / timezone | P3 | 03-columns.md | 0 |  |
| C30 | Country | P2 | 03-columns.md | 0 |  |
| C31 | Location | P3 | 03-columns.md | 0 |  |
| C32 | Color picker | P3 | 03-columns.md | 0 |  |
| C33 | Vote | P3 | 03-columns.md | 0 |  |
| C34 | Time tracking | P3 | 03-columns.md | 0 |  |
| C35 | Team | P2 | 03-columns.md | 0 |  |
| C36 | Doc / direct doc | P3 | 03-columns.md | 0 |  |
| C37 | Subitems column | P1 | 03-columns.md | 1 | AC-B7-* |
| C38 | CRM "Activities timeline" column | P1 | 03-columns.md | 1 |  |
| C39 | CRM "Active sequences" column | P3 | 03-columns.md | 0 |  |
| C40 | Column operations: add, rename, describe, reorder, resize, h | P1/P2 | 03-columns.md | 3 |  |
| C41 | Managed (account-level) status/dropdown columns shared acros | P3 | 03-columns.md | 0 |  |
| C42 | AI columns (summarize, categorize, translate, extract, write | OUT | 03-columns.md | 0 |  |
| D1 | Table (main) | P1 | 04-views.md | 2 |  |
| D2 | Table toolbar: Search, Person filter, Filter (AND/OR rule gr | P1 | 04-views.md | 3 |  |
| D3 | Saved views: multiple named views per board, each with own f | P1 | 04-views.md | 3 |  |
| D4 | Conditional formatting (color rows/cells by rule) | P2 | 04-views.md | 0 |  |
| D5 | Kanban | P1 | 04-views.md | 3 |  |
| D6 | Calendar | P2 | 04-views.md | 0 |  |
| D7 | Gantt / Timeline | P2 | 04-views.md | 0 |  |
| D8 | Chart view | P2 | 04-views.md | 0 |  |
| D9 | Form view | P1 | 04-views.md | 0 | AC-I1-*, AC-I3-* |
| D10 | File gallery | P3 | 04-views.md | 0 |  |
| D11 | Doc view | P3 | 04-views.md | 0 |  |
| D12 | Dashboard view (embedded dashboard on a board) | P2 | 04-views.md | 0 |  |
| D13 | Activity analytics view (CRM) | P2 | 04-views.md | 0 |  |
| D14 | Forecasting view (CRM) | P2 | 04-views.md | 0 |  |
| D15 | Map, Workload, Cards, other marketplace views | P3 | 04-views.md | 0 |  |
| D16 | "Build with Vibe" custom AI app view | OUT | 04-views.md | 0 |  |
| E1 | Item page modal / full page with deep link URL (`/boards/{b} | P1 | 05-item-page-collaboration.md | 3 |  |
| E2 | Field panel: all columns editable in a vertical form | P1 | 05-item-page-collaboration.md | 1 |  |
| E3 | Updates feed: rich text, @mentions (user/team), replies, lik | P1 | 05-item-page-collaboration.md | 4 |  |
| E4 | Activity log per item | P1 | 05-item-page-collaboration.md | 1 |  |
| E5 | Item description (rich doc) | P2 | 05-item-page-collaboration.md | 0 |  |
| E6 | Configurable item tabs (add/remove/reorder item views) | P2 | 05-item-page-collaboration.md | 0 |  |
| E7 | Item-level file gallery | P3 | 05-item-page-collaboration.md | 0 |  |
| E8 | AI "Summarize" / Sidekick on item | OUT | 05-item-page-collaboration.md | 0 |  |
| F1 | Invite users by email; activate/deactivate users | P1 | 05-item-page-collaboration.md | 3 |  |
| F2 | User types: Admin, Member, Viewer, Guest | P1 | 05-item-page-collaboration.md | 0 | AC-K1-*, AC-K3-* |
| F3 | Teams (create, members, owners) and Departments | P2/P3 | 05-item-page-collaboration.md | 0 |  |
| F4 | Subscribe/unsubscribe to board/item | P1 | 05-item-page-collaboration.md | 1 |  |
| F5 | Mentions in updates and docs trigger notifications | P1 | 05-item-page-collaboration.md | 0 | AC-E3-1 |
| F6 | Email notifications digest | P2 | 05-item-page-collaboration.md | 0 |  |
| F7 | Real-time collaboration: live updates of board changes to al | P1 | 05-item-page-collaboration.md | 5 |  |
| G1 | Automation engine: trigger/condition/action, variable interp | P1 | 06-automations.md | 10 |  |
| G2 | Triggers: item created; column changes; status changes to X; | P1/P2 | 06-automations.md | 0 | AC-G1-*, AC-L4-* |
| G3 | Conditions: only if column = value; only if person; and-comb | P1 | 06-automations.md | 1 |  |
| G4 | Actions: notify (me/user/people column/subscribers/team); se | P1/P2 | 06-automations.md | 0 | AC-G1-*, AC-L4-* |
| G5 | Cross-board automations (create & connect items, mirror on m | P1 | 06-automations.md | 1 |  |
| G6 | Recipe catalog with categories (Status change, Item creation | P1 | 06-automations.md | 1 |  |
| G7 | Run history / logs per automation with errors | P1 | 06-automations.md | 1 |  |
| G8 | Multi-step workflow builder (block graph, branching) | P3 | 06-automations.md | 0 |  |
| G9 | Action usage quota & account automation hub | P3 | 06-automations.md | 0 |  |
| G10 | Integration recipes (Gmail/Outlook/Slack/Zoom/etc.) | P3 | 06-automations.md | 0 |  |
| H1 | Dashboard CRUD, Main/Private, connect up to N boards | P1 | 07-dashboards.md | 2 |  |
| H2 | Grid layout: add/resize/move widgets | P1 | 07-dashboards.md | 1 |  |
| H3 | Widgets: Number (sum/avg/median/min/max/count), Chart (all g | P1/P2 | 07-dashboards.md | 3 |  |
| H4 | CRM widgets: Gauge (target vs actual), Goal/target bar, Funn | P1/P2 | 07-dashboards.md | 2 |  |
| H5 | Dashboard-level filter and person filter applied to all widg | P1 | 07-dashboards.md | 1 |  |
| H6 | Export dashboard (PDF/image) | P3 | 07-dashboards.md | 0 |  |
| H7 | Respect source-board permissions in widgets | P1 | 07-dashboards.md | 1 |  |
| I1 | Form bound to a board; each question maps to a column; submi | P1 | 08-forms.md | 2 |  |
| I2 | Public share link (no login), optional require-login, passwo | P1/P2 | 08-forms.md | 1 |  |
| I3 | Question types per column type, required flag, description,  | P1 | 08-forms.md | 2 |  |
| I4 | Conditional (show-if) logic | P2 | 08-forms.md | 0 |  |
| I5 | Appearance: logo, colors, background, layout, submit button  | P2 | 08-forms.md | 0 |  |
| I6 | Close date, response limit, prefill via URL params, UTM tags | P3 | 08-forms.md | 0 |  |
| I7 | Spam protection (captcha/rate limit) | P1 | 08-forms.md | 2 |  |
| J1 | Workspace docs: rich blocks (text, headings, lists, tables,  | P3 | — (P3, not detailed) | 0 |  |
| J2 | Real-time co-editing, mentions, comments, version history | P3 | — (P3, not detailed) | 0 |  |
| J3 | Embed board/item in doc | P3 | — (P3, not detailed) | 0 |  |
| K1 | Account roles Admin/Member/Viewer/Guest and account permissi | P1/P2 | 09-permissions-admin.md | 2 |  |
| K2 | Workspace roles: owner / member / non-member; workspace perm | P1 | 09-permissions-admin.md | 2 |  |
| K3 | Board permission sets: Edit everything / Only edit content / | P1 | 09-permissions-admin.md | 4 |  |
| K4 | Column permissions (restrict view/edit per column) | P2 | 09-permissions-admin.md | 0 |  |
| K5 | View permissions (who can edit a saved view) | P2 | 09-permissions-admin.md | 0 |  |
| K6 | Dashboard permissions (main/private, owners vs viewers) | P1 | 09-permissions-admin.md | 1 |  |
| K7 | Authentication: email+password, email verification, password | P1/P2/P3 | 09-permissions-admin.md | 3 |  |
| K8 | Session management, login history | P2 | 09-permissions-admin.md | 0 |  |
| K9 | Audit log (admin) | P2 | 09-permissions-admin.md | 0 |  |
| K10 | API tokens per user; service users | P2 | 09-permissions-admin.md | 0 |  |
| K11 | Billing / plans / seats | OUT | 09-permissions-admin.md | 0 |  |
| L1 | CRM workspace template | P1 | 10-crm.md | 3 | AC-L2-1 |
| L2 | Leads | P1 | 10-crm.md | 1 |  |
| L3 | Lead capture form | P1 | 10-crm.md | 0 | AC-I1-1, AC-I7-* |
| L4 | Lead → Contact + Deal conversion | P1 | 10-crm.md | 3 |  |
| L5 | Contacts | P1 | 10-crm.md | 1 |  |
| L6 | Accounts | P1 | 10-crm.md | 1 |  |
| L7 | Account auto-enrichment from domain (Crunchbase) | OUT | 10-crm.md | 0 |  |
| L8 | Deals | P1 | 10-crm.md | 1 |  |
| L9 | Pipeline Kanban with stage value sums | P1 | 10-crm.md | 1 |  |
| L10 | Emails & Activities timeline on Lead/Contact/Account/Deal | P1 | 10-crm.md | 6 | AC-C38-1 |
| L11 | CRM email via Amazon SES (D-006): send from item, replies to | P2 | 10-crm.md | 0 |  |
| L12 | Email templates (personal + shared) with merge fields | P2 | 10-crm.md | 0 |  |
| L13 | Custom activity types (name, icon, color) | P2 | 10-crm.md | 0 |  |
| L14 | Activities board auto-populated from timeline | P1 | 10-crm.md | 1 | AC-L10-* |
| L15 | Products & Services catalog | P1 | 10-crm.md | 1 |  |
| L16 | Quotes & Invoices | P2 | 10-crm.md | 0 |  |
| L17 | Quote/invoice PDF generation and send to client | P2 | 10-crm.md | 0 |  |
| L18 | Client Projects (post-sale) | P1 | 10-crm.md | 1 |  |
| L19 | Manage duplicates (detect by column match, merge items) | P2 | 10-crm.md | 0 |  |
| L20 | Round-robin assignment automation | P2 | 10-crm.md | 0 |  |
| L21 | Sequences (multi-step scheduled emails, enrol items, stop on | P3 | 10-crm.md | 0 |  |
| L22 | Mass emails / campaigns with tracking | P3 | 10-crm.md | 0 |  |
| L23 | Shared team inbox | P3 | 10-crm.md | 0 |  |
| L24 | Sales Dashboard + CRM widgets | P1 | 10-crm.md | 1 | AC-H3-*, AC-H4-* |
| L25 | Forecasting & Activity analytics views | P2 | 10-crm.md | 0 |  |
| L26 | Meeting notetaker, AI lead/sales agents, AI email composer,  | OUT | 10-crm.md | 0 |  |
| M1 | Public API for all entities (monday uses GraphQL) | P1/P2 | 11-api-nfr.md | 3 |  |
| M2 | Outbound webhooks on board events | P2 | 11-api-nfr.md | 0 |  |
| M3 | Integrations marketplace & third-party apps (Slack, Zoom, Te | OUT | 11-api-nfr.md | 0 |  |
| M4 | App framework (custom board/item views, custom automation bl | OUT | 11-api-nfr.md | 0 |  |
| O1 | Responsive web app (desktop-first; usable on tablet) | P1 | 11-api-nfr.md | 1 |  |
| O2 | Native iOS/Android apps | OUT | 11-api-nfr.md | 0 |  |
| O3 | Keyboard shortcuts | P2 | 11-api-nfr.md | 0 |  |
| O4 | Light/dark theme | P2 | 11-api-nfr.md | 0 |  |
| O5 | i18n (English only first) | P1 | 11-api-nfr.md | 1 |  |
| O6 | Accessibility (WCAG 2.1 AA target) | P2 | 11-api-nfr.md | 0 |  |

**Totals:** 191 unique acceptance criteria. P1 items without direct or cross coverage: none.

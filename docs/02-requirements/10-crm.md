# 10 — CRM (Area L)

All CRM behavior is built from generic platform features (boards, columns, views, automations, dashboards) plus three CRM-specific capabilities: the **Activity timeline** (L10/L14, C38 — a view over the Activities board, D-011), the **CRM workspace template** (L1), and CRM widgets (H4). No CRM rule may require hard-coded logic outside these.

## L1 CRM workspace template — P1
**Story:** As Ada, I create a ready-to-use CRM workspace in one click.
**Rules**
- L1.1 "Create from template → CRM" creates workspace "CRM" (name editable) containing the boards, columns, labels, groups, views, relations, automations and dashboard below, with optional sample data (3 accounts, 3 contacts, 5 deals, 2 leads, 3 projects, 6 activities) — sample data toggle default ON.
- L1.2 Entity boards (Leads, Contacts, Accounts, Deals) are flagged `crm_entity_type` = lead|contact|account|deal, which enables the Overview tab with timeline (E1.3) and the Activities timeline column.
- L1.3 Template creation is atomic: on failure nothing is left behind.
- L1.4 Everything created is editable afterwards like any user-built content.
**AC**
- AC-L1-1 Given Ada applies the CRM template in P1, then exactly this manifest exists: **boards** Leads, Contacts, Accounts, Deals, Activities, Products & Services, Client Projects (7) with schemas per L1-spec; **subitem boards** for Contacts, Deals, Client Projects (3); **dashboard** Sales Dashboard (1) with 8 widgets; **automations** per the L1-automations table — 14 active (Leads: 1, 2, 3, 4, 5; Contacts: 5; Deals: 5, 8a, 8b, 8c, 9a, 9b, 10, 11), owned by Ada.
- AC-L1-3 Given the template is applied, then every seeded automation is listed in the automation center as an ordinary recipe that can be edited, deactivated or deleted.
- AC-L1-2 Given the template run fails at step N (fault injected), then no CRM boards remain.

### L1-spec Board schemas (labels in display order)

**Leads** (term "Lead"; groups: New Leads [top], Qualified leads)
| Column (id) | Type | Settings |
|---|---|---|
| Name | name | |
| Status (lead_status) | status | New Lead, Attempted to contact, Contacted, Qualified, Unqualified (no done label, as in monday) |
| Activities timeline | C38 | |
| Company (lead_company) | text | |
| Title (lead_title) | text | |
| Email (lead_email) | email | |
| Phone (lead_phone) | phone | |
| Lead Source (lead_source) | status | Web form, Email, LinkedIn, Google ads, Facebook ads, Referral |
| Last interaction (last_interaction) | date | |
| Create a contact (convert_button) | button | text "Move to Contacts", green |
| Owner (lead_owner) | people | |
| Contacts (lead_contacts) | connect boards → Contacts | reflected as Contacts.Leads; single — deliberate addition (D-014) |
Views: Main table; Form "Lead submission form" (Name, Status hidden, Company, Title, Email, Phone, Lead Source hidden default "Web form").

**Contacts** (term "Contact"; groups: Active Contacts [top], Inactive Contacts; subitems: Name, Owner, Status, Date)
| Column | Type | Settings |
|---|---|---|
| Name | name | |
| Email (contact_email) | email | |
| Activities timeline | C38 | |
| Accounts (contact_account) | connect → Accounts | reflected as Accounts.Contacts, single |
| Deals (contact_deal) | connect → Deals | reflected as Deals.Contacts, multiple |
| Deals value (contact_deals_value) | mirror of contact_deal → Deals.deal_value | sum |
| Phone (contact_phone) | phone | |
| Title (contact_title) | dropdown | CEO, COO, CIO, CFO, CTO, VP Sales, Manager, Other |
| Type (contact_type) | status | Lead, Qualified Lead, Customer (done), Vendor, Partner |
| Priority (contact_priority) | status | High, Medium, Low |
| Comments (contact_comments) | long text | |
| Leads (contact_leads) | connect → Leads | hidden in Main table |
| Last interaction | date | |

**Accounts** (term "Account"; group: Companies)
| Column | Type | Settings |
|---|---|---|
| Name | name | |
| Domain (account_domain) | link | |
| Contacts (account_contact) | connect → Contacts (reflection of contact_account) | multiple |
| Deals (account_deal) | mirror of account_contact → Contacts.contact_deal | distinct |
| Industry | dropdown | 47-value industry list (see appendix A) |
| Description | long text | |
| No. of employees | text | |
| Headquarters location | text | |
| Activities timeline | C38 | |

**Deals** (term "Deal"; groups: Active Deals [top], Closed Won, Closed Lost*; subitems "Tasks": Name, Owner, Status, Date)
| Column | Type | Settings |
|---|---|---|
| Name | name | |
| Stage (deal_stage) | status | New, Discovery, Proposal, Negotiation, Won (done), Lost |
| Owner (deal_owner) | people | |
| Deal Value (deal_value) | numbers | $ left |
| Contacts (deal_contact) | connect → Contacts | reflection of contact_deal |
| Accounts (deal_account) | mirror of deal_contact → Contacts.contact_account | distinct |
| Expected Close Date | date | |
| Close Probability (deal_close_probability) | numbers | % right, 0–100 |
| Forecast Value (deal_forecast_value) | formula | `{deal_value} * {deal_close_probability} / 100` |
| Forecast category | status | Commit, Best case, Pipeline |
| Last interaction | date | |
| Main contact email (deal_main_email) | email | |
| Projects (deal_projects) | connect → Client Projects | reflection of project_deal |
| Activities timeline | C38 | |
\* *Closed Lost* group is an intentional improvement over the observed template (which only moves Won); see automation 8.
Views: Main table; Pipeline (Kanban by Stage, card fields Deal Value, Contacts, Owner, Expected Close Date; lane sum Deal Value); Sales report (Chart view P2 — in P1 shown as link to Sales Dashboard).

**Activities** (term "Activity"; group: Account Activities) — the single store of CRM timeline activities (D-011)
| Column | Type | Settings |
|---|---|---|
| Name | name | "<source item> - <activity type>" |
| Owner | people | |
| Activity Type | status | Meeting, Call summary, Phone call, Note, Email (P2) |
| Start time | date (time) | |
| End time | date (time) | |
| Status | status | Open, Done (done) |
| Related item | connect → Leads, Contacts, Accounts, Deals | multiple boards, no reflection (C18.7) |
| Title | text | |
| Body | long text (rich) | |
| Participants | people | |

**Products & Services** (group: Products) — Name, Description (long text), Price (numbers $), SKU (text), Type (status: Inventory, Service). P1.
**Quotes & Invoices** — P2 (L16).
**Client Projects** (term "Project"; groups: New Projects [top], Completed; subitems Name, Owner, Status, Date)
| Column | Type | Settings |
|---|---|---|
| Name | name | |
| Owner | people | |
| Priority | status | High, Medium, Low |
| Timeline | timeline | |
| Status | status | Not Started, Working on it, Stuck, Done (done) |
| Deals (project_deal) | connect → Deals | reflected as Deals.Projects |
| Contact (project_contact) | connect → Contacts | |
| Accounts (project_account) | connect → Accounts | |
| Phone, Email, File | phone, email, files | |
Views: Main table; Gantt (P2 view type; in P1 Table only).

**Sales Dashboard** (connected: Deals) widgets (all periods and buckets by **Expected Close Date**, account timezone): Annual Target (Gauge: sum Deal Value where Stage=Won, period this year, target 100,000), Monthly Target (Gauge, this month, target 10,000), Average deal value (Number avg Deal Value), Active deals value (Number sum Deal Value where group = Active Deals), Deal stage distribution (Chart pie by Stage), Actual revenue by month (Chart column X=Expected Close Date by month, Y=sum Deal Value, filter Stage=Won), Funnel (by Stage, excl. Lost), Leaderboard (Owner, sum Deal Value, Stage=Won).

### L1-automations (seeded, all built from the G-catalog)
| # | Board | Recipe |
|---|---|---|
| 1 | Leads | T3 Status → Qualified ⇒ A4 move to group "Qualified leads" |
| 2 | Leads | T3 Status → Qualified, condition "only if Contacts (lead_contacts) is empty" ⇒ step 1: A6 create Contact {Name←`{item.name}`, Email←`{item.lead_email}`, Phone←`{item.lead_phone}`, Type=Qualified Lead, Last interaction←`{item.last_interaction}`} in Active Contacts, connect to triggering lead via Contacts.Leads ⇒ step 2: A6 create Deal {Name←"`{item.lead_company}` Deal", Stage=New, Owner←`{item.lead_owner}`, Main contact email←`{item.lead_email}`, Last interaction←`{item.last_interaction}`} in Active Deals, connect to `{step[1].item}` via Deals.Contacts |
| 3 | Leads | T1 item created, condition "only if Status is empty" ⇒ A2 Status = New Lead |
| 4 | Leads | T5 button "Move to Contacts" ⇒ A5 move item to Contacts / Active Contacts (map name, email, phone, owner; B6.5 rules) |
| 5 | Leads, Contacts, Deals (3 rows) | T7 timeline activity created (any type), condition "only if Last interaction is empty or before `{trigger.activity.start}`" ⇒ A2 Last interaction ← `{trigger.activity.start}` (date part, account tz) |
| 6 | — | *Replaced by built-in behavior (D-011): the activity is itself the Activities-board item.* |
| 7 | Leads, Contacts, Deals | email received/opened ⇒ notify subscribers — **P2 with L11**, not seeded in P1 |
| 8a | Deals | T3 Stage → any of {New, Discovery, Proposal, Negotiation} ⇒ A4 move to Active Deals |
| 8b | Deals | T3 Stage → Won ⇒ A4 move to Closed Won |
| 8c | Deals | T3 Stage → Lost ⇒ A4 move to Closed Lost |
| 9a | Deals | T1 item created, condition "only if Contacts is empty" ⇒ A10 connect Deals.Contacts where Main contact email = Contacts.Email (first match) |
| 9b | Deals | T2 Main contact email changes, condition "only if Contacts is empty" ⇒ A10 (same as 9a) |
| 10 | Deals | T3 Stage → Won ⇒ A1 notify board subscribers "🎉 `{item.name}` worth `{item.deal_value}` has been won!" |
| 11 | Deals | T3 Stage → Won, condition "only if Projects is empty" ⇒ A6 create Client Project {Name←"`{item.name}` - New project", Owner←`{item.deal_owner}`} in New Projects, connect via Deals.Projects |

Seeded rows in P1: 1, 2, 3, 4, 5×3, 8a, 8b, 8c, 9a, 9b, 10, 11 = **14 automations** (AC-L1-1 counts these 14 as active).
- This requires G2 T3 to accept **multiple labels** ("changes to any of") — added to G2 as P1.

## L2–L4 Lead management & conversion — P1
- L2.1 Leads board per L1-spec; Lead Source defaults "Web form" for form submissions.
- L3.1 Lead capture form per I-area; public link copyable from Leads header ("Share form").
- L4.1 Qualifying a lead (automation 1+2) keeps the lead (moved to Qualified leads) and creates linked Contact + Deal; "Move to Contacts" (automation 4) moves the lead itself. Both must be possible.
- L4.2 Converting twice must not create duplicate contacts: automation 2 condition "only if Contacts (lead_contacts) is empty".
**AC**
- AC-L4-1 Given lead "Jane Doe, Acme, jane@acme.com", Owner Raj, when Status set to Qualified, then within 5 s: lead in Qualified leads; Contact "Jane Doe" (email, Type=Qualified Lead) linked to the lead; Deal "Acme Deal" (Stage New, Owner Raj, main contact email) linked to the contact; activity log shows the automation actor for each.
- AC-L4-2 Given the same lead set Qualified → Contacted → Qualified, then still exactly one Contact and one Deal exist.
- AC-L4-3 Given AC-L4-1, then Deal.Contacts = the new Contact only, the Deal is not linked to the Lead, Deal.Owner = the lead's Owner, and Deal.Accounts (mirror) is empty until the Contact is linked to an Account; Deal.Contacts has exactly 1 item even when an older Contact shares the email.

## L5, L6, L8, L15, L18 Entity boards — P1
- AC-L15-1 Given a product "Onboarding" Price 500, SKU ONB-1, Type Service, then it is created and listed; Price shows "$500".
- AC-L18-1 Given a Client Project linked to deal D, then D's Projects column shows it and the project's Deals column shows D (reflection).
Per L1-spec. Contacts↔Accounts↔Deals↔Projects relations must be navigable both ways from item pages.
- AC-L5-1 Given contact Robert linked to account Amazon and 2 deals, then Robert's item page shows the Amazon and both deal chips, each navigable to its item page.
- AC-L2-1 Given the Leads board of the template, then its columns, labels and groups exactly match L1-spec (schema snapshot test).
- AC-L8-1 Given Deal Value 100,000 and Close Probability 40, then Forecast Value = 40,000.
- AC-L6-1 Given Amazon linked to Robert, and Robert linked to 2 deals, then Amazon's Deals mirror lists both deals.

## L9 Pipeline — P1
Kanban per D5 on Deals with lane sums; also mobile-width friendly horizontal scroll.
- AC-L9-1 Given the template sample data, then the Pipeline view shows 6 lanes New…Lost in label order with counts and Deal Value sums matching the Deals table grouped by Stage.

## L10 Activity timeline (Emails & Activities) — P1 for activities; email per L11 (P2)
**Story:** As Raj, I log a call with notes on a contact and see its full history in one timeline.
**Rules**
- L10.1 Available on CRM entity items (Overview tab). Toolbar: "Log call", "Add activity" (type menu: Meeting, Call summary, Phone call, Note; custom types P2), "New email" (P2), Filters (by type, owner, date range), Search (text in activities).
- L10.2 Activity fields: type, title (optional), body (rich text, ≤ 20,000), start datetime (default now), end datetime/duration (meetings/calls), status Open|Done, owner (default creator), participants (users; P2: contacts), attachments (≤ 10 × 25 MB).
- L10.3 Timeline shows newest first grouped by month with sticky month chip; includes system entries: item created, stage/status changes (for the item's main status column), activity entries, (P2) emails. Each entry: icon by type, author, timestamp, collapsed body with "Show more", menu edit/delete (author or owner), emoji reactions.
- L10.4 Logging an activity creates an Activities-board item (D-011) whose Related item = this item, Owner = creator, Name = "<item name> - <type>"; it emits trigger T7 on the **source item's board** (automation 5) and T1 on the Activities board, plus real-time events on both.
- L10.4a Editing/deleting/restoring an activity from the timeline or from the Activities board is the same operation on the same item. An Activities item created directly on the Activities board with Related item = X appears on X's timeline (T7 fires on X's board too). Changing Related item moves the entry between timelines.
- L10.4b Activity permissions (D-016): timeline actions (log/edit/delete) are authorized against the source item's board per K3 "Can log CRM activities" and K3.4. The Activities board is a system-managed Main board in the CRM workspace whose rows are visible to a user iff they can see at least one Related item; direct edits on the Activities board use its own K3 set (default "Edit everything").
- AC-L10-6 Given Vic can see Contacts but the Activities board's Related item for activity X points only to a Private deal Vic cannot see, then X is not visible to Vic anywhere.
- L10.5 An activity appears on the timeline of every item in its Related item; T7 fires once for each linked item's board when that link is added. P2: read-only roll-up of a contact's activities onto its linked Account timeline.
- L10.6 C38 Activities timeline column: 12-week strip, one tick per week colored by most recent activity type; hover shows last activity summary; "+" opens Add activity.
**AC**
- AC-L10-1 Given Raj logs a 30-minute Meeting now on Robert Thompson, then it appears at the top of Robert's timeline under the current month and other viewers see it within 2 s; the Activities board contains exactly one item "Robert Thompson - Meeting" linked to Robert; within 5 s Robert's Last interaction = today.
- AC-L10-4 Given Mia deletes that item on the Activities board, then it disappears from Robert's timeline within 2 s; restoring it brings it back.
- AC-L10-5 Given an activity is added on the Activities board with Related item = Robert, then it appears on Robert's timeline.
- AC-L10-2 Given filters type = Meeting, then only meetings show.
- AC-L10-3 Given Mia is neither the author nor an owner of the Contacts board nor an Admin, when she edits Raj's activity, then 403; given Mia is a Contacts board owner, then the edit succeeds.

## L11 CRM email via Amazon SES — P2 (D-006)
Summary: connect org sending domain (DKIM/SPF/DMARC verified in SES); compose from item timeline (to = item email column, cc/bcc, template, attachments); outbound from user's name via org domain; Reply-To = per-thread tracking address `t+<token>@reply.<domain>`; inbound via SES receipt rule → parse → append to the item timeline thread, notify subscribers (automation 7); open tracking pixel (opt-in, privacy notice); bounce/complaint handling; per-user daily send limit.

## L12–L13 Email templates, custom activity types — P2
## L14 Activities board — P1 (single store of activities, D-011)
- AC-L14-1 Given 3 activities logged on 3 different leads, then the Activities board shows 3 items each linked to its lead, sortable by Start time.
## L16–L17 Quotes & Invoices with line items and PDF — P2
Line item math (per subitem): base = unit_price × quantity × multipliers; discount_value = base × discount_rate (or fixed); fee_value = (base − discount) × fee_rate; tax_value = (base − discount + fee) × tax_rate; total = base − discount + fee + tax; document Amount = Σ totals; currency per document. PDF from template with org logo; numbering per type (Q-0001 / INV-0001).
## L19 Manage duplicates — P2; L20 Round-robin assignment — P2
## L21 Sequences, L22 Mass email, L23 Shared inbox — P3
## L24 Sales Dashboard — P1 (per L1-spec, H3/H4)
- AC-L24-1 Given the template's sample data, then each of the 8 widgets renders a value that matches a direct computation over the Deals board in the test (golden values recorded in the test fixture).
## L25 Forecasting & Activity analytics views — P2
## L7, L26 — OUT

## Appendix A — Industry list (Accounts.Industry)
Administrative Services, Advertising, Agriculture and Farming, Apps, Artificial Intelligence, Biotechnology, Clothing and Apparel, Commerce and Shopping, Community and Lifestyle, Consumer Electronics, Consumer Goods, Content and Publishing, Data and Analytics, Design, Education, Energy, Events, Financial Services, Food and Beverage, Gaming, Government and Military, Hardware, Health Care, Information Technology, Internet Services, Lending and Investments, Manufacturing, Media and Entertainment, Messaging and Telecommunications, Mobile, Music and Audio, Natural Resources, Navigation and Mapping, Other, Payments, Platforms, Privacy and Security, Professional Services, Real Estate, Sales and Marketing, Science and Engineering, Software, Sports, Sustainability, Transportation, Travel and Tourism, Video.

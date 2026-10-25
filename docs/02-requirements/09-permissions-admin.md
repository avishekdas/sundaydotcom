# 09 — Authentication, Roles, Permissions, Admin (Area K)

## K7 Authentication — P1 (email+password, verification, reset, MFA), P2 (Google SSO), P3 (SAML)
**Rules**
- K7.1 Sign-in by email + password; password ≥ 12 chars, checked against breached-password list; after 5 failures in 15 min for an account from one IP, that IP is blocked for that account for 15 min with exponential backoff; other IPs are unaffected; password reset always remains available.
- K7.2 Invitation-only accounts (no public sign-up) — F1.
- K7.3 Password reset via emailed code/link valid 1 h; all sessions revoked after reset.
- K7.4 MFA: TOTP app; Admin can require MFA for all users (enforced at next sign-in).
- K7.5 Sessions: access token lifetime ≤ 60 min, refresh ≤ 30 days, revocable (sign out everywhere).
- K7.6 First Admin is bootstrapped at deployment (email from config) and must set password + MFA on first sign-in.
**AC**
- AC-K7-1 Given MFA required, when a user without MFA signs in, then they must enroll TOTP before accessing the app.
- AC-K7-2 Given 5 wrong passwords from IP A, then the 6th attempt from IP A within 15 min is refused regardless of correctness, while a correct attempt from IP B succeeds.
- AC-K7-3 Given a password reset, then previously issued refresh tokens no longer work.

## K1 Account roles — P1 (roles), P2 (configurable matrix)
| Capability | Admin | Member | Viewer | Guest (P2) |
|---|---|---|---|---|
| Account settings, users, roles, security, audit | ✔ | — | — | — |
| Create workspaces | ✔ | ✔ | — | — |
| Create boards/dashboards/forms | ✔ | ✔ | — | — |
| Invite users (Member/Viewer) | ✔ | P2 (if enabled) | — | — |
| Edit content on boards they can access | ✔ | per board permission (K3) | — (comment only) | per board permission on Shareable boards |
| Post updates | ✔ | ✔ | ✔ | ✔ (shareable boards) |
| Export | ✔ | ✔ | — (P2 setting) | — |
| Create automations | ✔ (board owner) | board owners | — | — |
| See Open workspaces / Main boards | ✔ | ✔ | ✔ (read) | — |
| Access Private boards | ✔ (all, admin override) | if invited | if invited (read) | — |
- K1.1 Admins can open any board/dashboard for administration (logged in audit, K9).
- K1.2 Viewer can never edit item values or structure, regardless of board setting.
- AC-K1-1 Given a Viewer, when calling create board, create workspace, export, or create automation, then each returns 403 and the corresponding UI entry points are hidden.
- AC-K1-2 Given an Admin not invited to Private board B, then the Admin can open B and the access is written to the audit store.

## K2 Workspace roles — P1
- Owner: manage workspace settings, membership, permissions; create boards in it.
- Member: see workspace and its Main boards; create boards (if account role allows).
- Non-member: for Open workspaces can see and join; for Closed workspaces, nothing visible.
- K2.1 An explicit invite to a board or dashboard grants access to it regardless of workspace membership; the workspace then appears to that user only as a breadcrumb containing just the shared objects.
- AC-K2-1 Given Raj is not a member of Closed workspace W, when invited to Private board B in W, then he can open B and the nav shows W containing only B.
- AC-K2-2 Given Raj is not a member of Closed workspace W, then no board, dashboard or search result from W is visible to him.

## K3 Board permissions — P1
| Permission set (applies to non-owners) | Can edit item values | Can edit structure (columns, groups, views, settings) | Can create/delete items | Can post updates | Can log CRM activities |
|---|---|---|---|---|---|
| Edit everything (default) | ✔ | ✔ | ✔ | ✔ | ✔ |
| Only edit content | ✔ | — | ✔ | ✔ | ✔ |
| Only edit assigned items (choose People column) | only items where the column contains the user (or their team, P2) | — | create ✔ (auto-assigned to self), delete own assigned only | ✔ | on assigned items only |
| View and comment | — | — | — | ✔ | ✔ (log own; cannot edit item values) |
- K3.5 (D-020) Row-level visibility (Activities board, D-016) is enforced on every read path: search, views, counts and footers, widgets, export, API pagination and real-time events.
- AC-K3-5 Given activity X visible only via a Private deal Vic cannot see, then X is absent from Vic's search results, Activities board export, Activities group count, and any dashboard widget count.
- K3.4 CRM activity edit/delete: the activity's author, or an owner of any Related item's board, or an Admin (D-016). Viewer account role: may post updates only, not log activities.
- K3.1 Owners always have full rights; Admins have owner rights (K1.1).
- K3.2 Effective permission = min(account role ceiling, workspace access (except as granted by K2.1), board access (kind/invite), board permission set). Evaluated server-side on every request; UI reflects it.
- K3.3 Automations act as their owner (G1.5); forms bypass board permission for creation only.
**AC**
- AC-K3-1 Given board set to "Only edit assigned items" on Owner column, when Raj edits a deal owned by Mia, then 403 and UI cell is read-only; when he edits his own, success.
- AC-K3-2 Given "Only edit content", when Raj tries to add a column, then 403 and the "+" column control is hidden.
- AC-K3-3 Given a Viewer on an "Edit everything" board, when she edits a cell, then 403 (K1.2).
- AC-K3-4 Given any API endpoint, then a permission test exists that asserts denial for each role/set lacking the right (test matrix generated from this table).

## K6 Dashboard permissions — P1
Main dashboards visible per workspace access; Private only to invited; owners edit, others view; data per H7.
- AC-K6-1 Given Main dashboard D in an Open workspace, then any Member can view it but only its owners can edit widgets (others: 403).

## K4 Column permissions — P2; K5 View permissions — P2; K8 Sessions & login history — P2; K9 Audit log — P2
- K9 audit: admin actions, permission changes, exports, sign-ins, API token use; retained 1 year; filter & CSV export.

## K10 API tokens — P2
Personal access tokens (scoped to the user's permissions, expiry ≤ 1 year, revocable); service users (P3).

## K11 Billing — OUT

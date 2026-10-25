# 05 — Item Page, Updates, Users & Real-time (Areas E, F)

## E1 Item page — P1
**Rules**
- E1.1 Opens as a right-side/large modal over the board from any view; full-page at URL `/boards/{b}/items/{i}`; Esc/close returns to the board preserving scroll.
- E1.2 Header: item name (inline rename), board/group breadcrumb, subscribers avatars + subscribe toggle, prev/next arrows (order of the current view), menu (duplicate, move, archive, delete, copy link).
- E1.3 Tabs P1: **Updates**, **Activity log**, and for CRM entity boards **Overview** (timeline L10 + field panel). Tab set is fixed per board type in P1 (configurable E6 is P2).
- E1.4 Field panel (E2) is visible on Overview (CRM) or as an "Info" side panel on non-CRM boards.
- E1.5 Subitems section on the item page (list with add/edit).
**AC**
- AC-E1-1 Given a deep link to an item the user can see, then the board loads with the item page open.
- AC-E1-2 Given the item is archived, then the page shows an "Archived" banner with Restore (if permitted) and fields are read-only.
- AC-E1-3 Given prev/next in a filtered view, then navigation follows only the filtered items in view order.

## E2 Field panel — P1
All non-hidden columns as label + editor (same editors/validation as table); column order follows the board's Main table; read-only computed fields marked.
- AC-E2-1 Given Raj changes Stage in the field panel, then the table row updates in place and the change appears in the item's activity log.

## E3 Updates — P1
**Story:** As Raj, I post an update on a deal, @mention Mia, attach a PDF; Mia replies.
**Rules**
- E3.1 Rich text: bold, italic, underline, strike, links, bullet/numbered lists, checklists, code inline, quote; paste images (stored as files); max 50,000 chars.
- E3.2 @mentions of users and teams (P2 for teams) and of the board ("@board" notifies subscribers, owners only).
- E3.3 Replies (one level), likes (toggle, list of likers), pin to top (one pinned per item), edit (author only, shows "edited"), delete (author or board owner; soft delete with "This update was deleted").
- E3.4 Attachments: files ≤ 100 MB each via C21 storage rules.
- E3.5 Posting an update subscribes the author to the item.
- E3.6 Row "updates" bubble shows count; unread indicator for subscribers.
- E3.7 Viewer role can post updates and replies (K3 "View and comment"), cannot edit fields.
**AC**
- AC-E3-1 Given Raj posts "@Mia please review", then Mia gets an in-app notification within 2 s linking to that update, and Mia is auto-subscribed to the item (F4).
- AC-E3-2 Given Mia edits Raj's update, then the action is rejected.
- AC-E3-3 Given an update with an attached PDF, when a user without access to the board requests the file URL, then 403/404.
- AC-E3-4 Given two users have the item page open, when one posts an update, then it appears for the other within 2 s.

## E4 Item activity log — P1
Per A15, filtered to the item, including subitem changes and update posts (not content).
- AC-E4-1 Given 3 value changes and 1 subitem creation on an item, then its Activity log tab lists 4 entries newest first with actor and before→after.

## E5–E8
- E5 Item description doc — P2. E6 Configurable item tabs — P2. E7 Item file gallery — P3. E8 AI on item — OUT.

## F1 Invite & lifecycle of users — P1
**Rules**
- F1.1 Admin (and Members if account permission allows, K1 P2) invites by email with role; invitation email with one-time link valid 7 days; resend/revoke.
- F1.2 Accepting sets password (K7) and profile.
- F1.3 Deactivate user: cannot sign in, sessions and API access revoked within 60 s (F7.7), data and attributions kept, removed from pickers; reactivate restores.
- F1.4 Change role (Admin only); last Admin cannot be demoted/deactivated.
- F1.5 Deactivating a user who owns automations, boards (as sole owner) or dashboards (as sole owner) requires the Admin to reassign them in a blocking dialog that lists each one; default target = the Admin.
- AC-F1-3 Given Mia owns 4 automations and is sole owner of the Deals board, when Ada deactivates her, then Ada must pick a new owner; afterwards the 4 automations run as the new owner and none fail.
**AC**
- AC-F1-1 Given an invite older than 7 days, when used, then "invitation expired" and Admin can resend.
- AC-F1-2 Given a user deactivated, then any API call after 60 s fails with 401 and their name still appears on past updates.

## F2 User types — P1
Admin, Member, Viewer, Guest (Guest only usable with Shareable boards → effectively P2). Capabilities defined in 09-permissions-admin.md.

## F3 Teams — P2; Departments — P3
Teams: name, members, owners; assignable in People columns and as board/workspace members; @team mentions.

## F4 Subscriptions — P1
Board subscribe = board member + notifications per A9; item subscribe via item page toggle; auto-subscribe on: create item, assigned, post/reply update, mentioned.
- AC-F4-1 Given Raj creates an item, then he is subscribed to it; when he toggles unsubscribe, then he gets no notification for the next update on it.

## F5 Mentions → notifications — P1
Covered by E3.2 + A9.

## F6 Email digest — P2
Daily digest option replacing per-event emails.

## F7 Real-time collaboration & presence — P1 (D-008)
**Story:** As Mia, while Raj works the board, I see his changes appear without reloading and see that he is on the board.
**Rules**
- F7.1 Push channels per board (structure + items + views), per item (updates, timeline), per user (notifications).
- F7.2 Events: item created/updated/moved/archived/deleted, column value changed, **computed value changed** (mirror, formula, C38 activities column, Last updated), group/column/view structure changed, update posted/edited/deleted, timeline entry added, automation-made changes (same events), notification created, permission changed (forces client re-authorization).
- F7.2a (D-018) Computed-value events include the value only for subscribers who can see every contributing board; other subscribers receive an invalidation and re-fetch their per-viewer value.
- AC-F7-6 Given Vic cannot see the 55,000 deal linked to Robert, when that deal's value changes, then no message delivered to Vic's connection contains Robert's full Deals value; Vic's cell refreshes to his own visible value within 3 s.
- F7.3 Delivery ≤ 2 s p95 from commit; ordered per item; client reconciles optimistic edits by server version number; on reconnect after drop, client re-syncs by fetching changes since last version (or full reload of view if gap > 5 min).
- F7.4 Clients only receive events for boards/items they are allowed to see (authorization at subscribe time and re-checked on permission change: removal from board ends the subscription within 60 s).
- F7.5 Presence: avatars of users currently viewing the board (heartbeat 30 s, timeout 60 s); on item page, show who else has it open (P2: who is editing which cell).
- F7.6 Scale: 500 concurrent connected users, 100 concurrent on a single board.
- F7.7 Role and permission changes (account role, workspace membership, board invite, board permission set) take effect on the API ≤ 60 s and on real-time subscriptions ≤ 60 s; authorization never relies on role/permission claims cached longer than 60 s (tokens carry identity only).
- AC-F7-5 Given Raj (Member) is editing, when Ada changes him to Viewer, then within 60 s his next edit is rejected (403) and his UI switches to read-only.
**AC**
- AC-F7-1 Given Raj and Mia on Deals, when Raj changes a Stage, then Mia's view updates within 2 s without reload.
- AC-F7-2 Given Mia is removed from a Private board while viewing it, then within 60 s she stops receiving events and sees "You no longer have access".
- AC-F7-3 Given Mia's network drops for 2 min while Raj makes 10 edits, when she reconnects, then her view shows all 10 edits without manual reload.
- AC-F7-4 Given Raj opens the board, then Mia sees Raj's avatar in the board header presence list within 5 s, and it disappears ≤ 60 s after he leaves.

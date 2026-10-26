# Cognito: user restore and account problems (plan §5, M1)

**Pool** `tasklane-<stage>` (RETAIN), app client `tasklane-<stage>-proxy`. The app's user row is `tl.users`
(linked by `cognito_sub`); Cognito holds only credentials. MFA is off until M9 (D-045).

## A user cannot sign in
1. Admin → Users page: status `deactivated`? Reactivate (re-enables the Cognito user).
2. Status `invited` and the invite expired (7 days, AC-F1-1)? Admin → Resend.
3. Locked out after failures: the proxy's counters close sign-in for 15 min (D-044, Sev2 `AccountClosed`, see
   [auth](auth.md)); a password reset always works and reopens it.
4. Cognito user missing but `tl.users` row present (pool rebuilt or user deleted by hand): re-invite with the same
   email from the Users page after deleting the stale row's `cognito_sub` link — or run, as admin:
   `aws cognito-idp admin-create-user --user-pool-id <pool> --username <email> --user-attributes Name=email,Value=<email> Name=email_verified,Value=true`
   then `update tl.users set cognito_sub = '<new sub>' where email = '<email>'`. Passwords cannot be restored;
   the user sets a new one from the invite.

## Pool rebuilt (disaster)
Users are re-created from `tl.users` (email, name) with invites; nothing else in the app depends on the old subs
once each row's `cognito_sub` is updated. Scripted test users come back on the next deploy (D-049) and the
bootstrap admin is re-invited (D-055).

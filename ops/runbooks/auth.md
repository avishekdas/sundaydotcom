# Auth proxy (`/api/auth/*`, arch 07 §7.1)

## Sev2: account sign-in closed (`AccountClosed`, D-044)
An account reached 10 failed sign-ins in 15 minutes from any IPs. Until CAPTCHA exists (M6) the proxy refuses every
sign-in for that account until the window ends; password reset stays available.
1. CloudWatch Logs `/aws/lambda/tasklane-<stage>-api`, filter `{ $.metric = "auth.account_closed" }` for the time.
   The log line carries no email (PII); correlate with the user's report or the counters table
   `tasklane-<stage>-counters` (keys `signin#<email>` / `signin#<email>#<ip>`; `expires_at` = window end).
2. Many accounts at once → a distributed guessing attack. Consider enabling WAF on the distribution early (D-041).
3. One account, real user locked out → ask them to wait for the window or reset the password. To reopen early,
   delete the `signin#<email>` (and `signin#<email>#*`) items from the counters table.

## Sign-in returns 403 for everyone
The origin secret (`/tasklane/<stage>/origin-secret`, D-050) differs between CloudFront and the api λ, or
`CloudFront-Viewer-Address` is not forwarded. Both read the SSM parameter at deploy time: re-run `deploy-dev`. Never
overwrite the parameter by hand without redeploying the Api and Edge stacks.

## Cognito errors
`AdminInitiateAuth` throttling or `ResourceNotFound` → check the user pool and the `tasklane-<stage>-proxy` client.

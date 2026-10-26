# Spike S-2b — Cognito lockout vs the auth proxy (M1 story 1, AC-K7-2, D-022)

**Date:** 2026-10-25 · **Setup:** throwaway pool `tasklane-spike-s2b` from `infra/template.json` (same password policy and
MFA setting as `tasklane-dev`, Essentials tier, no threat protection), client with `ALLOW_ADMIN_USER_PASSWORD_AUTH`;
`AdminInitiateAuth` called from one source (AWS MCP sandbox, account 920824005451, us-east-1). Viewer IPs are modelled by
the proxy (`harness.py`); Cognito sees only the caller. Stack deleted after the run.

## What was measured (8 runs, ~60 test users)
| # | Question | Result |
|---|---|---|
| 1 | Message sequence | failures 1–5: `Incorrect username or password`; during a lock **every** attempt, correct password included: `Password attempts exceeded` |
| 2 | Lock schedule (paced single user, no attempt during a lock; runs 6–8) | lock after the n-th evaluated failure = **2^(n−5) s**: 1, 2, 4, 8, 16, 32 s for n = 5…10. Gaps of 1.5/2.5/4.5/8.5/16.5/32.5 s after failures 5…10 were all evaluated; a correct sign-in 32.5 s after the 10th failure succeeded |
| 3 | Do attempts during a lock count? | No — rapid bursts show `BBBBB L B L B L`: locked attempts are not evaluated and did not lengthen the lock in single-user runs |
| 4 | Does success reset the counter? | Yes — 5 failures, success, then 2 more failures are both evaluated (`BAD BAD`) |
| 5 | Is there a per-caller (IP) or pool-wide lock? | **No** — 40 failures sprayed over 10 accounts from one caller in 11 s; fresh accounts then signed in (and failed) normally. Important because in production every call comes from the auth λ, not the viewer |
| 6 | **AC-K7-2 through the proxy model** | 5 wrong from IP A → 401 ×5; 6th from A → **429 without calling Cognito**; correct from A → 429; **correct from IP B → 200 in 2.7 s** (first call hits Cognito's 1 s lock, proxy waits it out and retries once) → **PASS** (≤ 35 s) |
| 7 | Worst cases through the proxy | 10 evaluated failures (A1 ×5, A2 ×5): the account hits the per-account cap → `captcha_required`; Cognito's own lock is then 32 s |
| 8 | Anomaly | In the most concurrent run (11 users attacked in parallel, ~2 s call latency) two accounts stayed locked longer than the schedule (a wrong attempt 9 s after the 7th failure was refused; probes up to 40 s refused). **Not reproduced** in an identical re-run (run 8, all 8 cases on schedule). Treated as: the schedule is the norm but not a guarantee |

## Verdict: **PASS for AC-K7-2, with two design changes needed for the worst case**
- The interplay works as 07 §7.1 intends: the per (email, IP) counter keeps one IP from driving Cognito past n = 5, so
  IP B pays at most Cognito's 1 s lock. Cognito counts per user only, so a shared Lambda egress IP is not a problem.
- **Finding 1 — the 35 s worst case cannot be waited out inside one request.** HTTP API integrations time out at
  30 s (the api λ is set to 29 s). With up to 10 evaluated failures before the per-account cap, Cognito's lock reaches
  32 s. The proxy can wait in-request only up to n = 8 (8 s); beyond that the retry must be driven by the SPA.
- **Finding 2 — a single computed retry is not robust.** Run 8's anomaly and run 6's margin show that waiting exactly
  2^(n−5) s and retrying once can miss. Retries need a margin and a second attempt.
- **Finding 3 — the per-account CAPTCHA step has nothing to verify against until WAF exists (M6, D-041).** In M1 the
  "≥ 10 failures → CAPTCHA" branch needs an interim behaviour.

## Proposed revision of D-022 / 07 §7.1 (user decision)
1. **Retry contract.** On a Cognito lock the proxy waits in-request only while the expected lock (from its own
   per-account counter) plus a 0.5 s margin fits in 20 s, retrying at most twice. Otherwise it returns the generic 401
   with `retry_after_s` computed **from the proxy's own counters** (same for unknown emails, so no enumeration oracle);
   the SPA shows "Signing you in…" and retries once automatically with the password still in memory. Bound stays
   **≤ 35 s** (n = 10: 32 s + one call).
2. **Per-account cap before WAF (M1–M5).** Options: (a) at ≥ 10 failures/15 min the account is closed to *all* IPs
   for the rest of the window except via password reset (K7.1 keeps reset available) plus a Sev2 alert; or (b) no
   per-account cap until M6 — Cognito's lock then grows to ~15 min under a distributed attack, also hitting the real
   user. CAPTCHA replaces the interim behaviour in M6.

## Not covered (by design)
- Real viewer IPs through CloudFront (`CloudFront-Viewer-Address` parsing is a unit-tested story in M1, SEC-6).
- MFA and refresh flows (later M1 stories, Tier B against the dev pool).

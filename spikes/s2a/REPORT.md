# Spike S-2a — WAF challenge for public forms (PE-2, SEC-7)

**Date:** 2026-10-25 · **Stack:** CloudFront → Lambda function URL (OAC, AWS_IAM) stub `stub.py`; WAF web ACL (CLOUDFRONT scope) with Bot Control **Common** (Count, scope-down to `/forms/*`, `/f2/*`), rule `TokenAccepted` (label `awswaf:managed:token:accepted` → Count + insert header `tl-chal: <secret>`), a Challenge-action rule on `*/chal.html` to obtain a token. Tested from a real Chrome session.
Two variants side by side:
- **A `/forms/*`** — design as written in arch 07 §7.4: CloudFront Function (viewer-request) strips viewer `x-amzn-waf-*` and `x-tl-*`.
- **B `/f2/*`** — no function; WAF rule (priority 0) **blocks** any request whose header keys start with `x-amzn-waf-` (AWS-recommended pattern).

| Test | A (CF Function strip) | B (WAF block rule) |
|---|---|---|
| No token, attempts 1–5 / 6–7 | pass / `challenge_required` ✔ | — |
| Forged `x-amzn-waf-tl-chal` without token | stripped, request passes as unchallenged ✔ | 403 from WAF ✔ |
| **With a valid token, attempts 1–11** | 5 × pass, **5 × `challenge_required`** ✘, 429 | **5 × pass, 5 × `pass_challenged`, 429** ✔ |
| Forged header with a valid token | — | 403 from WAF ✔ |
| Header seen by origin with token | **none** — the function removed WAF's own header | `x-amzn-waf-tl-chal` = secret ✔ |

## Verdict: **PASS with a design change**
- **Finding:** CloudFront runs WAF *before* the viewer-request CloudFront Function, so the function deletes the header WAF just inserted. The "CloudFront Function strips `x-amzn-waf-*`" design in arch 07 §7.4 cannot work.
- **Change (D-029):** forgery is stopped by a **WAF rule at priority 0 that blocks requests carrying any header key starting `x-amzn-waf-`** (AWS-documented practice; WAF also overwrites a same-named header on insert). A CloudFront Function may still strip `x-tl-*` but must never touch `x-amzn-waf-*`.
- Bot Control **Common** level is enough for token labels (no Targeted level needed) → cost ≈ $10/mo + $1/M requests on `/forms/*` only.
- The ramp pass → challenge → 429 works end to end with the app-side ladder.

## Residual for M6 (I7 public forms)
- The token was obtained through a Challenge-action page navigation. The SPA path (WAF JavaScript integration SDK `getToken()`) is still to be proven; `GetWebACL` via the API tools here did not return `ApplicationIntegrationURL`, so the CDK Edge stack must read it (custom resource or console value in SSM). Fallback: full-page navigation to a Challenge-protected `/forms/<id>/verify` that redirects back, or the CAPTCHA action.
- The stub counted per key without a time window; the real minute/day windows live in DynamoDB (AC-I7-*).

Resources were deleted after the run (stack `tasklane-spike-s2a`).

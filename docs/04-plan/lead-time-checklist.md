# External lead-time checklist (DL-8)

Checked against account 920824005451 (us-east-1) on 2026-10-25. Items marked **user** need your action or approval because they change the account, cost money or take an external review.

| # | Item | Needed by | Current state (observed) | Action | Owner | Status |
|---|---|---|---|---|---|---|
| 1 | Domain + hosted zone | M0b (Edge stack) | Route 53 zone `avishekdas.dev` exists; no registered domains in this account | Pick sub-domains, e.g. `app.tasklane.avishekdas.dev` (prod), `staging.…`, `dev.…`; delegate a `tasklane` sub-zone per account | decided D-033 | ready |
| 2 | ACM certificates (us-east-1 for CloudFront) | M0b | none | DNS-validated certs per stage; created by the Edge stack | CDK | blocked on 1 |
| 3 | SES production access | M7 (CRM email, P2 send) — request in week 1 because review takes days | sandbox: 200/day, 1 msg/s | Verify sending domain (DKIM, MAIL FROM), then submit production-access request with use-case text | **user** submits (AWS asks for account-owner details) | open |
| 4 | AWS accounts dev / staging / prod | M0b story 8 | single account, **no AWS Organization** | Create an Organization from this account (management), add 3 member accounts; enable IAM Identity Center; stop using the root user for daily work | deferred (D-031: dev only) | deferred |
| 5 | GitHub repo + OIDC deploy roles | M0b (CI, CDK deploys — zip uploads are not possible from this workspace) | no repo yet | Create private repo `tasklane`; OIDC provider + role per account trusting `environment:<stage>` | repo decided (D-032); GitHub access for Claude to push still needed | open |
| 6 | Lambda concurrency quota | M2 load gate / prod | **10** concurrent executions (new-account default) | Service Quotas request ≥ 1,000 in each stage account (dev can stay lower) | requested (D-034) | pending AWS |
| 7 | WAF Bot Control | M6 (public forms) | used in S-2a spike (Common level) | Subscription is per web ACL, billed monthly (~$10 + $1/M requests); keep scope-down to `/forms/*` | CDK | ready |
| 8 | CDK bootstrap per account/region | M0b | not bootstrapped | `cdk bootstrap` with OIDC trust (after 4, 5) | CDK | blocked on 4, 5 |
| 9 | Security baseline (GuardDuty, Security Hub, Config, org CloudTrail) | M0b story 8 | not enabled | Enabled from the Organization management account | CDK/user | blocked on 4 |

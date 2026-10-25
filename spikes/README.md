# Milestone 0a spikes

| Spike | Status | Report |
|---|---|---|
| S-1 Data API & JSONB performance | **PASS** (no fallback needed) | `s1/REPORT.md` |
| S-2a WAF challenge | **PASS** (design change D-029) | `s2a/REPORT.md` |
| S-3 cold start & sizing | **PASS** (no SnapStart/PC needed now) | `s3/REPORT.md` |
| S-4 recompute & per-viewer | **PASS** | `s4/REPORT.md` |

## Spike AWS resources (account 920824005451, us-east-1, tag `purpose=tasklane-spike-m0a`) — **deleted 2026-10-25**
- Aurora cluster `tasklane-spike` + instance `tasklane-spike-writer` (skip final snapshot; managed secret removed with the cluster)
- Stacks `tasklane-spike-s1` (loader λ) and `tasklane-spike-s2a` (CloudFront, WAF, Lambda, OAC, CF Function)
- IAM roles `tasklane-spike-s1`, `tasklane-spike-s2a`; S3 bucket `tasklane-spike-920824005451-use1`

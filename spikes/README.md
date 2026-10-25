# Milestone 0a spikes

| Spike | Status | Report |
|---|---|---|
| S-1 Data API & JSONB performance | running | `s1/REPORT.md` |
| S-2a WAF challenge | pending | |
| S-3 cold start & sizing | pending | |
| S-4 recompute & per-viewer | pending | |

## Spike AWS resources (account avishekd 920824005451, us-east-1) — all tagged `purpose=tasklane-spike-m0a`, delete after M0a
- Aurora Serverless v2 cluster `tasklane-spike` (PG 18.6, Data API, 0.5–4 ACU) + instance `tasklane-spike-writer`
- Lambda `tasklane-spike-s1` (CloudFormation stack `tasklane-spike-s1`; inline loader that fetches `s1/bench.py` from S3)
- IAM role `tasklane-spike-s1`, S3 bucket `tasklane-spike-920824005451-use1`

# Spike S-3 — Lambda cold start & sizing

**Date:** 2026-10-25 · **Function:** python3.13, arm64, 1,024 MB, public layer `AWSLambdaPowertoolsPythonV3-python313-arm64:40` (Powertools v3 + Pydantic v2), boto3 `rds-data` client created at init.
**Init code:** imports boto3, Powertools Logger, `APIGatewayHttpResolver(enable_validation=True)`, a Pydantic model; handler runs one Data API `select 1`.
**Method:** 10 forced cold starts (configuration change before each invoke), then 10 warm invokes; durations from Lambda `REPORT` logs.

| Measure | Values (ms) | p50 | max |
|---|---|---|---|
| Lambda `Init Duration` (cold) | 597, 610, 643, 669, 767, 803, 815, 822, 926, 974 | 785 | 974 |
| Imports inside init (measured in code) | 536 – 889 | 704 | 889 |
| First Data API call on a cold container | 98 – 178 | 149 | 178 |
| **Cold request, server side** (init + handler) | ≈ 700 – 1,150 | ≈ 930 | ≈ 1,150 |
| Warm handler (incl. one Data API call) | 12 – 15 (one outlier 136) | 13 | 136 |

## Verdict: **PASS** (threshold: cold p95 ≤ 1.5 s, warm ≤ 300 ms)
- **Decision (ADR-012):** no SnapStart and no provisioned concurrency for now. Cold starts add ≈ 1 s to the first request of a new container; with steady traffic most requests are warm.
- Init time is dominated by imports (Powertools event handler + Pydantic). Mitigations, if needed later: lazy-import rarely used routers; keep the `api` package slim (bundle only used Powertools modules); then SnapStart.
- Re-measure with the real `api` package at M3 and M8 exits (PE-14).
- Warm Data API call from inside Lambda ≈ 12–15 ms (S-1 saw 20–55 ms per call under its benchmark loop) — the 2-calls-per-hot-path budget leaves wide margin.

# M0b — canary rollback rehearsal on dev (2026-10-25)
Procedure: `ops/rehearse_canary_rollback.md`.
| Step | Result |
|---|---|
| Bad version | `tasklane-dev-api` v2 published with `TL_FAULT_INJECTION=1` (every call raises) |
| Deployment | CodeDeploy `d-1T2KSVIGM`, `live` v1 → v2, `LambdaCanary10Percent5Minutes` |
| Traffic | 70 invocations of `live` in 60 s → 4 errors (canary share ≈ 6 %) |
| Outcome | alarm `LiveErrors` fired → deployment **Stopped (ALARM_ACTIVE)** → automatic rollback `d-11CWANIGM` → `live` = v1 |
| After | fault flag removed; 20/20 calls to `live` succeed |

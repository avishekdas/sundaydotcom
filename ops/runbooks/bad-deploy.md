# Bad deploy — canary, pre-traffic check and rollback (M0B-6, M0B-16)

**How a deploy is protected.** Every push to `main` runs ci → deploy-dev → e2e-dev. The `api` λ is published as a
new version and the `live` alias moves through CodeDeploy `Canary10Percent5Minutes`:
1. **Pre-traffic hook** `tasklane-<stage>-predeploy-hook` invokes the *new* version's `/api/v1/health` directly
   (DB round trip, origin secret). A failure stops the deployment before any traffic shifts; `live` stays on the
   old version and the CloudFormation update of `tasklane-<stage>-api` fails (the deploy-dev run goes red).
2. **Canary window**: 10 % of `live` traffic for 5 min; alarm `LiveErrors` (any error on `live`) stops the
   deployment and CodeDeploy rolls `live` back automatically. On dev the window usually sees little traffic.

**When `LiveErrors` fires or deploy-dev fails at the api stack**
1. CodeDeploy console → application of `tasklane-<stage>-api` → the latest deployment: *Stopped* means the hook
   or the alarm stopped it and `live` is already back on the previous version. Confirm with
   `aws lambda get-alias --function-name tasklane-<stage>-api --name live`.
2. Hook failures: logs of `/aws/lambda/tasklane-<stage>-predeploy-hook` (`predeploy.result`, `predeploy.error`),
   then the new version's logs in `/aws/lambda/tasklane-<stage>-api`.
3. Manual rollback (if a bad version did reach 100 %): point `live` at the previous version
   (`aws lambda update-alias --function-name tasklane-<stage>-api --name live --function-version <n>`), or
   re-run the last green deploy-dev workflow from GitHub Actions ("Re-run all jobs" on that run).
4. Fix forward with a red test for the failure, then the fix (plan §1.2).
Rehearsal: `ops/rehearse_canary_rollback.md` (system test `docs/04-plan/system-tests/M0b-canary-rollback.md`).

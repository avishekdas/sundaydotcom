# Canary rollback rehearsal (M0b system test, PE-6)
Proves that a bad `api` deploy is rolled back automatically by CodeDeploy.
1. Set `TL_FAULT_INJECTION=1` on `tasklane-dev-api` (`$LATEST`) and publish a new version — every invocation of it raises.
2. Start a CodeDeploy deployment of the `live` alias from the current version to the new one
   (application/deployment group of the `tasklane-dev-api` stack, config `LambdaCanary10Percent5Minutes`).
3. Invoke the `live` alias repeatedly for ~2 minutes (about 10 % of calls hit the bad version).
4. Expect: alarm `LiveErrors` → ALARM, deployment status `Stopped`/`Failed` with rollback, `live` points at the old
   version again, and calls succeed. Then remove `TL_FAULT_INJECTION` (the next pipeline deploy resets it anyway).
Never available in prod: the handler ignores the flag when `STAGE=prod`.

# api λ errors
1. CloudWatch Logs `/aws/lambda/tasklane-<stage>-api`: find the exception and `request_id` (also returned to the client in error bodies).
2. Data API errors (`DatabaseResumingException` beyond retries, throttling) → check the Aurora cluster status and ACU.
3. A bad deploy → see [bad-deploy](bad-deploy.md) (pre-traffic hook, canary, automatic and manual rollback).

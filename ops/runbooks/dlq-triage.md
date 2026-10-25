# DLQ triage
**Alarm:** messages visible in a `*-dlq` queue.
1. Open the queue in the SQS console → *Send and receive messages* → poll; read the body and the `ErrorMessage`/attributes.
2. Find the failing function's logs (CloudWatch → `/aws/lambda/tasklane-<stage>-<fn>`) around the message's `SentTimestamp`.
3. Fix the cause (code deploy, data fix). Never edit messages by hand.
4. Redrive: SQS console → *Start DLQ redrive* back to the source queue (or `ops/redrive.py` once added). For schedule/rule DLQs the source is the target function: invoke it once manually instead.
5. Confirm the DLQ is empty and the alarm returns to OK.

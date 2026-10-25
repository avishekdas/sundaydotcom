# outbox-acker errors
The acker marks `tl.outbox.published_at` for events delivered to the `outbox-ack` queue.
- Errors usually mean the Data API is unavailable (cluster resuming, throttled) — SQS retries automatically; malformed records go to the DLQ (see dlq-triage).
- If errors persist > 15 min, the sweeper circuit will open (see outbox-circuit). Check the `tl_worker` secret and the function's IAM policy.

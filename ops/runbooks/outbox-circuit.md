# Outbox backlog / retries / circuit open
- **Backlog > 1,000** or **rows retried > 3 times**: EventBridge `PutEvents` is failing or the acker is not acking. Check sweeper logs (`outbox.sweep` lines: `failed`, `republished`).
- **Circuit open**: nothing was acked for 5 min while the API kept publishing → the acker path (rule → queue → acker) is broken. The sweeper now republishes one probe row per run (every minute; hourly 08:00–19:00 New York on dev, D-037); it closes itself once an ack arrives.
  1. Check the `tasklane-<stage>-outbox-ack` rule target and the queue's DLQ.
  2. Check acker errors. Fix, then watch `Circuit` return to 0.
- Consumers are idempotent (event_id), so duplicate deliveries are safe; floods are what the circuit prevents.
- **Dev (D-037):** the sweeper runs hourly 08:00–19:00 New York time, so an event whose first publish failed may be republished up to an hour later (overnight: at 08:00). Normal pushes do not depend on the sweeper.

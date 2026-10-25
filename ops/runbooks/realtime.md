# Realtime (WebSocket handlers / fan-out) errors
- `ws-handlers` errors: check the registry table `tasklane-<stage>-realtime` permissions and throttling; clients reconnect with backoff and gap-sync via `/boards/{id}/changes`, so no data is lost.
- `fanout` errors or messages in `tasklane-<stage>-fanout-dlq`: check `WS_MANAGEMENT_URL` and `execute-api:ManageConnections`. Missed pushes are recovered by clients' gap sync; redrive is optional.

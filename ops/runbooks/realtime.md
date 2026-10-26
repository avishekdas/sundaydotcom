# Realtime (WebSocket handlers / fan-out) errors
- `ws-handlers` errors: check the registry table `tasklane-<stage>-realtime` permissions and throttling; clients reconnect with backoff and gap-sync via `/boards/{id}/changes`, so no data is lost.
- `fanout` errors or messages in `tasklane-<stage>-fanout-dlq`: check `WS_MANAGEMENT_URL` and `execute-api:ManageConnections`. Missed pushes are recovered by clients' gap sync: on reconnect and every 60 s while connected (M0B-4), so a connected client may lag up to a minute; redrive is optional.

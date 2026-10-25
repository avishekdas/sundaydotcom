-- 0004 — narrow the worker roles (M0A-4, SEC-11). Runs as tl_migrator (owner of all tl objects).
-- tl_worker becomes the scheduler-tick role: partition functions only, no table access.
revoke all on all tables in schema tl from tl_worker;
revoke all on all sequences in schema tl from tl_worker;
alter default privileges for role tl_migrator in schema tl revoke all on tables from tl_worker;
alter default privileges for role tl_migrator in schema tl revoke all on sequences from tl_worker;

-- tl_worker_outbox: acker (published_at) and sweeper (attempt bookkeeping + its lease).
grant select (event_id, type, schema_version, board_id, item_id, payload, created_at, id,
              published_at, publish_attempts, last_published_at) on tl.outbox to tl_worker_outbox;
grant update (published_at, publish_attempts, last_published_at) on tl.outbox to tl_worker_outbox;
grant select, insert, update on tl.leases to tl_worker_outbox;

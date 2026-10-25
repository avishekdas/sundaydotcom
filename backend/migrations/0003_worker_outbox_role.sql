-- run-as: admin
-- 0003 — table-scoped worker roles (M0A-4): a role for the outbox acker + sweeper.
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'tl_worker_outbox') then
    create role tl_worker_outbox nologin;
  end if;
end $$;
grant usage on schema tl to tl_worker_outbox;

-- 0007 — least privilege for tl_api_rw (M0B-8, 07 §7.3). Runs as tl_migrator (owner of all tl objects).
-- New tables no longer grant tl_api_rw anything by default; each table below is granted explicitly and the grant
-- table in tests/integration/migrations/test_0007_api_grants.py must change with it.
alter default privileges for role tl_migrator in schema tl revoke select, insert, update, delete on tables from tl_api_rw;
revoke all on all tables in schema tl from tl_api_rw;

grant select on tl.account to tl_api_rw;
grant update (name, timezone, date_format, week_start, allowed_domains, logo_file_id, require_mfa) on tl.account to tl_api_rw;
grant select, insert on tl.activity_log, tl.board_changes, tl.jobs to tl_api_rw;
grant select, insert on tl.outbox to tl_api_rw;  -- SELECT: the mutation's INSERT … RETURNING payload needs it
grant select, insert, update on tl.boards, tl.columns, tl.groups, tl.items, tl.recompute_pending, tl.workspaces to tl_api_rw;
grant select, insert, delete on tl.item_links to tl_api_rw;
grant select, insert, update, delete on tl.board_members, tl.idempotency_keys, tl.item_text, tl.users,
  tl.view_item_positions, tl.views, tl.workspace_members to tl_api_rw;

-- perm_epoch (and db_generation) are not writable by the api role: permission changes bump the epoch here only.
create function tl.bump_perm_epoch() returns bigint
  language sql security definer set search_path = pg_catalog, tl
  as $$ update tl.account set perm_epoch = perm_epoch + 1 where id = 1 returning perm_epoch $$;
revoke execute on function tl.bump_perm_epoch() from public;
grant execute on function tl.bump_perm_epoch() to tl_api_rw;

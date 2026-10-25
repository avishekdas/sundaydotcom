-- 0001_init — core tables (arch 03 §3.3, §3.3a, §3.7). Runs as tl_migrator.
-- TOAST lz4 comes from the Aurora parameter default_toast_compression (D-028), not DDL.
create sequence tl.id_seq cache 20;   -- one id space for every entity (B6.3); not creation-ordered (PERF-19)

create table tl.account (id smallint primary key default 1 check (id = 1),
  name text not null, logo_file_id bigint, timezone text not null default 'UTC',
  date_format text not null, week_start smallint not null, allowed_domains jsonb not null default '[]',
  require_mfa boolean not null default true,
  perm_epoch bigint not null default 0,         -- global permission epoch (07 §7.2)
  db_generation bigint not null default 1,      -- incremented by the restore runbook (OPS-10)
  settings jsonb not null default '{}');

create table tl.users (id bigint primary key default nextval('tl.id_seq'), cognito_sub uuid unique,
  email citext unique not null, name text not null, title text, phone text, photo_file_id bigint, timezone text,
  role text not null check (role in ('admin','member','viewer','guest')),
  status text not null check (status in ('invited','active','deactivated')),
  tokens_valid_after timestamptz not null default 'epoch',   -- AR-9 revocation
  created_at timestamptz not null default now(), updated_at timestamptz not null default now());

create table tl.workspaces (id bigint primary key default nextval('tl.id_seq'), name text not null,
  description text, icon jsonb, kind text not null check (kind in ('open','closed')),
  is_default boolean not null default false, position text collate "C" not null,
  state text not null default 'active' check (state in ('active','archived','deleted')),
  deleted_at timestamptz, version bigint not null default 1);
create table tl.workspace_members (workspace_id bigint references tl.workspaces, user_id bigint references tl.users,
  role text not null check (role in ('owner','member')), primary key (workspace_id, user_id));

create table tl.boards (id bigint primary key default nextval('tl.id_seq'),
  workspace_id bigint not null references tl.workspaces,
  folder_id bigint, parent_board_id bigint references tl.boards,       -- subitem boards (B7)
  name text not null, description text, item_term text not null default 'Item',
  kind text not null check (kind in ('main','private','shareable')),
  permission_set text not null default 'edit_everything'
    check (permission_set in ('edit_everything','edit_content','edit_assigned','view_comment')),
  assign_column_id text,
  crm_entity_type text check (crm_entity_type in ('lead','contact','account','deal')),
  row_visibility text not null default 'board' check (row_visibility in ('board','related')),  -- D-016
  is_system boolean not null default false, top_group_id bigint, position text collate "C" not null,
  state text not null default 'active' check (state in ('active','archived','deleted')),
  deleted_at timestamptz, version bigint not null default 1,
  created_by bigint, created_at timestamptz not null default now());
create table tl.board_members (board_id bigint references tl.boards, principal_type text not null default 'user',
  principal_id bigint not null, role text not null check (role in ('owner','member')),
  subscribed boolean not null default true, primary key (board_id, principal_type, principal_id));

create table tl.groups (id bigint primary key default nextval('tl.id_seq'), board_id bigint not null references tl.boards,
  title text not null, color text not null, position text collate "C" not null,
  state text not null default 'active' check (state in ('active','archived','deleted')), deleted_at timestamptz);

create table tl.columns (board_id bigint references tl.boards, id text not null,  -- slug, immutable
  title text not null, type text not null, description text, settings jsonb not null default '{}',
  position text collate "C" not null,
  state text not null default 'active' check (state in ('active','archived','deleted')), deleted_at timestamptz,
  version bigint not null default 1, primary key (board_id, id));
create unique index columns_title_unique on tl.columns (board_id, lower(title)) where state = 'active';

create table tl.items (id bigint primary key default nextval('tl.id_seq'), board_id bigint not null references tl.boards,
  group_id bigint not null references tl.groups, parent_item_id bigint references tl.items,
  name text not null, position text collate "C" not null,
  values jsonb not null default '{}',            -- user-entered cell values keyed by column id
  computed jsonb not null default '{}',          -- materialized formula / mirror values (ADR-009)
  version bigint not null default 1,             -- D-010
  computed_version bigint not null default 0,    -- AR-2
  computed_source_seq bigint not null default 0, -- OPS-1
  created_idem_key text unique,                  -- AR-13
  state text not null default 'active' check (state in ('active','archived','deleted')),
  deleted_at timestamptz, archived_at timestamptz,
  created_by_type text not null, created_by bigint, created_at timestamptz not null default now(),
  updated_by_type text, updated_by bigint, updated_at timestamptz not null default now())
  with (fillfactor = 90);                        -- HOT updates for computed-only changes (PERF-11)
create index items_board_list on tl.items (board_id, state, group_id, position);
create index items_parent on tl.items (parent_item_id) where parent_item_id is not null;
create index items_values_gin on tl.items using gin (board_id, values jsonb_path_ops);   -- S-1: 10x on filters

create table tl.item_text (item_id bigint not null references tl.items, column_id text not null, body text not null,
  primary key (item_id, column_id));

create table tl.item_links (board_id bigint not null, column_id text not null,
  from_item_id bigint not null references tl.items, to_item_id bigint not null references tl.items,
  to_board_id bigint not null, position text collate "C" not null, created_at timestamptz not null default now(),
  primary key (from_item_id, column_id, to_item_id));
create index item_links_reverse on tl.item_links (to_item_id, board_id, column_id);
create index item_links_vis on tl.item_links (from_item_id, column_id, to_board_id);

create table tl.views (id bigint primary key default nextval('tl.id_seq'), board_id bigint not null references tl.boards,
  name text not null, type text not null check (type in ('table','kanban','form','calendar','gantt','chart','dashboard')),
  settings jsonb not null default '{}', filter jsonb, sort jsonb, group_by jsonb,
  position text collate "C" not null, is_default boolean not null default false, version bigint not null default 1,
  public_token text unique);
create table tl.view_item_positions (view_id bigint references tl.views, item_id bigint references tl.items,
  position text collate "C" not null, primary key (view_id, item_id));

-- Partitions for append-only logs (PERF-16); scheduler-tick (tl_worker) pre-creates ahead.
-- SECURITY DEFINER, so it is bounded to known parents and a small horizon, and only tl_worker may call it (M0A-2).
create function tl.ensure_partitions(parent regclass, from_day date, n int, step text) returns int
language plpgsql security definer set search_path = pg_catalog, tl as $$
declare
  base text := (select relname from pg_class where oid = parent);
  d date; nxt date; made int := 0; part text;
begin
  if parent not in ('tl.board_changes'::regclass, 'tl.outbox'::regclass, 'tl.activity_log'::regclass) then
    raise exception 'ensure_partitions: % is not a partitioned log table', parent;
  end if;
  if n < 1 or n > 31 or step not in ('day', 'month') then
    raise exception 'ensure_partitions: n must be 1..31 and step day|month (got %, %)', n, step;
  end if;
  for i in 0 .. n - 1 loop
    if step = 'day' then
      d := from_day + i; nxt := d + 1; part := base || '_p' || to_char(d, 'YYYYMMDD');
    else
      d := (date_trunc('month', from_day) + make_interval(months => i))::date;
      nxt := (d + interval '1 month')::date; part := base || '_p' || to_char(d, 'YYYYMM');
    end if;
    if to_regclass('tl.' || part) is null then
      execute format('create table tl.%I partition of %s for values from (%L) to (%L)', part, parent,
        (d::timestamp at time zone 'UTC'), (nxt::timestamp at time zone 'UTC'));
      made := made + 1;
    end if;
  end loop;
  return made;
end $$;
create function tl.ensure_daily_partitions(parent regclass, from_day date, days int) returns int
language sql security definer set search_path = pg_catalog, tl
as $$ select tl.ensure_partitions(parent, from_day, days, 'day') $$;
revoke execute on function tl.ensure_partitions(regclass, date, int, text), tl.ensure_daily_partitions(regclass, date, int) from public;
grant execute on function tl.ensure_partitions(regclass, date, int, text), tl.ensure_daily_partitions(regclass, date, int) to tl_worker;

create table tl.board_changes (seq bigserial, board_id bigint not null, item_id bigint,
  kind text not null check (kind in ('value','computed','links','moved','archived','deleted','restored','structure')),
  columns text[], xid xid8 not null default pg_current_xact_id(), at timestamptz not null default now(),
  primary key (seq, at)) partition by range (at);
create index board_changes_cursor on tl.board_changes (board_id, xid);

create table tl.recompute_pending (item_id bigint primary key, requested_seq bigint not null,
  requested_at timestamptz not null default now(), claimed_until timestamptz);

create table tl.leases (name text primary key, holder text, until timestamptz not null default 'epoch');   -- FR-3

create table tl.outbox (id bigserial, event_id uuid not null, type text not null,
  schema_version smallint not null default 1,
  board_id bigint, item_id bigint, payload jsonb not null, created_at timestamptz not null default now(),
  published_at timestamptz, publish_attempts smallint not null default 0, last_published_at timestamptz,
  primary key (id, created_at), unique (event_id, created_at)) partition by range (created_at);
create index outbox_unpublished on tl.outbox (id) where published_at is null;

create table tl.activity_log (id bigint not null default nextval('tl.id_seq'), board_id bigint not null, item_id bigint,
  actor_type text not null, actor_id bigint, kind text not null, column_id text, before jsonb, after jsonb,
  at timestamptz not null default now(), primary key (id, at)) partition by range (at);   -- monthly, kept 12 months (A15.4)
create index activity_log_board on tl.activity_log (board_id, at desc);
create index activity_log_item on tl.activity_log (item_id, at desc) where item_id is not null;

-- Horizon: yesterday + 7 days ahead (M0A-15) so a stalled scheduler-tick has a week before writes fail.
select tl.ensure_partitions('tl.board_changes', current_date - 1, 9, 'day');
select tl.ensure_partitions('tl.outbox', current_date - 1, 9, 'day');
select tl.ensure_partitions('tl.activity_log', current_date, 3, 'month');

create table tl.idempotency_keys (key text not null, user_id bigint not null, request_hash text not null,
  status text not null default 'in_progress', response jsonb, created_at timestamptz not null default now(),
  primary key (user_id, key));   -- SEC-15

create table tl.jobs (id bigint primary key default nextval('tl.id_seq'), type text not null, status text not null,
  progress jsonb, input jsonb, result jsonb, created_by bigint, created_at timestamptz not null default now());

create table tl.audit_events (id bigint primary key default nextval('tl.id_seq'), actor_id bigint, kind text not null,
  target jsonb, ip inet, user_agent text, at timestamptz not null default now());

-- Indexes for the permission snapshot and FK lookups (M0A-16)
create index board_members_principal on tl.board_members (principal_type, principal_id);
create index workspace_members_user on tl.workspace_members (user_id);
create index groups_board on tl.groups (board_id);
create index views_board on tl.views (board_id);
create index idempotency_keys_created on tl.idempotency_keys (created_at);

-- The singleton account row: the epoch guard (03 §3.5) reads perm_epoch from it (M0A-16).
insert into tl.account (name, date_format, week_start) values ('Tasklane', 'YYYY-MM-DD', 1);

-- Exceptions to the default grants (07 §7.3 least privilege) --------------------------------------
revoke insert, delete on tl.account from tl_api_rw, tl_worker;    -- singleton (M0A-4)
revoke delete on tl.outbox from tl_api_rw;                         -- only the purge (tl_worker) deletes
revoke all on tl.audit_events from tl_reader, tl_worker;
revoke update, delete on tl.audit_events from tl_api_rw;          -- append-only
grant insert on tl.audit_events to tl_audit_writer;

-- Public form worker: build an item only (FR-5, SEC-8)
grant select on tl.account, tl.workspaces, tl.boards, tl.board_members, tl.groups, tl.columns, tl.views,
  tl.items, tl.item_links, tl.item_text, tl.recompute_pending, tl.idempotency_keys to tl_worker_forms;
grant insert, update on tl.items, tl.item_links, tl.item_text, tl.recompute_pending, tl.idempotency_keys to tl_worker_forms;
grant insert on tl.board_changes, tl.outbox, tl.activity_log to tl_worker_forms;

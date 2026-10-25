-- run-as: admin
-- Bootstrap: roles per function class (PE-8, SEC-11), extensions, schema owned by tl_migrator.
-- Roles are NOLOGIN here; the migrate λ / CDK sets LOGIN + password from each role's secret.
do $$
declare r text;
begin
  foreach r in array array['tl_migrator','tl_api_rw','tl_reader','tl_worker','tl_worker_forms','tl_audit_writer'] loop
    if not exists (select 1 from pg_roles where rolname = r) then
      execute format('create role %I nologin', r);
    end if;
  end loop;
end $$;
grant tl_migrator to current_user;

create extension if not exists citext;
create extension if not exists btree_gin;
create extension if not exists pg_trgm;

create schema tl authorization tl_migrator;
grant usage on schema tl to tl_api_rw, tl_reader, tl_worker, tl_worker_forms, tl_audit_writer;

create table tl.schema_migrations (version text primary key, name text not null, checksum text not null,
  applied_at timestamptz not null default now());
alter table tl.schema_migrations owner to tl_migrator;

-- Everything tl_migrator creates from here on is granted by default; exceptions are revoked per table.
alter default privileges for role tl_migrator in schema tl grant select on tables to tl_reader;
alter default privileges for role tl_migrator in schema tl grant select, insert, update, delete on tables to tl_api_rw, tl_worker;
alter default privileges for role tl_migrator in schema tl grant usage, select on sequences to tl_api_rw, tl_worker, tl_worker_forms, tl_audit_writer;
-- Functions: the per-schema form cannot remove PUBLIC's EXECUTE (M0A-2), so revoke globally for the migrator
-- and grant each function explicitly where it is created.
alter default privileges for role tl_migrator revoke execute on functions from public;

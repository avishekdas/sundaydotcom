-- 0002 — partition retention for scheduler-tick (PERF-16, A15.4). SECURITY DEFINER, so the retention floor
-- is fixed here and the cutoff uses the database's own clock; callers cannot shorten it.
create function tl.drop_partitions_older_than(parent regclass, keep_days int) returns int
language plpgsql security definer set search_path = pg_catalog, tl as $$
declare
  floor_days int := case parent when 'tl.board_changes'::regclass then 2
                                when 'tl.outbox'::regclass then 7
                                when 'tl.activity_log'::regclass then 365 end;
  cutoff date;
  r record;
  ends date;
  dropped int := 0;
begin
  if floor_days is null then
    raise exception 'drop_partitions_older_than: % is not a partitioned log table', parent;
  end if;
  if keep_days < floor_days or keep_days > 3650 then
    raise exception 'drop_partitions_older_than: keep_days for % must be % .. 3650 (got %)', parent, floor_days, keep_days;
  end if;
  cutoff := current_date - keep_days;
  for r in select c.relname from pg_inherits i join pg_class c on c.oid = i.inhrelid where i.inhparent = parent loop
    if r.relname ~ '_p\d{8}$' then
      ends := to_date(right(r.relname, 8), 'YYYYMMDD') + 1;
    elsif r.relname ~ '_p\d{6}$' then
      ends := (to_date(right(r.relname, 6), 'YYYYMM') + interval '1 month')::date;
    else
      continue;
    end if;
    if ends <= cutoff then
      execute format('drop table tl.%I', r.relname);
      dropped := dropped + 1;
    end if;
  end loop;
  return dropped;
end $$;
revoke execute on function tl.drop_partitions_older_than(regclass, int) from public;
grant execute on function tl.drop_partitions_older_than(regclass, int) to tl_worker;

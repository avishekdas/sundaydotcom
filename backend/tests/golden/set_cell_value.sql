with old as (select id, values -> :col as v from tl.items
             where id = :id and state = 'active' for update),
u as (update tl.items i set values = jsonb_set(i.values, array[:col], :v::jsonb, true),
             version = i.version + 1, updated_by_type = :atype, updated_by = :aid, updated_at = now()
      from old
      where i.id = old.id
        and (select perm_epoch from tl.account) = :cached_epoch
        and (:assign_col::text is null
             or i.values -> :assign_col -> 'p' @> :me::jsonb
             or exists (select 1 from tl.items p where p.id = i.parent_item_id
                        and p.values -> :assign_col -> 'p' @> :me::jsonb))
      returning i.id, i.board_id, i.version, old.v as before, i.values -> :col as after),
a as (insert into tl.activity_log (board_id, item_id, actor_type, actor_id, kind, column_id, before, after)
      select board_id, id, :atype, :aid, 'value', :col, before, after from u),
c as (insert into tl.board_changes (board_id, item_id, kind, columns)
      select board_id, id, 'value', array[:col] from u returning seq),
r as (insert into tl.recompute_pending (item_id, requested_seq) select u.id, c.seq from u, c
      on conflict (item_id) do update set requested_seq = greatest(tl.recompute_pending.requested_seq, excluded.requested_seq)),
o as (insert into tl.outbox (event_id, type, board_id, item_id, payload)
      select :eid::uuid, 'item.values_changed', board_id, id,
             jsonb_build_object('changes', jsonb_build_array(jsonb_build_object('col', :col, 'old', before, 'new', after)),
                                'version', version, 'seq', (select seq from c), 'mutation_id', :mid) from u)
select u.version, (select seq from c) as seq from u
union all
select null, null where not exists (select 1 from u)

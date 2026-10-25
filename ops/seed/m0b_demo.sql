-- M0b walking-skeleton demo data (dev only). :sub = the Cognito sub of test user A.
-- Idempotent: safe to re-run.
insert into tl.users (id, cognito_sub, email, name, role, status)
values (1, :sub::uuid, 'tasklane-test-a@example.com', 'Test User A', 'admin', 'active')
on conflict (id) do update set cognito_sub = excluded.cognito_sub, status = 'active';
insert into tl.workspaces (id, name, kind, position, is_default) values (1, 'Main workspace', 'open', 'a', true)
on conflict (id) do nothing;
insert into tl.boards (id, workspace_id, name, kind, position, item_term)
values (10, 1, 'Skeleton board', 'main', 'a', 'Item') on conflict (id) do nothing;
insert into tl.groups (id, board_id, title, color, position)
values (100, 10, 'This week', 'blue', 'a'), (101, 10, 'Next week', 'purple', 'b') on conflict (id) do nothing;
insert into tl.columns (board_id, id, title, type, settings, position) values
  (10, 'status', 'Status', 'status',
   '{"labels":[{"id":0,"text":"Working on it","color":"#fdab3d"},{"id":1,"text":"Done","color":"#00c875"},{"id":2,"text":"Stuck","color":"#df2f4a"}]}', 'a'),
  (10, 'note', 'Note', 'text', '{}', 'b'),
  (10, 'amount', 'Amount', 'numbers', '{}', 'c')
on conflict (board_id, id) do nothing;
insert into tl.items (id, board_id, group_id, name, position, created_by_type, created_by, values)
select 1000 + g, 10, case when g <= 12 then 100 else 101 end, 'Task ' || g, lpad(g::text, 4, '0'), 'system', 1,
       jsonb_build_object('status', jsonb_build_object('l', g % 3), 'amount', (g * 125)::text)
from generate_series(1, 20) g
on conflict (id) do nothing;
-- explicit demo ids above must never collide with generated ones
select setval('tl.id_seq', greatest((select last_value from tl.id_seq), 100000));

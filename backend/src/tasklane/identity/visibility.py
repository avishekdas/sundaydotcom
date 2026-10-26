"""VisibleItems builder (ADR-014, arch 07 §7.2/§7.2a): the single definition of what a user can see.

Every row-returning query is built on these CTEs, so board visibility, row visibility (D-016/D-020) and item
state are decided in one place:

- ``vis_user``   — the user, only while active (deactivated or unknown → every CTE is empty);
- ``vis_boards`` — active boards in active workspaces the user can open: admins all (K1.1, audited by the caller);
  explicit board members regardless of workspace (K2.1), guests only on shareable boards; members and viewers
  every main board of an open workspace or a workspace they belong to (K2); subitem boards follow their parent
  board (B7.7);
- ``vis_items``  — active items on visible boards; on ``row_visibility='related'`` boards (Activities) only items
  linked through ``related_item`` to an active item on a visible board.

Sets never travel as array parameters (Data API, AR-4): the only parameter is the user id.
"""

from __future__ import annotations

from tasklane.platform.db import Param
from tasklane.platform.mutation import Cte

USER_PARAM = "vis_uid"

VIS_USER = Cte(
    "vis_user",
    "select u.id, u.role from tl.users u where u.id = :vis_uid and u.status = 'active'",
)

VIS_BOARDS = Cte(
    "vis_boards",
    """select b.id
       from tl.boards b
       join tl.boards root on root.id = coalesce(b.parent_board_id, b.id)
       join tl.workspaces w on w.id = root.workspace_id
       cross join vis_user vu
       where b.state = 'active' and root.state = 'active' and w.state = 'active'
         and (vu.role = 'admin'
              or (exists (select 1 from tl.board_members bm
                          where bm.board_id = root.id and bm.principal_type = 'user' and bm.principal_id = vu.id)
                  and (vu.role <> 'guest' or root.kind = 'shareable'))
              or (vu.role in ('member', 'viewer') and root.kind = 'main'
                  and (w.kind = 'open'
                       or exists (select 1 from tl.workspace_members wm
                                  where wm.workspace_id = w.id and wm.user_id = vu.id))))""",
)

VIS_ITEMS = Cte(
    "vis_items",
    """select i.id, i.board_id
       from tl.items i
       join tl.boards b on b.id = i.board_id
       where i.state = 'active' and i.board_id in (select id from vis_boards)
         and (b.row_visibility = 'board'
              or exists (select 1 from tl.item_links l join tl.items t on t.id = l.to_item_id
                         where l.from_item_id = i.id and l.column_id = 'related_item'
                           and t.state = 'active' and l.to_board_id in (select id from vis_boards)))""",
)

CTES = (VIS_USER, VIS_BOARDS, VIS_ITEMS)


def visibility_ctes(user_id: int) -> tuple[list[Cte], dict[str, Param]]:
    """The CTEs (in dependency order) and their parameters, for composing into a larger statement."""
    return list(CTES), {USER_PARAM: user_id}


def visible_sql(user_id: int, select: str) -> tuple[str, dict[str, Param]]:
    """``with vis_user …, vis_boards …, vis_items … <select>`` — ``select`` may read any of the three CTEs."""
    ctes, params = visibility_ctes(user_id)
    head = ",\n".join(f"{c.name} as ({c.sql})" for c in ctes)
    return f"with {head}\n{select}", params


VIS_USER_BY_SUB = Cte(
    "vis_user",
    "select u.id, u.role from tl.users u where u.cognito_sub = :vis_sub::uuid and u.status = 'active'",
)

SNAPSHOT_SELECT = """select json_build_object(
  'user', (select json_build_object('id', u.id::text, 'name', u.name, 'email', u.email::text, 'role', u.role,
                                    'tva', extract(epoch from u.tokens_valid_after)::bigint)
           from tl.users u join vis_user v on v.id = u.id),
  'epoch', (select perm_epoch from tl.account),
  'boards', coalesce((select json_agg(json_build_array(b.id::text, root.permission_set,
                        exists (select 1 from tl.board_members bm
                                where bm.board_id = root.id and bm.principal_type = 'user'
                                  and bm.principal_id = (select id from vis_user) and bm.role = 'owner')))
                      from vis_boards vb join tl.boards b on b.id = vb.id
                      join tl.boards root on root.id = coalesce(b.parent_board_id, b.id)), '[]'))::text as doc"""


def snapshot_sql(cognito_sub: str) -> tuple[str, dict[str, Param]]:
    """One statement for the PermissionSnapshot (07 §7.2): the user (by token `sub`), the global permission epoch
    and every board they can see with its permission set and their ownership — built on the same ``vis_boards``."""
    head = ",\n".join(f"{c.name} as ({c.sql})" for c in (VIS_USER_BY_SUB, VIS_BOARDS))
    return f"with {head}\n{SNAPSHOT_SELECT}", {"vis_sub": cognito_sub}

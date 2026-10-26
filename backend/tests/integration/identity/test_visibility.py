"""VisibleItems harness (ADR-014, arch 07 §7.2/§7.2a, PE-9): one rule table, run against the real SQL.

The world below exercises each visibility rule once; later milestones add rows (new board kinds, teams,
trash/archive views) rather than new ad-hoc tests. Runs through StrictDataApiFake so the builder also obeys the
Data API rules (no array parameters, AR-4).

Rules (07 §7.2): deactivated → nothing; admin → every active board (K1.1 admin override); explicit board member
→ that board regardless of workspace (K2.1); main board → visible when its workspace is open or the user is a
workspace member (K2); guest → only shareable boards they are invited to; subitem boards follow their parent
board (B7.7) and are hidden when either is archived; archived/deleted boards and boards in archived workspaces are not visible; items must be active;
on `row_visibility='related'` boards (Activities, D-016/D-020) an item is visible only when it links to an
active item on a board the user can see, through the `related_item` column only.

The world was sharpened by mutating the builder: every condition in it is needed by at least one row.
"""

from __future__ import annotations

import psycopg
import pytest

from tasklane.identity.visibility import visible_sql
from tasklane.platform.db import StrictDataApiFake

pytestmark = [pytest.mark.integration]

USERS = {"adm": 1, "mia": 2, "raj": 3, "vic": 4, "dee": 5, "gus": 6}

WORLD = """
insert into tl.users (id, email, name, role, status) values
  (1, 'adm@x.test', 'Adm', 'admin', 'active'), (2, 'mia@x.test', 'Mia', 'member', 'active'),
  (3, 'raj@x.test', 'Raj', 'member', 'active'), (4, 'vic@x.test', 'Vic', 'viewer', 'active'),
  (5, 'dee@x.test', 'Dee', 'member', 'deactivated'), (6, 'gus@x.test', 'Gus', 'guest', 'active');
insert into tl.workspaces (id, name, kind, position, state) values
  (100, 'W1 open', 'open', 'a', 'active'), (200, 'W2 closed', 'closed', 'b', 'active'),
  (300, 'W3 archived', 'open', 'c', 'archived');
insert into tl.workspace_members (workspace_id, user_id, role) values (200, 2, 'owner'), (200, 5, 'member');
insert into tl.boards (id, workspace_id, parent_board_id, name, kind, row_visibility, state, position) values
  (110, 100, null, 'M1 main',        'main',      'board',   'active',   'a'),
  (111, 100, null, 'P1 private',     'private',   'board',   'active',   'b'),
  (112, 100, null, 'A1 activities',  'main',      'related', 'active',   'c'),
  (113, 100, null, 'X1 archived',    'main',      'board',   'archived', 'd'),
  (114, 100, 110,  'SUB1 of M1',     'main',      'board',   'active',   'e'),
  (115, 100, 113,  'SUB of archived','main',      'board',   'active',   'f'),
  (116, 100, 110,  'SUB archived',   'main',      'board',   'archived', 'g'),
  (210, 200, null, 'M2 main',        'main',      'board',   'active',   'a'),
  (211, 200, null, 'P2 private',     'private',   'board',   'active',   'b'),
  (212, 200, null, 'S2 shareable',   'shareable', 'board',   'active',   'c'),
  (213, 200, 211,  'SUB2 of P2',     'private',   'board',   'active',   'd'),
  (310, 300, null, 'M3 main',        'main',      'board',   'active',   'a');
insert into tl.board_members (board_id, principal_id, role) values
  (111, 3, 'member'), (211, 3, 'member'), (212, 6, 'member'), (110, 6, 'member');
insert into tl.groups (id, board_id, title, color, position)
  select b.id * 10, b.id, 'G', 'blue', 'a' from tl.boards b;
insert into tl.items (id, board_id, group_id, name, position, created_by_type, state, parent_item_id) values
  (1101, 110, 1100, 'm1 item',      'a', 'user', 'active',  null),
  (1102, 110, 1100, 'm1 deleted',   'b', 'user', 'deleted', null),
  (1111, 111, 1110, 'p1 item',      'a', 'user', 'active',  null),
  (1131, 113, 1130, 'x1 item',      'a', 'user', 'active',  null),
  (1141, 114, 1140, 'sub1 item',    'a', 'user', 'active',  1101),
  (1151, 115, 1150, 'sub of x1',    'a', 'user', 'active',  1131),
  (1161, 116, 1160, 'archived sub', 'a', 'user', 'active',  1101),
  (2101, 210, 2100, 'm2 item',      'a', 'user', 'active',  null),
  (2111, 211, 2110, 'p2 item',      'a', 'user', 'active',  null),
  (2121, 212, 2120, 's2 item',      'a', 'user', 'active',  null),
  (2131, 213, 2130, 'sub2 item',    'a', 'user', 'active',  2111),
  (3101, 310, 3100, 'm3 item',      'a', 'user', 'active',  null),
  (1121, 112, 1120, 'act → m1',     'a', 'user', 'active',  null),
  (1122, 112, 1120, 'act → p1',     'b', 'user', 'active',  null),
  (1123, 112, 1120, 'act → p2+m1',  'c', 'user', 'active',  null),
  (1124, 112, 1120, 'act → none',   'd', 'user', 'active',  null),
  (1125, 112, 1120, 'act → deleted','e', 'user', 'active',  null),
  (1126, 112, 1120, 'act ~ m1 (other column)', 'f', 'user', 'active', null);
insert into tl.item_links (board_id, column_id, from_item_id, to_item_id, to_board_id, position) values
  (112, 'related_item', 1121, 1101, 110, 'a'), (112, 'related_item', 1122, 1111, 111, 'a'),
  (112, 'related_item', 1123, 2111, 211, 'a'), (112, 'related_item', 1123, 1101, 110, 'b'),
  (112, 'related_item', 1125, 1102, 110, 'a'), (112, 'contact', 1126, 1101, 110, 'a');
"""

# user → (visible boards, visible items)
RULES: dict[str, tuple[set[int], set[int]]] = {
    "adm": (
        {110, 111, 112, 114, 210, 211, 212, 213},
        {1101, 1111, 1141, 2101, 2111, 2121, 2131, 1121, 1122, 1123},
    ),
    "mia": ({110, 112, 114, 210}, {1101, 1141, 2101, 1121, 1123}),
    "raj": ({110, 111, 112, 114, 211, 213}, {1101, 1111, 1141, 2111, 2131, 1121, 1122, 1123}),
    "vic": ({110, 112, 114}, {1101, 1141, 1121, 1123}),
    "dee": (set(), set()),
    "gus": ({212}, {2121}),
}


@pytest.fixture(scope="module")
def world(pg_uri: str) -> str:
    import uuid

    from psycopg.conninfo import make_conninfo

    from tasklane.platform.migrations import apply_migrations
    from tests.conftest import MIGRATIONS

    name = "vis_" + uuid.uuid4().hex[:8]
    with psycopg.connect(pg_uri, autocommit=True) as c:
        c.execute(f"create database {name}")
    uri = make_conninfo(pg_uri, dbname=name)
    apply_migrations(uri, MIGRATIONS)
    with psycopg.connect(uri, autocommit=True) as c:
        c.execute(WORLD)
    return uri


def _ids(db: StrictDataApiFake, user: str, select: str) -> set[int]:
    sql, params = visible_sql(USERS[user], select)
    return {int(r["id"]) for r in db.query(sql, params)}


@pytest.mark.parametrize("user", sorted(RULES))
def test_visible_boards(world: str, user: str) -> None:
    assert _ids(StrictDataApiFake(world), user, "select id from vis_boards") == RULES[user][0]


@pytest.mark.parametrize("user", sorted(RULES))
def test_visible_items(world: str, user: str) -> None:
    assert _ids(StrictDataApiFake(world), user, "select id from vis_items") == RULES[user][1]


def test_unknown_user_sees_nothing(world: str) -> None:
    sql, params = visible_sql(999, "select id from vis_items")
    assert StrictDataApiFake(world).query(sql, params) == []


def test_visible_items_are_on_visible_boards(world: str) -> None:
    """Metamorphic: for every user, vis_items ⊆ items on vis_boards."""
    db = StrictDataApiFake(world)
    for user in RULES:
        on_boards = _ids(
            db, user, "select i.id from tl.items i where i.board_id in (select id from vis_boards)"
        )
        assert _ids(db, user, "select id from vis_items") <= on_boards

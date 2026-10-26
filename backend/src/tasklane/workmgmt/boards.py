"""Skeleton board service (M0b story 6). Endpoints are thin adapters over these functions (arch 04 §4.4).

Authorization is a stub here (any active user); the permission framework and VisibleItems arrive in M1.
IDs leave the service as strings (arch 04 §4.1).
"""

from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass, field
from typing import Any

from tasklane.platform.db import Db, Json
from tasklane.platform.mutation import Cte, Failure, Mutation, classify_failure, run
from tasklane.platform.outbox import OutboxEvent
from tasklane.schema.types import CodecError, codec_for

MAX_FETCH = 200
_SLUG = re.compile(r"^[a-z][a-z0-9_]{0,62}$")


class ValidationFailed(ValueError):
    def __init__(self, fields: dict[str, str]) -> None:
        super().__init__("validation_error")
        self.fields = fields


@dataclass(frozen=True)
class Actor:
    user_id: int
    cached_epoch: int
    actor_type: str = "user"


def _j(v: Any) -> Any:
    return json.loads(v) if isinstance(v, str) else v


def get_schema(db: Db, board_id: int) -> dict[str, Any] | None:
    rows = db.query(
        """select json_build_object(
             'board', (select json_build_object('id', b.id::text, 'name', b.name, 'item_term', b.item_term,
                                                 'version', b.version) from tl.boards b
                       where b.id = :b and b.state = 'active'),
             'groups', coalesce((select json_agg(json_build_object('id', g.id::text, 'title', g.title, 'color', g.color,
                                                                    'position', g.position) order by g.position, g.id)
                                 from tl.groups g where g.board_id = :b and g.state = 'active'), '[]'),
             'columns', coalesce((select json_agg(json_build_object('id', c.id, 'title', c.title, 'type', c.type,
                                                                     'settings', c.settings, 'version', c.version)
                                                  order by c.position, c.id)
                                  from tl.columns c where c.board_id = :b and c.state = 'active'), '[]'))::text as doc""",
        {"b": board_id},
    )
    doc = _j(rows[0]["doc"])
    return doc if doc["board"] else None


def query_board(db: Db, board_id: int) -> dict[str, Any]:
    """Ordered item ids + group counts (filter/sort QuerySpec compiler arrives in M2)."""
    rows = db.query(
        """select json_build_object(
             'ids', coalesce((select json_agg(i.id::text order by g.position, g.id, i.position, i.id)
                              from tl.items i join tl.groups g on g.id = i.group_id
                              where i.board_id = :b and i.state = 'active' and i.parent_item_id is null), '[]'),
             'groups', coalesce((select json_agg(json_build_object('id', g.id::text, 'count',
                                   (select count(*) from tl.items i where i.group_id = g.id and i.state = 'active'
                                      and i.parent_item_id is null)) order by g.position, g.id)
                                 from tl.groups g where g.board_id = :b and g.state = 'active'), '[]'))::text as doc""",
        {"b": board_id},
    )
    return _j(rows[0]["doc"])  # type: ignore[no-any-return]


def fetch_items(db: Db, board_id: int, ids: list[str]) -> list[dict[str, Any]]:
    if len(ids) > MAX_FETCH:
        raise ValidationFailed({"ids": f"at most {MAX_FETCH} ids per request"})
    try:
        clean = [int(i) for i in ids]
    except ValueError:
        raise ValidationFailed({"ids": "ids must be integers"}) from None
    rows = db.query(
        """select json_build_object('id', i.id::text, 'name', i.name, 'group_id', i.group_id::text,
                                    'version', i.version, 'values', i.values, 'computed', i.computed)::text as doc
           from tl.items i
           where i.board_id = :b and i.state = 'active'
             and i.id in (select (jsonb_array_elements_text(:ids::jsonb))::bigint)""",
        {"b": board_id, "ids": Json(clean)},
    )
    by_id = {d["id"]: d for d in (_j(r["doc"]) for r in rows)}
    return [by_id[str(i)] for i in clean if str(i) in by_id]


@dataclass(frozen=True)
class WriteResult:
    version: int | None = None
    values: dict[str, Any] = field(default_factory=dict)
    events: list[OutboxEvent] = field(default_factory=list)
    failure: Failure | None = None


def _columns_of_item_board(db: Db, item_id: int) -> tuple[int | None, dict[str, dict[str, Any]]]:
    rows = db.query(
        """select i.board_id, coalesce((select json_object_agg(c.id, json_build_object('type', c.type, 'settings', c.settings))
                                         from tl.columns c where c.board_id = i.board_id and c.state = 'active'), '{}')::text as cols
           from tl.items i where i.id = :id and i.state = 'active'""",
        {"id": item_id},
    )
    if not rows:
        return None, {}
    return int(rows[0]["board_id"]), _j(rows[0]["cols"])


def set_values(
    db: Db, actor: Actor, item_id: int, changes_in: dict[str, Any], *, mutation_id: str
) -> WriteResult:
    board_id, cols = _columns_of_item_board(db, item_id)
    if board_id is None:
        return WriteResult(failure="not_found")
    errors: dict[str, str] = {}
    normalized: dict[str, Any] = {}
    for col, raw in changes_in.items():
        if not _SLUG.match(col) or col not in cols:
            errors[f"values.{col}"] = "unknown column"
            continue
        try:
            normalized[col] = codec_for(cols[col]["type"]).normalize(raw, cols[col]["settings"])
        except CodecError as e:
            errors[f"values.{col}"] = str(e)
    if errors:
        raise ValidationFailed(errors)
    if not normalized:
        raise ValidationFailed({"values": "no changes"})
    to_set = {k: v for k, v in normalized.items() if v is not None}
    to_del = sorted(k for k, v in normalized.items() if v is None)
    event_id = str(uuid.uuid4())
    m = Mutation(
        lock=Cte(
            "pre",
            """select id, values as v from tl.items
             where id = :id and board_id = :board and state = 'active' for update""",
        ),
        main=Cte(
            "u",
            """update tl.items i
             set values = (i.values || :set::jsonb) - coalesce((select array_agg(k) from jsonb_array_elements_text(:del::jsonb) k), '{}'::text[]),
                 version = i.version + 1, updated_by_type = :atype, updated_by = :aid, updated_at = now()
      from pre
      where i.id = pre.id and (select perm_epoch from tl.account) = :cached_epoch
      returning i.id, i.board_id, i.version, pre.v as before_all, i.values as after_all""",
        ),
        final="""select u.version, (select seq from c) as seq, (select payload::text from o) as payload from u
union all
select null, null, null where not exists (select 1 from u)""",
        params={
            "id": item_id,
            "board": board_id,
            "set": Json(to_set),
            "del": Json(to_del),
            "cols": Json(sorted(normalized)),
            "atype": actor.actor_type,
            "aid": actor.user_id,
            "cached_epoch": actor.cached_epoch,
            "eid": event_id,
            "mid": mutation_id,
        },
    )
    m.add(
        Cte(
            "ch",
            """select u.id, u.board_id, k.col, u.before_all -> k.col as before, u.after_all -> k.col as after
      from u, jsonb_array_elements_text(:cols::jsonb) as k(col)""",
        )
    )
    m.add(
        Cte(
            "a",
            """insert into tl.activity_log (board_id, item_id, actor_type, actor_id, kind, column_id, before, after)
      select board_id, id, :atype, :aid, 'value', col, before, after from ch""",
        )
    )
    m.add(
        Cte(
            "c",
            """insert into tl.board_changes (board_id, item_id, kind, columns)
      select board_id, id, 'value', (select array_agg(col order by col) from ch) from u returning seq""",
        )
    )
    m.add(
        Cte(
            "r",
            """insert into tl.recompute_pending (item_id, requested_seq) select u.id, c.seq from u, c
      on conflict (item_id) do update set requested_seq = greatest(tl.recompute_pending.requested_seq, excluded.requested_seq)""",
        )
    )
    m.add(
        Cte(
            "o",
            """insert into tl.outbox (event_id, type, board_id, item_id, payload)
      select :eid::uuid, 'item.values_changed', board_id, id,
             jsonb_build_object('changes', (select jsonb_agg(jsonb_build_object('col', col, 'old', before, 'new', after)
                                                             order by col) from ch),
                                'version', version, 'seq', (select seq from c), 'mutation_id', :mid::text)
      from u returning payload""",
        )
    )
    res = run(db, m)
    if not res.ok:
        return WriteResult(failure=classify_failure(db, item_id=item_id, cached_epoch=actor.cached_epoch))
    payload = _j(res.row["payload"])  # exactly what the outbox row holds, so a sweeper republish is identical
    event = OutboxEvent(
        event_id=event_id,
        type="item.values_changed",
        schema_version=1,
        board_id=board_id,
        item_id=item_id,
        payload=payload,
    )
    return WriteResult(version=res.version, values=normalized, events=[event])


CHANGES_PAGE = 1000
CURSOR_MAX_AGE_S = 24 * 3600  # board_changes keeps 25 h; older cursors must reload (arch 03 §3.3a)
_CURSOR = re.compile(r"^v1\.(\d+)\.(-?\d+)\.(\d+)$")


class CursorExpired(ValueError):
    """The cursor is older than the change-log retention → 410, the client reloads the board."""


def encode_cursor(xid: int, seq: int, issued: int) -> str:
    return f"v1.{xid}.{seq}.{issued}"


def changes(db: Db, board_id: int, *, since_xmin: str | None) -> dict[str, Any]:
    """Gap sync (arch 03 §3.3a, M0B-1).

    The cursor is opaque: a keyset position (xid, seq) plus the time it was issued. Rows come back in (xid, seq)
    order with ``(xid, seq) > position`` and ``xid < pg_snapshot_xmin`` (every older transaction has finished, so
    none can still appear below the position). A full page returns ``more: true`` and a cursor at the last row;
    otherwise the next cursor is the snapshot xmin. Cursors older than 24 h raise CursorExpired.
    """
    if since_xmin is None:
        cx, cs, issued = None, -1, 0
    else:
        m = _CURSOR.match(since_xmin)
        if not m:
            raise ValidationFailed({"since_xmin": "invalid cursor"})
        cx, cs, issued = int(m.group(1)), int(m.group(2)), int(m.group(3))
    rows = db.query(
        """with snap as (select pg_snapshot_xmin(pg_current_snapshot()) as xmin, extract(epoch from now())::bigint as now_s),
           page as (select c.item_id, c.kind, c.columns, c.seq, c.xid from tl.board_changes c, snap
                    where :cx::text is not null and c.board_id = :b and c.at >= now() - interval '25 hours'
                      and (c.xid > (:cx::text)::xid8 or (c.xid = (:cx::text)::xid8 and c.seq > :cs))
                      and c.xid < snap.xmin
                    order by c.xid, c.seq limit :lim)
           select json_build_object(
             'xmin', (select xmin::text from snap), 'now_s', (select now_s from snap),
             'db_generation', (select db_generation from tl.account),
             'rows', coalesce((select json_agg(json_build_object('item_id', p.item_id::text, 'kind', p.kind,
                                 'columns', p.columns, 'seq', p.seq, 'xid', p.xid::text) order by p.xid, p.seq)
                               from page p), '[]'::json))::text as doc""",
        {"b": board_id, "cx": None if cx is None else str(cx), "cs": cs, "lim": CHANGES_PAGE + 1},
    )
    doc = _j(rows[0]["doc"])
    now_s = int(doc["now_s"])
    if cx is not None and now_s - issued > CURSOR_MAX_AGE_S:
        raise CursorExpired(since_xmin)
    page = doc["rows"]
    more = len(page) > CHANGES_PAGE
    page = page[:CHANGES_PAGE]
    if more:
        last = page[-1]
        nxt = encode_cursor(int(last["xid"]), int(last["seq"]), issued)
    else:
        nxt = encode_cursor(int(doc["xmin"]), -1, now_s)
    return {"next_since_xmin": nxt, "db_generation": doc["db_generation"], "more": more,
            "changes": [{k: r[k] for k in ("item_id", "kind", "columns", "seq")} for r in page]}

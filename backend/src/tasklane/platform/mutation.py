"""Mutation builder: one writable-CTE statement per mutation (arch 03 §3.5, 11; D-010, AR-3, SEC-3, PE-9).

A mutation is an ordered list of named CTEs:
  1. the **lock** CTE (`SELECT … FOR UPDATE`) — row locks + pre-images;
  2. the **main** write CTE ``u`` — carries the permission guards in its WHERE (SEC-3 epoch, edit_assigned);
  3. **fragments** — every further write depends on ``u`` (data dependency defines execution order) and no
     fragment reads rows written by a sibling (only their RETURNING output).
Other contexts contribute fragments with ``Mutation.add`` (activity log, board_changes, outbox, automation rows),
so their tables are written atomically without a multi-statement transaction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

from tasklane.platform.db import Db, Json, Param, param_names

_NAME = re.compile(r"^[a-z][a-z0-9_]*$")
_SLUG = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_DEPENDS_ON_U = re.compile(r"\bfrom\s+u\b|\bu\s*\.|\bfrom\s+[^;]*\bu\s*,|,\s*u\b", re.IGNORECASE)


class MutationRuleError(ValueError):
    """A mutation violates the single-statement CTE rules (arch 03 §3.5)."""


@dataclass(frozen=True)
class Cte:
    name: str
    sql: str
    params: dict[str, Param] = field(default_factory=dict)


@dataclass(frozen=True)
class MutationResult:
    ok: bool
    version: int | None
    seq: int | None


class Mutation:
    def __init__(self, *, lock: Cte, main: Cte, final: str, params: dict[str, Param] | None = None) -> None:
        if not re.search(r"\bfor\s+update\b", lock.sql, re.IGNORECASE):
            raise MutationRuleError("the first CTE must take row locks with SELECT … FOR UPDATE")
        if main.name != "u":
            raise MutationRuleError("the main write CTE must be named u")
        self._ctes: list[Cte] = []
        self._params: dict[str, Param] = {}
        self._final = final
        self._merge(params or {})
        self._push(lock)
        self._push(main)

    def _merge(self, params: dict[str, Param]) -> None:
        for k, v in params.items():
            if k in self._params and self._params[k] != v:
                raise MutationRuleError(f"conflicting value for parameter :{k}")
            self._params[k] = v

    def _push(self, cte: Cte) -> None:
        if not _NAME.match(cte.name):
            raise MutationRuleError(f"bad CTE name {cte.name!r}")
        if any(c.name == cte.name for c in self._ctes):
            raise MutationRuleError(f"duplicate CTE name {cte.name!r}")
        self._merge(cte.params)
        self._ctes.append(cte)

    def add(self, cte: Cte) -> Mutation:
        """Add a write fragment; it must depend on ``u``."""
        if not _DEPENDS_ON_U.search(cte.sql):
            msg = f"fragment {cte.name!r} must depend on the main write CTE u"
            raise MutationRuleError(msg)
        self._push(cte)
        return self

    def build(self) -> tuple[str, dict[str, Param]]:
        body = ",\n".join(f"{c.name} as ({c.sql.strip()})" for c in self._ctes)
        sql = f"with {body}\n{self._final.strip()}"
        used = set(param_names(sql))
        return sql, {k: v for k, v in self._params.items() if k in used}


def run(db: Db, mutation: Mutation) -> MutationResult:
    sql, params = mutation.build()
    rows = db.query(sql, params)
    row = rows[0] if rows else {"version": None, "seq": None}
    version = row.get("version")
    seq = row.get("seq")
    return MutationResult(
        ok=version is not None,
        version=int(version) if version is not None else None,
        seq=int(seq) if seq is not None else None,
    )


Failure = Literal["not_found", "stale_epoch", "forbidden"]


def classify_failure(db: Db, *, item_id: int, cached_epoch: int) -> Failure:
    """Map a 0-row mutation to 404 / retry-once / 403 (FR-9). One cheap read."""
    rows = db.query(
        """select case when not exists (select 1 from tl.items where id = :id and state = 'active') then 'not_found'
                       when (select perm_epoch from tl.account) <> :epoch then 'stale_epoch'
                       else 'forbidden' end as reason""",
        {"id": item_id, "epoch": cached_epoch},
    )
    reason: Any = rows[0]["reason"]
    return reason  # type: ignore[no-any-return]


# --- standard mutations -------------------------------------------------------------------------------


def _check_column(column_id: str) -> None:
    if not _SLUG.match(column_id):
        raise ValueError(f"bad column id {column_id!r}: column ids are immutable slugs")


def set_cell_value(
    *,
    item_id: int,
    column_id: str,
    value: Any,
    assign_column_id: str | None,
    actor_type: str,
    actor_id: int | None,
    cached_epoch: int,
    mutation_id: str,
    event_id: str,
) -> Mutation:
    """Scalar cell write (arch 03 §3.5 example) with epoch and edit_assigned guards."""
    _check_column(column_id)
    if assign_column_id is not None:
        _check_column(assign_column_id)
    m = Mutation(
        lock=Cte(
            "pre",
            """select id, values -> :col as v from tl.items
             where id = :id and state = 'active' for update""",
        ),
        main=Cte(
            "u",
            """update tl.items i set values = jsonb_set(i.values, array[:col::text], :v::jsonb, true),
             version = i.version + 1, updated_by_type = :atype, updated_by = :aid, updated_at = now()
      from pre
      where i.id = pre.id
        and (select perm_epoch from tl.account) = :cached_epoch
        and (:assign_col::text is null
             or i.values -> :assign_col -> 'p' @> :me::jsonb
             or exists (select 1 from tl.items p where p.id = i.parent_item_id
                        and p.values -> :assign_col -> 'p' @> :me::jsonb))
      returning i.id, i.board_id, i.version, pre.v as before, i.values -> :col as after""",
        ),
        final="""select u.version, (select seq from c) as seq from u
union all
select null, null where not exists (select 1 from u)""",
        params={
            "id": item_id,
            "col": column_id,
            "v": Json(value),
            "atype": actor_type,
            "aid": actor_id,
            "cached_epoch": cached_epoch,
            "assign_col": assign_column_id,
            "me": Json([{"t": "u", "id": actor_id}]),
            "eid": event_id,
            "mid": mutation_id,
        },
    )
    m.add(
        Cte(
            "a",
            """insert into tl.activity_log (board_id, item_id, actor_type, actor_id, kind, column_id, before, after)
      select board_id, id, :atype, :aid, 'value', :col, before, after from u""",
        )
    )
    m.add(
        Cte(
            "c",
            """insert into tl.board_changes (board_id, item_id, kind, columns)
      select board_id, id, 'value', array[:col::text] from u returning seq""",
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
             jsonb_build_object('changes', jsonb_build_array(jsonb_build_object('col', :col::text, 'old', before, 'new', after)),
                                'version', version, 'seq', (select seq from c), 'mutation_id', :mid::text) from u""",
        )
    )
    return m

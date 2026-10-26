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


class MutationRuleError(ValueError):
    """A mutation violates the single-statement CTE rules (arch 03 §3.5)."""


# Rule 4 (SEC-3): the main write carries these guards verbatim, so a cached permission snapshot can never authorize
# a write after a permission change, and edit_assigned is checked on the row itself (B7.7).
EPOCH_GUARD = "(select perm_epoch from tl.account) = :cached_epoch"
ASSIGN_GUARD = """(:assign_col::text is null
             or i.values -> :assign_col -> 'p' @> :me::jsonb
             or exists (select 1 from tl.items p where p.id = i.parent_item_id
                        and p.values -> :assign_col -> 'p' @> :me::jsonb))"""

_COMMENTS = re.compile(r"--[^\n]*|/\*.*?\*/", re.DOTALL)
_LITERALS = re.compile(r"'(?:[^']|'')*'")
_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_$.]*|[(),;]")
_CLAUSE_END = {
    "where",
    "group",
    "order",
    "limit",
    "returning",
    "on",
    "using",
    "join",
    "inner",
    "left",
    "right",
    "full",
    "cross",
    "natural",
    "union",
    "except",
    "intersect",
    "having",
    "window",
    "set",
    "values",
    "select",
    "for",
    "lateral",
}


def _code(sql: str) -> str:
    """SQL without comments and string literals: text there is never a table reference."""
    return _LITERALS.sub("''", _COMMENTS.sub(" ", sql))


def _relations(sql: str) -> set[str]:
    """Relation names read through FROM / JOIN lists (``x``, ``tl.x``), aliases excluded."""
    toks = [t.lower() for t in _TOKEN.findall(_code(sql))]
    out: set[str] = set()
    i = 0
    while i < len(toks):
        if toks[i] in ("from", "join") and i + 1 < len(toks):
            j = i + 1
            while j < len(toks) and toks[j] not in ("(", ")", ";") and toks[j] not in _CLAUSE_END:
                out.add(toks[j])
                j += 1
                if j < len(toks) and toks[j] == "as":
                    j += 1
                if j < len(toks) and toks[j] not in (",", "(", ")", ";") and toks[j] not in _CLAUSE_END:
                    j += 1  # alias
                if j < len(toks) and toks[j] == ",":
                    j += 1
                    continue
                break
            i = j
        else:
            i += 1
    return out


def _written(sql: str) -> str | None:
    """The table a write CTE changes (``insert into`` / ``update`` / ``delete from``)."""
    m = re.match(
        r"\s*(?:insert\s+into|update|delete\s+from)\s+([a-z_][a-z0-9_.]*)", _code(sql), re.IGNORECASE
    )
    return m.group(1).lower() if m else None


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
    row: dict[str, Any] = field(
        default_factory=dict
    )  # the full final-select row (extra columns per mutation)


class Mutation:
    def __init__(self, *, lock: Cte, main: Cte, final: str, params: dict[str, Param] | None = None) -> None:
        if not re.search(r"\bfor\s+update\b", lock.sql, re.IGNORECASE):
            raise MutationRuleError("the first CTE must take row locks with SELECT … FOR UPDATE")
        if main.name != "u":
            raise MutationRuleError("the main write CTE must be named u")
        if " ".join(EPOCH_GUARD.split()) not in " ".join(_code(main.sql).split()):
            raise MutationRuleError("the main write CTE must carry the epoch guard (SEC-3, rule 4)")
        self._ctes: list[Cte] = []
        self._dependents: set[str] = {"u"}  # u and every CTE that reads from it (transitively)
        self._written: dict[str, str] = {}  # table → CTE that writes it (rule 3)
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
        target = _written(cte.sql)
        if target and cte.name != self._ctes[0].name:
            self._written.setdefault(target, cte.name)

    def add(self, cte: Cte) -> Mutation:
        """Add a fragment. Rule 2: it reads ``u`` (or a CTE that does) as a relation. Rule 3: it reads no table
        that ``u`` or another fragment writes (it would see the pre-statement snapshot, not their writes)."""
        reads = _relations(cte.sql)
        if not reads & self._dependents:
            raise MutationRuleError(
                f"fragment {cte.name!r} must depend on the main write CTE u (read it in FROM)"
            )
        own = _written(cte.sql)
        for table in sorted(reads - {own} if own else reads):
            if table in self._written:
                raise MutationRuleError(
                    f"fragment {cte.name!r} reads {table}, which is written by {self._written[table]!r} "
                    "in the same statement (rule 3)"
                )
        self._push(cte)
        self._dependents.add(cte.name)
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
        row=dict(row),
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
        and __EPOCH_GUARD__
        and __ASSIGN_GUARD__
      returning i.id, i.board_id, i.version, pre.v as before, i.values -> :col as after""".replace(
                "__EPOCH_GUARD__", EPOCH_GUARD
            ).replace("__ASSIGN_GUARD__", ASSIGN_GUARD),
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

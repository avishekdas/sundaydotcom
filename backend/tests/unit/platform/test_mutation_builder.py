"""Mutation builder (arch 03 §3.5, 11 — DX-6, PE-9): composition rules and golden SQL."""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from tasklane.platform.db import Json, param_names
from tasklane.platform.mutation import Cte, Mutation, MutationRuleError, set_cell_value

GOLDEN = Path(__file__).resolve().parents[2] / "golden"


def norm(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def actor() -> dict[str, object]:
    return {"actor_type": "user", "actor_id": 42, "cached_epoch": 3, "mutation_id": "m-1",
            "event_id": "00000000-0000-0000-0000-000000000001"}


def test_set_cell_value_matches_golden_sql() -> None:
    sql, _ = set_cell_value(item_id=7, column_id="status", value={"i": 1}, assign_column_id=None, **actor()).build()  # type: ignore[arg-type]
    assert norm(sql) == norm((GOLDEN / "set_cell_value.sql").read_text())


def test_params_cover_exactly_the_placeholders() -> None:
    sql, params = set_cell_value(item_id=7, column_id="status", value={"i": 1}, assign_column_id="owner", **actor()).build()  # type: ignore[arg-type]
    assert set(param_names(sql)) == set(params)
    assert params["v"] == Json({"i": 1}) and params["me"] == Json([{"t": "u", "id": 42}])
    assert params["assign_col"] == "owner"


def test_fragments_from_other_contexts_are_added_before_the_final_select() -> None:
    m = set_cell_value(item_id=7, column_id="status", value=1, assign_column_id=None, **actor())  # type: ignore[arg-type]
    m.add(Cte("auto", "insert into tl.jobs (type, status, input) select 'automation', 'queued', jsonb_build_object('item', id) from u"))
    sql, _ = m.build()
    assert sql.index("auto as (") > sql.index("o as (") and sql.index("auto as (") < sql.index("select u.version")


def test_first_cte_must_lock_rows() -> None:
    with pytest.raises(MutationRuleError, match="FOR UPDATE"):
        Mutation(lock=Cte("old", "select id from tl.items where id = :id"), main=Cte("u", "update tl.items set name = 'x' from old returning id"),
                 final="select 1 from u", params={"id": 1})


def test_write_fragments_must_depend_on_the_main_write() -> None:
    m = set_cell_value(item_id=7, column_id="status", value=1, assign_column_id=None, **actor())  # type: ignore[arg-type]
    with pytest.raises(MutationRuleError, match="depend on"):
        m.add(Cte("bad", "insert into tl.jobs (type, status) values ('x', 'queued')"))


def test_duplicate_names_and_conflicting_params_are_rejected() -> None:
    m = set_cell_value(item_id=7, column_id="status", value=1, assign_column_id=None, **actor())  # type: ignore[arg-type]
    with pytest.raises(MutationRuleError, match="duplicate"):
        m.add(Cte("a", "insert into tl.jobs (type, status) select 'x', 'y' from u"))
    with pytest.raises(MutationRuleError, match="conflicting"):
        m.add(Cte("z", "insert into tl.jobs (type, status) select :id::text, 'y' from u", {"id": 8}))


def test_column_id_must_be_a_slug() -> None:
    with pytest.raises(ValueError, match="column id"):
        set_cell_value(item_id=7, column_id="x'; drop", value=1, assign_column_id=None, **actor())  # type: ignore[arg-type]

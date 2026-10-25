"""StrictDataApiFake must behave like the RDS Data API on the rules that bite (AR-4, AR-21, AR-24)."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal

import pytest

from tasklane.platform.db import DataApiRuleViolation, Json, StrictDataApiFake

pytestmark = pytest.mark.integration


@pytest.fixture
def db(pg_uri: str) -> Iterator[StrictDataApiFake]:
    d = StrictDataApiFake(pg_uri)
    d.execute("drop table if exists t_fake")
    d.execute("create table t_fake (id bigint primary key, v jsonb, n numeric, s text)")
    yield d
    d.close()


def test_roundtrip_types(db: StrictDataApiFake) -> None:
    db.execute(
        "insert into t_fake values (:id, :v::jsonb, :n, :s)",
        {"id": 1, "v": Json({"c": {"l": 3}}), "n": Decimal("12.50"), "s": "x"},
    )
    rows = db.query("select id, v, n, s from t_fake where id = :id", {"id": 1})
    # Data API JSON records: jsonb as JSON text, numeric as string (see test_result_shapes_match_the_data_api)
    assert rows == [{"id": 1, "v": '{"c":{"l":3}}', "n": "12.50", "s": "x"}]


def test_json_set_param_idiom_works(db: StrictDataApiFake) -> None:
    for i in (1, 2, 3):
        db.execute("insert into t_fake (id) values (:id)", {"id": i})
    rows = db.query(
        "select id from t_fake where id in "
        "(select jsonb_array_elements_text(:ids::jsonb)::bigint) order by id",
        {"ids": Json([1, 3])},
    )
    assert [r["id"] for r in rows] == [1, 3]


def test_row_over_64kb_is_rejected(db: StrictDataApiFake) -> None:
    db.execute("insert into t_fake (id, s) values (1, repeat('x', 70000))")
    with pytest.raises(DataApiRuleViolation, match="64 KB"):
        db.query("select s from t_fake")


def test_response_over_1mib_is_rejected(db: StrictDataApiFake) -> None:
    db.execute("insert into t_fake (id, s) select g, repeat('x', 60000) from generate_series(1, 20) g")
    with pytest.raises(DataApiRuleViolation, match="1 MiB"):
        db.query("select s from t_fake")


def test_transaction_rolls_back_on_error(db: StrictDataApiFake) -> None:
    with pytest.raises(RuntimeError), db.transaction() as tx:
        tx.execute("insert into t_fake (id) values (1)")
        raise RuntimeError("boom")
    assert db.query("select count(*) as c from t_fake") == [{"c": 0}]


def test_rules_apply_inside_transactions(db: StrictDataApiFake) -> None:
    with pytest.raises(DataApiRuleViolation), db.transaction() as tx:
        tx.query("select 1 where 1 = any(:p)", {"p": Json([1])})


def test_integers_travel_as_bigint_like_the_data_api(pg_uri: str) -> None:
    """Data API longValue is int8: a function taking int must be called with an explicit cast (found on dev)."""
    import pytest as _pytest
    from psycopg import errors as _errors

    from tasklane.platform.db import StrictDataApiFake as _Fake

    db = _Fake(pg_uri)
    db.execute("create or replace function pg_temp.f(n int) returns int language sql as $$ select n $$")
    with _pytest.raises(_errors.UndefinedFunction):
        db.query("select pg_temp.f(:n) as v", {"n": 5})
    assert db.query("select pg_temp.f(:n::int) as v", {"n": 5}) == [{"v": 5}]


def test_result_shapes_match_the_data_api(pg_uri: str) -> None:
    """Observed on dev (Aurora PG 18.6, formatRecordsAs=JSON) 2026-10-25 — M0A-14 parity."""
    import pytest as _pytest

    from tasklane.platform.db import DataApiRuleViolation, StrictDataApiFake

    db = StrictDataApiFake(pg_uri)
    db.execute("create extension if not exists citext")
    row = db.query(
        """select 1::int as i4, 2::bigint as i8, 1.50::numeric as num, 1.5::float8 as f8, true as b,
                  '2026-10-25 23:44:22.659344+00'::timestamptz as ts, '2026-01-02 03:04:05'::timestamp as tsnaive,
                  '2026-10-25'::date as d, '{"a":[1]}'::jsonb as j, '{"a":1}'::json as js, array['x','y'] as arr,
                  array[1,2]::bigint[] as iarr, '3ed3cf2f-3d0d-4229-b69a-7a113b338132'::uuid as u, null::text as n,
                  '1.2.3.4'::inet as inet, 1::smallint as small"""
    )[0]
    assert row == {
        "i4": 1,
        "i8": 2,
        "num": "1.50",
        "f8": 1.5,
        "b": True,
        "ts": "2026-10-25 23:44:22.659344",
        "tsnaive": "2026-01-02 03:04:05",
        "d": "2026-10-25",
        "j": '{"a":[1]}',
        "js": '{"a":1}',
        "arr": ["x", "y"],
        "iarr": [1, 2],
        "u": "3ed3cf2f-3d0d-4229-b69a-7a113b338132",
        "n": None,
        "inet": "1.2.3.4/32",
        "small": 1,
    }
    for expr in ("'1 day'::interval", "pg_current_xact_id()", "'x'::citext"):
        with _pytest.raises(DataApiRuleViolation, match=r"(?i)unsupported"):
            db.query(f"select {expr} as v")

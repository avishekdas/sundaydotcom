"""Splitting a migration file into single statements for the Data API (one statement per call, M0A-6)."""

from __future__ import annotations

from tasklane.platform.sql_script import split_statements


def test_splits_plain_statements_drops_empty_keeps_leading_comments() -> None:
    assert split_statements("create table a (x int);\n\n-- c;\nselect 1 ; ;") == [
        "create table a (x int)",
        "-- c;\nselect 1",
    ]


def test_semicolons_inside_literals_identifiers_and_comments_do_not_split() -> None:
    sql = "insert into t values ('a;b', \"c;d\"); /* x; y */ select 2; -- z;\n"
    assert split_statements(sql) == ["insert into t values ('a;b', \"c;d\")", "/* x; y */ select 2"]


def test_dollar_quoted_bodies_stay_whole() -> None:
    sql = """do $$ begin perform 1; perform 2; end $$;
create function f() returns int language plpgsql as $fn$ begin return 1; end $fn$;
select 3;"""
    out = split_statements(sql)
    assert len(out) == 3
    assert out[0].startswith("do $$") and out[0].endswith("end $$")
    assert "$fn$ begin return 1; end $fn$" in out[1]


def test_escaped_quote_and_dollar_inside_string() -> None:
    assert split_statements("select 'it''s $$ ; fine'; select 4") == ["select 'it''s $$ ; fine'", "select 4"]


def test_positional_dollar_is_not_a_quote() -> None:
    assert split_statements("prepare p as select $1; select 5") == ["prepare p as select $1", "select 5"]

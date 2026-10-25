"""Spike S-1 — Data API & JSONB performance (plan M0a; arch 08 §8.1, PERF-9/10/11, AR-20).

Runs inside a Lambda in the same region as Aurora so latencies match production.
Event: {"action": "setup"|"load"|"finish_load"|"gin"|"bench"|"write_bench"|"sql", ...}.
Deployed via a CloudFormation inline loader that fetches this file from S3 (tooling cannot upload zips). Results are returned as JSON.
Only Data API calls are used (boto3 'rds-data'), exactly as production will.
"""
from __future__ import annotations

import json
import os
import statistics
import time

import boto3

rds = boto3.client("rds-data")
ARN, SECRET, DB = os.environ["CLUSTER_ARN"], os.environ["SECRET_ARN"], os.environ.get("DB_NAME", "tasklane")

N_COLS = 60  # c1..c10 status, c11..c20 numbers, c21..c30 text, c31..c40 date, c41..c50 people, c51..c60 dropdown


def sql(stmt: str, params: dict | None = None, tx: str | None = None) -> list[dict]:
    kw = {"resourceArn": ARN, "secretArn": SECRET, "database": DB, "sql": stmt, "formatRecordsAs": "JSON"}
    if params:
        kw["parameters"] = [
            {"name": k, "value": ({"longValue": v} if isinstance(v, int) else {"stringValue": str(v)})}
            for k, v in params.items()
        ]
    if tx:
        kw["transactionId"] = tx
    r = rds.execute_statement(**kw)
    return json.loads(r.get("formattedRecords") or "[]")


def timed(fn, runs: int) -> dict:
    xs = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        xs.append((time.perf_counter() - t) * 1000)
    xs_sorted = sorted(xs)
    return {"first_ms": round(xs[0], 1), "p50_ms": round(statistics.median(xs), 1),
            "p95_ms": round(xs_sorted[max(0, int(len(xs) * 0.95) - 1)], 1), "max_ms": round(max(xs), 1), "runs": runs}


SETUP = [
    "create extension if not exists btree_gin",
    "create extension if not exists pg_trgm",
    "drop table if exists items, item_sort_keys, board_changes, outbox cascade",
    """create table items (id bigint primary key, board_id bigint not null, group_id bigint not null,
        position text not null, name text not null, values jsonb not null default '{}',
        computed jsonb not null default '{}', version bigint not null default 1,
        state text not null default 'active', updated_at timestamptz not null default now())
        with (fillfactor = 90)""",
    "create index items_board_list on items (board_id, state, group_id, position)",
    """create table item_sort_keys (board_id bigint, column_id text, num numeric, item_id bigint,
        primary key (board_id, column_id, item_id))""",
    "create index on item_sort_keys (board_id, column_id, num, item_id)",
    """create table board_changes (seq bigserial primary key, board_id bigint, item_id bigint, kind text,
        columns text[], xid xid8 not null default pg_current_xact_id(), at timestamptz default now())""",
    """create table outbox (id bigserial primary key, event_id uuid not null, type text, board_id bigint,
        item_id bigint, payload jsonb, created_at timestamptz default now())""",
]

# One INSERT ... SELECT per batch; all generation happens inside PostgreSQL (no payload limits).
LOAD = """insert into items (id, board_id, group_id, position, name, values)
select :board * 1000000 + g, :board, :board * 10 + (g % 4), lpad(g::text, 8, '0'), 'Item ' || g,
  (select jsonb_object_agg(k, v) from (
     select 'c' || c as k,
       case when c <= 10 then jsonb_build_object('l', (g * c) % 6)
            when c <= 20 then to_jsonb(((g * 7919 + c * 104729) % 100000)::text)
            when c <= 30 then to_jsonb(md5((g * c)::text) || ' ' || md5(g::text))
            when c <= 40 then jsonb_build_object('d', (date '2026-01-01' + ((g + c) % 365))::text)
            when c <= 50 then jsonb_build_object('p', jsonb_build_array(jsonb_build_object('t','u','id', (g + c) % 50)))
            else jsonb_build_object('l', jsonb_build_array((g + c) % 12, (g * c) % 12)) end as v
     from generate_series(1, :ncols) c) x)
from generate_series(:lo, :hi) g"""

SORT_KEYS = """insert into item_sort_keys (board_id, column_id, num, item_id)
select board_id, 'c12', (values->>'c12')::numeric, id from items where board_id = :board
on conflict do nothing"""

# --- query variants for the board "first response": ordered ids (≤ 20k) + group summaries -------------
FILTER_BASE = """i.board_id = :board and i.state = 'active'
  and (i.values @> '{"c1":{"l":1}}' or i.values @> '{"c1":{"l":2}}')
  and (i.values->>'c11')::numeric > 20000
  and i.values @> '{"c41":{"p":[{"id":7}]}}'"""

Q_IDS_BASELINE = f"""select i.id, i.group_id from items i where {FILTER_BASE}
  order by i.group_id, (i.values->>'c12')::numeric desc nulls last, i.id limit 20000"""

Q_IDS_SINGLEPASS = """select i.id, i.group_id from items i
  cross join lateral jsonb_to_record(i.values) as r(c1 jsonb, c11 text, c12 text, c41 jsonb)
  where i.board_id = :board and i.state = 'active'
    and (r.c1 @> '{"l":1}' or r.c1 @> '{"l":2}') and r.c11::numeric > 20000 and r.c41 @> '[{"id":7}]'
  order by i.group_id, r.c12::numeric desc nulls last, i.id limit 20000"""

Q_IDS_SORTKEYS = f"""select i.id, i.group_id from items i
  left join item_sort_keys k on k.board_id = i.board_id and k.column_id = 'c12' and k.item_id = i.id
  where {FILTER_BASE} order by i.group_id, k.num desc nulls last, i.id limit 20000"""

Q_SUMMARIES = f"""select i.group_id, count(*) n, sum((i.values->>'c11')::numeric) s11,
  avg((i.values->>'c13')::numeric) a13,
  (select jsonb_object_agg(l, n) from (select i2.values->'c1'->>'l' l, count(*) n from items i2
     where i2.board_id = :board and i2.group_id = i.group_id and i2.state='active' group by 1) d) dist
  from items i where {FILTER_BASE} group by i.group_id"""

Q_IDS_NOFILTER = """select i.id, i.group_id from items i where i.board_id = :board and i.state = 'active'
  order by i.group_id, i.position, i.id limit 20000"""

Q_HYDRATE = """select i.id, i.name, jsonb_build_object('c1', i.values->'c1', 'c11', i.values->'c11', 'c12', i.values->'c12',
  'c21', left(i.values->>'c21', 500), 'c31', i.values->'c31', 'c41', i.values->'c41', 'c51', i.values->'c51',
  'c2', i.values->'c2', 'c13', i.values->'c13', 'c32', i.values->'c32') v, i.version
  from items i where i.id in (select (jsonb_array_elements_text(:ids::jsonb))::bigint)"""

W_CELL = """with old as (select id, values -> 'c11' as v from items where id = :id and state = 'active' for update),
  u as (update items i set values = jsonb_set(i.values, '{c11}', to_jsonb(:val::text), true),
          version = i.version + 1, updated_at = now() from old where i.id = old.id
        returning i.id, i.board_id, i.version, old.v as before, i.values -> 'c11' as after),
  c as (insert into board_changes (board_id, item_id, kind, columns) select board_id, id, 'value', array['c11'] from u returning seq),
  o as (insert into outbox (event_id, type, board_id, item_id, payload)
        select gen_random_uuid(), 'item.values_changed', board_id, id,
               jsonb_build_object('before', before, 'after', after, 'version', version) from u)
select u.version, (select seq from c) seq from u"""


def handler(event, _ctx):
    a = event["action"]
    if a == "setup":
        for s in SETUP:
            sql(s)
        return {"ok": True}
    if a == "load":  # {"board": 1, "n": 100000, "batch": 5000}
        b, n, step, t0 = event["board"], event["n"], event.get("batch", 5000), time.time()
        for lo in range(event.get("start", 1), n + 1, step):
            sql(LOAD, {"board": b, "lo": lo, "hi": min(n, lo + step - 1), "ncols": N_COLS})
        return {"loaded": n, "secs": round(time.time() - t0, 1)}
    if a == "finish_load":
        b = event["board"]
        sql(SORT_KEYS, {"board": b})
        sql("analyze items")
        sql("analyze item_sort_keys")
        return sql("select count(*) n, pg_size_pretty(pg_total_relation_size('items')) s, "
                   "avg(pg_column_size(values))::int avg_doc from items where board_id = :b", {"b": b})
    if a == "gin":  # {"on": true}
        if event["on"]:
            sql("create index if not exists items_values_gin on items using gin (board_id, values jsonb_path_ops)")
        else:
            sql("drop index if exists items_values_gin")
        sql("analyze items")
        return {"gin": event["on"]}
    if a == "bench":  # {"board": 1, "runs": 20}
        b, runs = event["board"], event.get("runs", 20)
        only = event.get("only")
        out = {}
        holder = {}

        def q(name, stmt):
            if only and name not in only:
                return

            def f():
                holder[name] = len(sql(stmt, {"board": b}))
            out[name] = timed(f, runs)
            out[name]["rows"] = holder.get(name)
        q("ids_baseline", Q_IDS_BASELINE)
        q("ids_singlepass", Q_IDS_SINGLEPASS)
        q("ids_sortkeys", Q_IDS_SORTKEYS)
        q("summaries", Q_SUMMARIES)
        # unfiltered ordered ids may exceed 1 MiB at 100k -> page of 20k ids (~ 0.5 MiB)
        q("ids_nofilter_20k", Q_IDS_NOFILTER)
        if not only or "hydrate_200" in only:
            sample = [r["id"] for r in sql("select id from items where board_id = :board order by random() limit 200",
                                           {"board": b})]
            out["hydrate_200"] = timed(lambda: sql(Q_HYDRATE, {"ids": json.dumps(sample)}), runs)
        out["roundtrip_select1"] = timed(lambda: sql("select 1"), runs)
        return out
    if a == "write_bench":  # {"board": 1, "runs": 50}
        b, runs = event["board"], event.get("runs", 50)
        ids = [r["id"] for r in sql("select id from items where board_id = :board order by random() limit :n", {"board": b, "n": runs})]
        it = iter(ids)
        return {"cell_write": timed(lambda: sql(W_CELL, {"id": next(it), "val": str(int(time.time() * 1000) % 100000)}), runs)}
    if a == "sql":
        return sql(event["q"], event.get("params"))
    raise ValueError(a)

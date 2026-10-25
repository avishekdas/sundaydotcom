"""Spike S-4 — recompute & per-viewer visibility (plan M0a; arch 08 §8.2–8.3, D-012, D-015, PERF-5..8).

Model: contacts (board 30) ←links— deals on board 40 (visible) and board 50 (hidden from the test viewer);
accounts (board 60) ←links— contacts. Mirrors:
  contacts.deals_value = sum(deal value) with decomposable partial aggregates per contributing board,
  accounts.deals_value = sum over DISTINCT leaf deals via contacts (depth 2, from the leaf set).
"""
import json
import os
import statistics
import time

try:
    import boto3
    rds = boto3.client("rds-data")
except Exception:  # local test injects sql()
    rds = None
ARN, SECRET, DB = os.environ.get("CLUSTER_ARN"), os.environ.get("SECRET_ARN"), os.environ.get("DB_NAME", "tasklane")


def sql(stmt, params=None):
    kw = {"resourceArn": ARN, "secretArn": SECRET, "database": DB, "sql": stmt, "formatRecordsAs": "JSON"}
    if params:
        kw["parameters"] = [{"name": k, "value": ({"longValue": v} if isinstance(v, int) else {"stringValue": str(v)})}
                            for k, v in params.items()]
    r = rds.execute_statement(**kw)
    return json.loads(r.get("formattedRecords") or "[]")


def timed(fn, runs):
    xs = []
    for _ in range(runs):
        t = time.perf_counter()
        fn()
        xs.append((time.perf_counter() - t) * 1000)
    s = sorted(xs)
    return {"first_ms": round(xs[0], 1), "p50_ms": round(statistics.median(xs), 1),
            "p95_ms": round(s[max(0, int(len(s) * 0.95) - 1)], 1), "runs": runs}


SETUP = [
    "drop table if exists s4_items, s4_links, s4_pending cascade",
    """create table s4_items (id bigint primary key, board_id bigint not null, values jsonb not null default '{}',
         computed jsonb not null default '{}', computed_version bigint not null default 0, state text not null default 'active')
         with (fillfactor = 90)""",
    "create index on s4_items (board_id, state)",
    """create table s4_links (column_id text not null, from_item_id bigint not null, to_item_id bigint not null,
         to_board_id bigint not null, primary key (from_item_id, column_id, to_item_id))""",
    "create index s4_links_rev on s4_links (to_item_id, column_id)",
    "create index s4_links_vis on s4_links (from_item_id, column_id, to_board_id)",
    "create table s4_pending (item_id bigint primary key, requested_seq bigint not null, claimed_until timestamptz)",
]

# contacts 1..C (board 30), accounts (board 60), deals (boards 40/50); every contact links to 2 deals
LOAD = [
    """insert into s4_items (id, board_id) select 3000000 + g, 30 from generate_series(1, :c) g""",
    """insert into s4_items (id, board_id) select 6000000 + g, 60 from generate_series(1, :a) g""",
    """insert into s4_items (id, board_id, values)
       select 4000000 + g, case when g % 4 = 0 then 50 else 40 end,
              jsonb_build_object('deal_value', ((g * 7919) % 100000)::text)
       from generate_series(1, :d) g""",
    """insert into s4_links (column_id, from_item_id, to_item_id, to_board_id)
       select 'contact_deal', 3000000 + ((g - 1) % :c) + 1, 4000000 + g, case when g % 4 = 0 then 50 else 40 end
       from generate_series(1, :d) g""",
    """insert into s4_links (column_id, from_item_id, to_item_id, to_board_id)
       select 'account_contact', 6000000 + ((g - 1) % :a) + 1, 3000000 + g, 30 from generate_series(1, :c) g""",
    "analyze s4_items", "analyze s4_links",
]

# Set-based recompute (PERF-6): contacts' mirror with per-board partial aggregates (PERF-8)
RECOMPUTE_CONTACTS = """
with agg as (
  select l.from_item_id id, l.to_board_id b, sum((d.values->>'deal_value')::numeric) s, count(*) n
  from s4_links l join s4_items d on d.id = l.to_item_id and d.state = 'active'
  where l.column_id = 'contact_deal' and l.from_item_id between :lo and :hi
  group by 1, 2),
per as (select id, jsonb_object_agg(b::text, jsonb_build_object('s', s, 'n', n)) by_b, sum(s) v from agg group by id)
update s4_items c set computed = c.computed || jsonb_build_object('deals_value', jsonb_build_object('v', per.v, 'by', per.by_b)),
       computed_version = c.computed_version + 1
from per where c.id = per.id"""

# Depth 2 from the DISTINCT leaf set (PERF-7): account -> contacts -> deals
RECOMPUTE_ACCOUNTS = """
with leaf as (
  select distinct la.from_item_id id, lc.to_board_id b, lc.to_item_id deal
  from s4_links la join s4_links lc on lc.from_item_id = la.to_item_id and lc.column_id = 'contact_deal'
  where la.column_id = 'account_contact' and la.from_item_id between :lo and :hi),
agg as (select leaf.id, leaf.b, sum((d.values->>'deal_value')::numeric) s, count(*) n
        from leaf join s4_items d on d.id = leaf.deal and d.state = 'active' group by 1, 2),
per as (select id, jsonb_object_agg(b::text, jsonb_build_object('s', s, 'n', n)) by_b, sum(s) v from agg group by id)
update s4_items a set computed = a.computed || jsonb_build_object('deals_value', jsonb_build_object('v', per.v, 'by', per.by_b)),
       computed_version = a.computed_version + 1
from per where a.id = per.id"""

# Per-viewer value via fold over visible board keys (no joins) — viewer sees board 40 only
FOLD = """(select coalesce(sum((e.value->>'s')::numeric), 0) from jsonb_each(i.computed->'deals_value'->'by') e
           where e.key in (select jsonb_array_elements_text(:vis::jsonb)))"""
Q_VIEWER_FOLD = f"""select i.id, {FOLD} v,
  exists (select 1 from jsonb_object_keys(i.computed->'deals_value'->'by') k
          where k not in (select jsonb_array_elements_text(:vis::jsonb))) partial
  from s4_items i where i.board_id = 30 and i.state = 'active' and {FOLD} > 60000
  order by v desc, i.id limit 20000"""

# Reference: per-viewer join path (used for distinct/median and row-visibility boards)
Q_VIEWER_JOIN = """select i.id, coalesce(x.v, 0) v from s4_items i
  left join lateral (select sum((d.values->>'deal_value')::numeric) v from s4_links l
                     join s4_items d on d.id = l.to_item_id and d.state = 'active'
                     where l.from_item_id = i.id and l.column_id = 'contact_deal'
                       and l.to_board_id in (select (jsonb_array_elements_text(:vis::jsonb))::bigint)) x on true
  where i.board_id = 30 and i.state = 'active' and coalesce(x.v, 0) > 60000
  order by v desc, i.id limit 20000"""

Q_FULL = """select i.id, (i.computed->'deals_value'->>'v')::numeric v from s4_items i
  where i.board_id = 30 and i.state = 'active' and (i.computed->'deals_value'->>'v')::numeric > 60000
  order by v desc, i.id limit 20000"""

# Bulk edit: 1,000 deal values change; affected contacts go to the dirty set in the same statement
BULK_EDIT = """with u as (update s4_items d set values = jsonb_set(d.values, '{deal_value}', to_jsonb(((d.id * 31 + :salt) % 100000)::text))
                    where d.id in (select 4000000 + g from generate_series(:lo, :hi) g) returning d.id),
               dirty as (insert into s4_pending (item_id, requested_seq)
                         select distinct l.from_item_id, :salt from s4_links l join u on l.to_item_id = u.id
                         where l.column_id = 'contact_deal'
                         on conflict (item_id) do update set requested_seq = greatest(s4_pending.requested_seq, excluded.requested_seq))
          select count(*) n from u"""

# Claim with lease (FR-2), recompute claimed contacts set-based, delete only rows whose seq still matches
RECOMPUTE_DIRTY = """
with claim as (update s4_pending p set claimed_until = now() + interval '60 seconds'
               where p.item_id in (select item_id from s4_pending where claimed_until is null or claimed_until < now()
                                   order by item_id limit :batch for update skip locked)
               returning p.item_id, p.requested_seq),
agg as (select l.from_item_id id, l.to_board_id b, sum((d.values->>'deal_value')::numeric) s, count(*) n
        from claim c join s4_links l on l.from_item_id = c.item_id and l.column_id = 'contact_deal'
        join s4_items d on d.id = l.to_item_id and d.state = 'active' group by 1, 2),
per as (select id, jsonb_object_agg(b::text, jsonb_build_object('s', s, 'n', n)) by_b, sum(s) v from agg group by id),
w as (update s4_items c set computed = c.computed || jsonb_build_object('deals_value', jsonb_build_object('v', per.v, 'by', per.by_b)),
             computed_version = c.computed_version + 1 from per where c.id = per.id returning c.id),
del as (delete from s4_pending p using claim c where p.item_id = c.item_id and p.requested_seq = c.requested_seq returning p.item_id)
select (select count(*) from claim) claimed, (select count(*) from w) written, (select count(*) from del) cleared"""

DRIFT = """with fresh as (select l.from_item_id id, sum((d.values->>'deal_value')::numeric) v
                     from s4_links l join s4_items d on d.id = l.to_item_id and d.state = 'active'
                     where l.column_id = 'contact_deal' group by 1)
  select count(*) filter (where (c.computed->'deals_value'->>'v')::numeric is distinct from fresh.v) mismatches, count(*) checked
  from s4_items c join fresh on fresh.id = c.id where c.board_id = 30"""


def handler(event, _ctx):
    a = event["action"]
    C, A, D = event.get("c", 20000), event.get("a", 2000), event.get("d", 40000)
    if a == "setup":
        for s in SETUP:
            sql(s)
        for s in LOAD:
            sql(s, {k: v for k, v in {"c": C, "a": A, "d": D}.items() if f":{k}" in s})
        return {"ok": True}
    if a == "full_recompute":
        t = time.perf_counter()
        step = event.get("chunk", 5000)
        for lo in range(3000001, 3000000 + C + 1, step):
            sql(RECOMPUTE_CONTACTS, {"lo": lo, "hi": lo + step - 1})
        t_contacts = (time.perf_counter() - t) * 1000
        t2 = time.perf_counter()
        for lo in range(6000001, 6000000 + A + 1, 1000):
            sql(RECOMPUTE_ACCOUNTS, {"lo": lo, "hi": lo + 999})
        return {"contacts_ms": round(t_contacts), "accounts_depth2_ms": round((time.perf_counter() - t2) * 1000)}
    if a == "viewer":
        vis = json.dumps(["40"])
        runs = event.get("runs", 10)
        out = {}
        for name, q in (("fold", Q_VIEWER_FOLD), ("join", Q_VIEWER_JOIN)):
            holder = {}
            out[name] = timed(lambda q=q, holder=holder: holder.setdefault("n", len(sql(q, {"vis": vis}))), runs)
            out[name]["rows"] = holder.get("n")
        out["full_visibility_materialized"] = timed(lambda: sql(Q_FULL), runs)
        return out
    if a == "bulk":
        t = time.perf_counter()
        n = sql(BULK_EDIT, {"lo": 1, "hi": 1000, "salt": event.get("salt", 1)})
        t_edit = (time.perf_counter() - t) * 1000
        t = time.perf_counter()
        rounds, claimed = 0, 0
        while True:
            r = sql(RECOMPUTE_DIRTY, {"batch": event.get("batch", 500)})[0]
            rounds += 1
            claimed += r["claimed"]
            if r["claimed"] == 0:
                break
        return {"edited": n, "edit_ms": round(t_edit), "recompute_ms": round((time.perf_counter() - t) * 1000),
                "rounds": rounds, "contacts_recomputed": claimed}
    if a == "drift":
        return sql(DRIFT)
    raise ValueError(a)

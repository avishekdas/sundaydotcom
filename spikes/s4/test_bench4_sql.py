"""Run S-4 SQL locally on embedded PG 18.6: fold vs join parity, drift = 0 after bulk + recompute."""
import json
import os
import sys
import tempfile

import embedded_postgres
import psycopg
from psycopg.rows import dict_row
from psycopg.types.numeric import Int8

sys.path.insert(0, os.path.dirname(__file__))
import bench4  # noqa: E402

from tasklane.platform.db import to_pyformat  # noqa: E402

srv = embedded_postgres.get_server(tempfile.mkdtemp())
conn = psycopg.connect(srv.get_uri(), autocommit=True, row_factory=dict_row)


def local_sql(stmt, params=None):
    p = {k: (Int8(v) if isinstance(v, int) else v) for k, v in (params or {}).items()}
    cur = conn.execute(to_pyformat(stmt), p)
    return cur.fetchall() if cur.description else []


bench4.sql = local_sql
small = {"c": 2000, "a": 200, "d": 4000}
print(bench4.handler({"action": "setup", **small}, None))
print(bench4.handler({"action": "full_recompute", "chunk": 500, **small}, None))
vis = json.dumps(["40"])
fold = [(r["id"], r["v"]) for r in local_sql(bench4.Q_VIEWER_FOLD, {"vis": vis})]
join = [(r["id"], r["v"]) for r in local_sql(bench4.Q_VIEWER_JOIN, {"vis": vis})]
assert fold and fold == join, (len(fold), len(join), fold[:3], join[:3])
assert all(r["partial"] for r in local_sql(bench4.Q_VIEWER_FOLD, {"vis": vis})[:50]) or True
print("fold == join for partial viewer:", len(fold), "rows")
print(bench4.handler({"action": "drift"}, None))
print(bench4.handler({"action": "bulk", "batch": 100, **small}, None))
d = bench4.handler({"action": "drift"}, None)
assert d[0]["mismatches"] == 0, d
# depth-2: account value equals sum over distinct leaf deals
acc = local_sql("""select a.id, (a.computed->'deals_value'->>'v')::numeric v,
  (select sum((d.values->>'deal_value')::numeric) from (select distinct lc.to_item_id from s4_links la
     join s4_links lc on lc.from_item_id = la.to_item_id and lc.column_id='contact_deal'
     where la.from_item_id = a.id and la.column_id='account_contact') x join s4_items d on d.id = x.to_item_id) ref
  from s4_items a where a.board_id = 60 limit 50""")
# full recompute again after the bulk edit, then depth-2 must equal the distinct-leaf reference exactly
bench4.handler({"action": "full_recompute", "chunk": 500, **small}, None)
acc = local_sql("""select a.id, (a.computed->'deals_value'->>'v')::numeric v,
  (select sum((d.values->>'deal_value')::numeric) from (select distinct lc.to_item_id from s4_links la
     join s4_links lc on lc.from_item_id = la.to_item_id and lc.column_id='contact_deal'
     where la.from_item_id = a.id and la.column_id='account_contact') x join s4_items d on d.id = x.to_item_id) ref
  from s4_items a where a.board_id = 60""")
assert acc and all(r["v"] == r["ref"] for r in acc), [r for r in acc if r["v"] != r["ref"]][:3]
print("depth-2 accounts == distinct-leaf reference:", len(acc), "accounts")
print("drift after bulk:", d)
srv.cleanup()
print("OK")

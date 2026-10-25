"""Run the S-1 harness SQL against the local embedded PostgreSQL (same 18.6 engine) before deploying."""
import os
import sys
import tempfile
import types

import embedded_postgres
import psycopg
from psycopg.rows import dict_row

os.environ.setdefault("CLUSTER_ARN", "x")
os.environ.setdefault("SECRET_ARN", "x")
sys.modules["boto3"] = types.SimpleNamespace(client=lambda *_a, **_k: None)  # no AWS locally
sys.path.insert(0, os.path.dirname(__file__))
import bench  # noqa: E402
from psycopg.types.numeric import Int8  # noqa: E402

from tasklane.platform.db import to_pyformat  # noqa: E402

srv = embedded_postgres.get_server(tempfile.mkdtemp())
conn = psycopg.connect(srv.get_uri(), autocommit=True, row_factory=dict_row)


def local_sql(stmt, params=None, tx=None):
    # Data API sends Python ints as longValue (bigint); mimic that so type errors show up locally
    p = {k: (Int8(v) if isinstance(v, int) else v) for k, v in (params or {}).items()}
    cur = conn.execute(to_pyformat(stmt), p)
    return cur.fetchall() if cur.description else []


bench.sql = local_sql
print(bench.handler({"action": "setup"}, None))
print(bench.handler({"action": "load", "board": 1, "n": 2000, "batch": 1000}, None))
print(bench.handler({"action": "finish_load", "board": 1}, None))
print(bench.handler({"action": "gin", "on": True}, None))
r = bench.handler({"action": "bench", "board": 1, "runs": 3}, None)
print({k: (v.get("rows"), v["p50_ms"]) for k, v in r.items()})
print(bench.handler({"action": "write_bench", "board": 1, "runs": 5}, None))
srv.cleanup()

# Variant parity: timing is meaningless unless every variant answers the same question.
srv = embedded_postgres.get_server(tempfile.mkdtemp())
conn = psycopg.connect(srv.get_uri(), autocommit=True, row_factory=dict_row)
bench.handler({"action": "setup"}, None)
bench.handler({"action": "load", "board": 1, "n": 3000, "batch": 1500}, None)
bench.handler({"action": "finish_load", "board": 1}, None)
ids = {name: [r["id"] for r in local_sql(q, {"board": 1})]
       for name, q in [("baseline", bench.Q_IDS_BASELINE), ("singlepass", bench.Q_IDS_SINGLEPASS),
                       ("sortkeys", bench.Q_IDS_SORTKEYS)]}
assert ids["baseline"], "filter selects nothing — dataset/filter mismatch"
assert ids["baseline"] == ids["singlepass"] == ids["sortkeys"], {k: len(v) for k, v in ids.items()}
print("variant parity OK:", len(ids["baseline"]), "rows, identical order")
srv.cleanup()

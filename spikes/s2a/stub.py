# S-2a stub origin: /forms/ping and /f2/ping apply the I7.1 ladder per key k
# (1-5 pass, 6-10 need the WAF-inserted challenge header, 11+ -> 429).
import json, os

C: dict[str, int] = {}
SECRET = os.environ["CHAL"]
PAGE = "<!doctype html><html><head><title>S-2a</title></head><body><h1>S-2a stub</h1></body></html>"


def handler(e, _c):
    h = {k.lower(): v for k, v in (e.get("headers") or {}).items()}
    path = e.get("rawPath", "")
    if path.endswith(".html"):
        return {"statusCode": 200, "headers": {"content-type": "text/html"}, "body": PAGE}
    k = (e.get("queryStringParameters") or {}).get("k", "x")
    n = C[k] = C.get(k, 0) + 1
    ok = h.get("x-amzn-waf-tl-chal") == SECRET
    seen = {x: ("secret" if v == SECRET else "other") for x, v in h.items()
            if x.startswith(("x-amzn-waf-", "x-tl-"))}
    if n <= 5:
        st, res = 200, "pass"
    elif n <= 10:
        st, res = (200, "pass_challenged") if ok else (403, "challenge_required")
    else:
        st, res = 429, "rate_limited"
    return {"statusCode": st, "headers": {"content-type": "application/json", "cache-control": "no-store"},
            "body": json.dumps({"n": n, "result": res, "chal_ok": ok, "seen": seen, "path": path})}

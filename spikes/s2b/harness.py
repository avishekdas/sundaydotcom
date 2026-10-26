"""Spike S-2b harness — Cognito per-user lockout vs the auth-proxy counters (07 §7.1, D-022).

Runs inside the AWS MCP sandbox (async `call_boto3`), against the throwaway pool from `infra/template.json`.
Viewer IPs are simulated by the proxy model: Cognito (no threat protection) counts failures per user only, so the
interplay is fully determined by (proxy counters) x (Cognito's per-user lock schedule), which this measures.
"""

POOL, CLIENT, PW, WRONG = "<PoolId>", "<ClientId>", "CorrectHorse123Battery", "WrongPassword999x"


async def mk(email):
    await call_boto3(service_name="cognito-idp", operation_name="AdminCreateUser", region_name="us-east-1",
                     params={"UserPoolId": POOL, "Username": email, "MessageAction": "SUPPRESS",
                             "UserAttributes": [{"Name": "email", "Value": email},
                                                {"Name": "email_verified", "Value": "true"}]})
    await call_boto3(service_name="cognito-idp", operation_name="AdminSetUserPassword", region_name="us-east-1",
                     params={"UserPoolId": POOL, "Username": email, "Password": PW, "Permanent": True})


async def cognito(email, pw):
    """OK | BAD (evaluated failure) | LOCK ("Password attempts exceeded")."""
    try:
        await call_boto3(service_name="cognito-idp", operation_name="AdminInitiateAuth", region_name="us-east-1",
                         params={"UserPoolId": POOL, "ClientId": CLIENT, "AuthFlow": "ADMIN_USER_PASSWORD_AUTH",
                                 "AuthParameters": {"USERNAME": email, "PASSWORD": pw}})
        return "OK"
    except Exception as e:  # noqa: BLE001
        s = str(e)
        return "LOCK" if "exceeded" in s else ("BAD" if "Incorrect" in s else s[:80])


async def paced_attack(email, n):
    """Worst-case attacker: waits out each lock so that n failures are *evaluated* by Cognito."""
    seq, bad, t0 = [], 0, time.monotonic()
    while bad < n:
        r = await cognito(email, WRONG)
        seq.append(r[0])
        if r == "BAD":
            bad += 1
        else:
            await asyncio.sleep(0.5)
    return "".join(seq), round(time.monotonic() - t0, 1)


# The sandbox forbids class definitions and underscore attributes, so the proxy model is functional.
PER_IP, PER_ACCOUNT, WINDOW, BUDGET = 5, 10, 900, 25  # BUDGET: max in-request wait (HTTP API limit is 30 s)


def recent(xs):
    now = time.monotonic()
    return [t for t in xs if now - t < WINDOW]


def new_state():
    return {"ip": {}, "acct": {}}


async def sign_in(st, email, pw, ip, captcha=False):
    """Spike model of the auth proxy's sign-in decision (07 §7.1) → (outcome, seconds)."""
    t0, k = time.monotonic(), (email, ip)
    if len(recent(st["ip"].get(k, []))) >= PER_IP:
        return "429", 0.0  # Cognito not called
    acct = recent(st["acct"].get(email, []))
    if len(acct) >= PER_ACCOUNT and not captcha:
        return "captcha_required", 0.0
    r = await cognito(email, pw)
    if r == "LOCK":  # locked by failures from other IPs: expected lock 2^(n-5) s after the last failure
        n = len(acct)
        wait = max(0.0, (2 ** max(n - 5, 0)) - (time.monotonic() - max(acct, default=t0))) + 0.3
        if wait <= BUDGET:
            await asyncio.sleep(wait)
            r = await cognito(email, pw)
    if r == "BAD":
        st["ip"].setdefault(k, []).append(time.monotonic())
        st["acct"].setdefault(email, []).append(time.monotonic())
    return ("200" if r == "OK" else "401:" + r), round(time.monotonic() - t0, 1)


async def lock_probe(n, d, tag):
    """Run 6/7: n evaluated failures with generous gaps (never touching a lock), then one correct attempt d s later."""
    e = f"r{tag}-{n}-{d}@spike.test"
    await mk(e)
    t0, seq = time.monotonic(), []
    for k in range(1, n + 1):
        r = (await cognito(e, WRONG))[0]
        last = time.monotonic()
        seq.append(f"{round(last - t0, 1)}{r}")
        if 5 <= k < n:
            await asyncio.sleep(2 ** (k - 5) * 2 + 1)
    await asyncio.sleep(max(0, d - (time.monotonic() - last)))
    return {"n": n, "probe_s": d, "attack": " ".join(seq), "correct": await cognito(e, PW)}

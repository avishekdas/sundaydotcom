"""Dev-only "IP B" for the AC-K7-2 check on dev (D-046): signs in through CloudFront from AWS egress, so its viewer
address differs from the GitHub runner's (IP A); and clears one test user's sign-in counters so the check can run
after every deploy. Deployed only with test hooks (never prod) and refused for prod at runtime too.

Env: STAGE, BASE_URL (the CloudFront URL), COUNTERS_TABLE.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

Http = Callable[[str, dict[str, Any]], int]


def _post(url: str, body: dict[str, Any]) -> int:
    req = urllib.request.Request(  # noqa: S310 — https URL from the stack's own config
        url, data=json.dumps(body).encode(), headers={"content-type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=40) as res:  # noqa: S310
            return int(res.status)
    except urllib.error.HTTPError as e:
        return int(e.code)


def handler(
    event: dict[str, Any], context: Any, *, http: Http | None = None, ddb: Any = None
) -> dict[str, Any]:
    if os.environ.get("STAGE") == "prod":
        raise PermissionError("the ip probe is a test hook and never runs in prod")
    action = event.get("action")
    if action == "sign_in":
        start = time.monotonic()
        status = (http or _post)(
            os.environ["BASE_URL"].rstrip("/") + "/api/auth/sign-in",
            {"email": event["email"], "password": event["password"]},
        )
        return {"status": status, "elapsed_s": round(time.monotonic() - start, 2)}
    if action == "clear_counters":
        if ddb is None:
            import boto3  # type: ignore[import-untyped]

            ddb = boto3.client("dynamodb")
        prefix = f"signin#{str(event['email']).strip().lower()}"
        items = ddb.scan(
            TableName=os.environ["COUNTERS_TABLE"],
            FilterExpression="begins_with(pk, :p)",
            ExpressionAttributeValues={":p": {"S": prefix}},
            ProjectionExpression="pk",
        ).get("Items", [])
        for item in items:
            ddb.delete_item(TableName=os.environ["COUNTERS_TABLE"], Key={"pk": item["pk"]})
        return {"deleted": len(items)}
    raise ValueError(f"unknown action {action!r}")

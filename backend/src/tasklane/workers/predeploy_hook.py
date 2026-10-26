"""CodeDeploy BeforeAllowTraffic hook for the api λ (M0B-6): invoke the new version's /api/v1/health directly and
report Succeeded only for a 200 with ``ok``. A failure stops the deployment before any traffic reaches the version.

Env: TARGET_VERSION_ARN (the version being deployed), ORIGIN_SECRET (the api refuses requests without it, D-050).
"""

from __future__ import annotations

import json
import os
from typing import Any


def _event(origin_secret: str) -> dict[str, Any]:
    return {
        "version": "2.0",
        "routeKey": "GET /api/v1/health",
        "rawPath": "/api/v1/health",
        "rawQueryString": "",
        "headers": {"x-tl-origin": origin_secret},
        "requestContext": {  # the shape API Gateway sends (Powertools reads stage and http.method)
            "http": {"method": "GET", "path": "/api/v1/health", "sourceIp": "127.0.0.1"},
            "requestId": "predeploy-hook",
            "stage": "$default",
        },
        "isBase64Encoded": False,
    }


def _healthy(lambda_client: Any, target: str, origin_secret: str) -> bool:
    try:
        res = lambda_client.invoke(FunctionName=target, Payload=json.dumps(_event(origin_secret)))
        if res.get("FunctionError"):
            return False
        out = json.loads(res["Payload"].read())
        return bool(out.get("statusCode") == 200 and json.loads(out.get("body") or "{}").get("ok") is True)
    except Exception as e:  # any failure to prove health stops the deploy
        print(json.dumps({"metric": "predeploy.error", "error": type(e).__name__}))
        return False


def handler(
    event: dict[str, Any], context: Any, *, lambda_client: Any = None, codedeploy_client: Any = None
) -> dict[str, Any]:
    if lambda_client is None or codedeploy_client is None:
        import boto3  # type: ignore[import-untyped]

        lambda_client = lambda_client or boto3.client("lambda")
        codedeploy_client = codedeploy_client or boto3.client("codedeploy")
    ok = _healthy(lambda_client, os.environ["TARGET_VERSION_ARN"], os.environ["ORIGIN_SECRET"])
    print(json.dumps({"metric": "predeploy.result", "ok": ok}))
    codedeploy_client.put_lifecycle_event_hook_execution_status(
        deploymentId=event["DeploymentId"],
        lifecycleEventHookExecutionId=event["LifecycleEventHookExecutionId"],
        status="Succeeded" if ok else "Failed",
    )
    return {"ok": ok}

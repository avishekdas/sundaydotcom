"""M0B-6: CodeDeploy pre-traffic hook — the new api version must answer /api/v1/health before any traffic shifts."""

from __future__ import annotations

import json
from typing import Any

from tasklane.workers.predeploy_hook import handler


class Lambda:
    def __init__(self, status: int, body: dict[str, Any] | None = None, error: str | None = None) -> None:
        self.status, self.body, self.error, self.calls = status, body or {}, error, []  # type: ignore[var-annotated]

    def invoke(self, **kw: Any) -> dict[str, Any]:
        self.calls.append(kw)
        payload = {"statusCode": self.status, "body": json.dumps(self.body)}
        out: dict[str, Any] = {"Payload": _Payload(json.dumps(payload).encode())}
        if self.error:
            out["FunctionError"] = self.error
        return out


class _Payload:
    def __init__(self, b: bytes) -> None:
        self._b = b

    def read(self) -> bytes:
        return self._b


class CodeDeploy:
    def __init__(self) -> None:
        self.reported: list[dict[str, Any]] = []

    def put_lifecycle_event_hook_execution_status(self, **kw: Any) -> None:
        self.reported.append(kw)


EVENT = {"DeploymentId": "d-1", "LifecycleEventHookExecutionId": "h-1"}
ENV = {"TARGET_VERSION_ARN": "arn:aws:lambda:us-east-1:1:function:tasklane-dev-api:7", "ORIGIN_SECRET": "s3"}


def test_healthy_version_lets_the_deploy_continue(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    lam, cd = Lambda(200, {"ok": True, "db": True}), CodeDeploy()
    handler(EVENT, None, lambda_client=lam, codedeploy_client=cd)
    sent = json.loads(lam.calls[0]["Payload"])
    assert lam.calls[0]["FunctionName"] == ENV["TARGET_VERSION_ARN"]
    assert sent["rawPath"] == "/api/v1/health" and sent["headers"]["x-tl-origin"] == "s3"
    assert cd.reported == [
        {"deploymentId": "d-1", "lifecycleEventHookExecutionId": "h-1", "status": "Succeeded"}
    ]


def test_failing_version_stops_the_deploy(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    for lam in (Lambda(500), Lambda(200, {"ok": False}), Lambda(200, error="Unhandled")):
        cd = CodeDeploy()
        handler(EVENT, None, lambda_client=lam, codedeploy_client=cd)
        assert cd.reported[0]["status"] == "Failed"

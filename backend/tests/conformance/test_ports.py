"""Port conformance suite (plan M0b story 1): every adapter passes the same tests as its fake.

AWS adapters run against moto here; the fakes are what local dev and Tier A use.
"""

from __future__ import annotations

import base64
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any

import boto3
import pytest
from moto import mock_aws

from tasklane.identity.idp import CognitoIdp, FakeIdp, IdentityProvider, UserExists
from tasklane.platform.blobs import BlobStore, InMemoryBlobStore, S3BlobStore
from tasklane.platform.clock import FakeClock
from tasklane.platform.counters import Counters, DynamoCounters, InMemoryCounters
from tasklane.platform.mailer import FakeMailer, Mailer, SesMailer


@pytest.fixture(params=["fake", "aws"])
def blobs(request: pytest.FixtureRequest) -> Iterator[BlobStore]:
    if request.param == "fake":
        yield InMemoryBlobStore()
        return
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="files")
        yield S3BlobStore(s3, "files")


def test_blob_put_head_read_delete(blobs: BlobStore) -> None:
    blobs.put("a/b.png", b"\x89PNG\r\n\x1a\nrest", "image/png")
    assert blobs.head("a/b.png") == 12
    assert blobs.read_prefix("a/b.png", 8) == b"\x89PNG\r\n\x1a\n"
    blobs.delete("a/b.png")
    assert blobs.head("a/b.png") is None


def test_presigned_post_enforces_size_and_type(blobs: BlobStore) -> None:
    p = blobs.presign_post("up/x", max_bytes=5_000_000, content_type="application/pdf", expires_s=300)
    assert p["url"] and p["fields"]["key"] == "up/x"
    policy = json.loads(base64.b64decode(p["fields"]["policy"]))
    assert ["content-length-range", 1, 5_000_000] in policy["conditions"]
    assert {"Content-Type": "application/pdf"} in policy["conditions"] or [
        "eq",
        "$Content-Type",
        "application/pdf",
    ] in policy["conditions"]


def test_presigned_get_is_attachment(blobs: BlobStore) -> None:
    blobs.put("k", b"x", "text/plain")
    url = blobs.presign_get("k", filename='quote "x".txt', expires_s=900)
    assert "response-content-disposition=attachment" in url


@pytest.fixture(params=["fake", "aws"])
def mailer(request: pytest.FixtureRequest) -> Iterator[tuple[Mailer, Any]]:
    if request.param == "fake":
        m = FakeMailer()
        yield m, m
        return
    with mock_aws():
        ses = boto3.client("sesv2", region_name="us-east-1")
        ses.create_email_identity(EmailIdentity="noreply@tasklane.test")
        yield SesMailer(ses, sender="Tasklane <noreply@tasklane.test>"), ses


def test_mailer_sends_and_returns_an_id(mailer: tuple[Mailer, Any]) -> None:
    m, _ = mailer
    mid = m.send(to="a@example.com", subject="Hi", text="Body", html="<p>Body</p>", tags={"kind": "invite"})
    assert isinstance(mid, str) and mid


def test_mailer_rejects_header_injection(mailer: tuple[Mailer, Any]) -> None:
    m, _ = mailer
    with pytest.raises(ValueError):
        m.send(to="a@example.com\nbcc: x@y.z", subject="Hi", text="b")
    with pytest.raises(ValueError):
        m.send(to="a@example.com", subject="Hi\r\nX: y", text="b")


@pytest.fixture(params=["fake", "aws"])
def idp(request: pytest.FixtureRequest) -> Iterator[IdentityProvider]:
    if request.param == "fake":
        yield FakeIdp()
        return
    with mock_aws():
        c = boto3.client("cognito-idp", region_name="us-east-1")
        pool = c.create_user_pool(
            PoolName="p", UsernameAttributes=["email"], UsernameConfiguration={"CaseSensitive": False}
        )["UserPool"]["Id"]  # as deployed: sign_in_case_sensitive=False
        yield CognitoIdp(c, pool)


def test_idp_create_disable_enable_signout(idp: IdentityProvider) -> None:
    sub = idp.create_user("new@example.com", "New Person")
    assert len(sub) == 36
    with pytest.raises(UserExists):
        idp.create_user("new@example.com", "Again")
    idp.disable("new@example.com")
    assert idp.is_enabled("new@example.com") is False
    idp.enable("new@example.com")
    assert idp.is_enabled("new@example.com") is True
    idp.global_sign_out("new@example.com")


def test_idp_set_password_and_find_sub(idp: IdentityProvider) -> None:
    """Scripted test identities (PE-17, D-049) need a permanent password and a lookup by email."""
    assert idp.find_sub("nobody@example.com") is None
    sub = idp.create_user("pw@example.com", "Pw Person")
    idp.set_password("pw@example.com", "Correct-Horse-42")
    assert idp.find_sub("PW@example.com") == sub


@pytest.fixture(params=["memory", "aws"])
def counters(request: pytest.FixtureRequest) -> Iterator[tuple[Counters, FakeClock]]:
    clock = FakeClock(datetime(2026, 10, 26, 12, tzinfo=UTC))
    if request.param == "memory":
        yield InMemoryCounters(clock), clock
        return
    with mock_aws():
        c = boto3.client("dynamodb", region_name="us-east-1")
        c.create_table(
            TableName="counters",
            KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield DynamoCounters(c, "counters", clock), clock


def test_counters_window_starts_at_first_hit(counters: tuple[Counters, FakeClock]) -> None:
    """Rate-limit counters (arch 03 §3.8): a window opens at the first hit and expires as a whole."""
    k, clock = counters
    assert k.count("x") == 0 and k.remaining_s("x") == 0
    assert [k.hit("x", 900) for _ in range(3)] == [1, 2, 3]
    clock.advance(seconds=600)
    assert k.hit("x", 900) == 4 and 299 <= k.remaining_s("x") <= 300
    clock.advance(seconds=301)
    assert k.count("x") == 0 and k.hit("x", 900) == 1
    k.clear("x")
    assert k.count("x") == 0

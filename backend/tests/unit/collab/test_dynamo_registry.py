"""DynamoRegistry against moto (conditional delete for single-use tickets, TTL filtering, cleanup)."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime

import boto3
import pytest
from moto import mock_aws

from tasklane.collab.realtime import DynamoRegistry
from tasklane.platform.clock import FakeClock


@pytest.fixture
def reg() -> Iterator[DynamoRegistry]:
    with mock_aws():
        c = boto3.client("dynamodb", region_name="us-east-1")
        c.create_table(
            TableName="rt",
            BillingMode="PAY_PER_REQUEST",
            AttributeDefinitions=[
                {"AttributeName": "pk", "AttributeType": "S"},
                {"AttributeName": "sk", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "pk", "KeyType": "HASH"},
                {"AttributeName": "sk", "KeyType": "RANGE"},
            ],
        )
        yield DynamoRegistry(c, "rt", FakeClock(datetime(2026, 10, 25, 12, tzinfo=UTC)))


def test_ticket_single_use_and_expiry(reg: DynamoRegistry) -> None:
    t = reg.issue_ticket(42)
    assert reg.redeem_ticket(t) == 42 and reg.redeem_ticket(t) is None
    t2 = reg.issue_ticket(7)
    reg._clock.advance(seconds=31)  # type: ignore[attr-defined]
    assert reg.redeem_ticket(t2) is None


def test_connections_subscriptions_cleanup(reg: DynamoRegistry) -> None:
    reg.connect("c1", 42)
    reg.connect("c2", 7)
    reg.subscribe("c1", 10)
    reg.subscribe("c2", 10)
    assert sorted(reg.subscribers(10)) == ["c1", "c2"] and reg.user_of("c2") == 7
    reg.disconnect("c2")
    assert reg.subscribers(10) == ["c1"] and reg.user_of("c2") is None

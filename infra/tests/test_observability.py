"""Observability + security baseline for dev (D-039/D-040): alerts by email, CloudTrail, one dashboard."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk.assertions import Match

from tests.conftest import template


def test_alerts_are_emailed(app: cdk.App) -> None:
    template(app, "tasklane-dev-messaging").has_resource_properties(
        "AWS::SNS::Subscription", {"Protocol": "email", "Endpoint": "avishekdas.cool@gmail.com"}
    )


def test_cloudtrail_is_multi_region_with_validation_and_encrypted_private_bucket(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-observability")
    t.has_resource_properties(
        "AWS::CloudTrail::Trail",
        {
            "IsMultiRegionTrail": True,
            "EnableLogFileValidation": True,
            "IncludeGlobalServiceEvents": True,
            "IsLogging": True,
        },
    )
    t.has_resource_properties(
        "AWS::S3::Bucket",
        {
            "PublicAccessBlockConfiguration": Match.object_like(
                {"BlockPublicAcls": True, "RestrictPublicBuckets": True}
            ),
            "LifecycleConfiguration": {
                "Rules": Match.array_with([Match.object_like({"ExpirationInDays": 365})])
            },
        },
    )


def test_no_paid_baseline_services_on_dev(app: cdk.App) -> None:  # D-039: CloudTrail only
    t = template(app, "tasklane-dev-observability")
    for r in ("AWS::GuardDuty::Detector", "AWS::SecurityHub::Hub", "AWS::Config::ConfigurationRecorder"):
        t.resource_count_is(r, 0)


def test_dashboard_exists(app: cdk.App) -> None:
    t = template(app, "tasklane-dev-observability")
    t.has_resource_properties("AWS::CloudWatch::Dashboard", {"DashboardName": "tasklane-dev"})

"""Network: a VPC with isolated subnets only — Aurora needs one; Lambdas stay outside it (Data API, ADR-002)."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_ec2 as ec2
from constructs import Construct


class NetworkStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, **kw: object) -> None:
        super().__init__(scope, id, **kw)  # type: ignore[arg-type]
        self.vpc = ec2.Vpc(
            self,
            "Vpc",
            max_azs=2,
            nat_gateways=0,
            subnet_configuration=[
                ec2.SubnetConfiguration(name="db", subnet_type=ec2.SubnetType.PRIVATE_ISOLATED, cidr_mask=24)
            ],
        )

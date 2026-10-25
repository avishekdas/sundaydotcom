"""Edge: one CloudFront distribution — SPA from S3, /api/* → HTTP API, /ws → WebSocket API (arch 02)."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_cloudfront as cf
from aws_cdk import aws_cloudfront_origins as origins
from aws_cdk import aws_s3 as s3
from aws_cdk import aws_s3_deployment as s3d
from constructs import Construct

from tasklane_infra.assets import web_asset
from tasklane_infra.config import Stage
from tasklane_infra.stacks.api import ApiStack
from tasklane_infra.stacks.identity import IdentityStack
from tasklane_infra.stacks.realtime import RealtimeStack

SPA_FALLBACK = """function handler(event) {
  var r = event.request;
  if (r.uri.indexOf('.') === -1) { r.uri = '/index.html'; }
  return r;
}"""


class EdgeStack(cdk.Stack):
    def __init__(
        self,
        scope: Construct,
        id: str,
        *,
        stage: Stage,
        api: ApiStack,
        realtime: RealtimeStack,
        identity: IdentityStack,
        **kw: object,
    ) -> None:
        super().__init__(scope, id, **kw)  # type: ignore[arg-type]
        bucket = s3.Bucket(
            self,
            "Web",
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            removal_policy=cdk.RemovalPolicy.DESTROY,
            auto_delete_objects=True,
        )
        no_cache = cf.CachePolicy.CACHING_DISABLED
        all_but_host = cf.OriginRequestPolicy.ALL_VIEWER_EXCEPT_HOST_HEADER
        api_domain = cdk.Fn.select(2, cdk.Fn.split("/", api.http_api.api_endpoint))
        ws_domain = cdk.Fn.select(2, cdk.Fn.split("/", realtime.ws_api.api_endpoint))
        fallback = cf.Function(
            self,
            "SpaFallback",
            code=cf.FunctionCode.from_inline(SPA_FALLBACK),
            runtime=cf.FunctionRuntime.JS_2_0,
        )
        self.distribution = cf.Distribution(
            self,
            "Cdn",
            comment=f"tasklane-{stage.name}",
            default_root_object="index.html",
            minimum_protocol_version=cf.SecurityPolicyProtocol.TLS_V1_2_2021,
            default_behavior=cf.BehaviorOptions(
                origin=origins.S3BucketOrigin.with_origin_access_control(bucket),
                viewer_protocol_policy=cf.ViewerProtocolPolicy.REDIRECT_TO_HTTPS,
                response_headers_policy=cf.ResponseHeadersPolicy.SECURITY_HEADERS,
                function_associations=[
                    cf.FunctionAssociation(function=fallback, event_type=cf.FunctionEventType.VIEWER_REQUEST)
                ],
            ),
            additional_behaviors={
                "/api/*": cf.BehaviorOptions(
                    origin=origins.HttpOrigin(api_domain),
                    allowed_methods=cf.AllowedMethods.ALLOW_ALL,
                    viewer_protocol_policy=cf.ViewerProtocolPolicy.HTTPS_ONLY,
                    cache_policy=no_cache,
                    origin_request_policy=all_but_host,
                ),
                "/ws": cf.BehaviorOptions(
                    origin=origins.HttpOrigin(ws_domain),
                    viewer_protocol_policy=cf.ViewerProtocolPolicy.HTTPS_ONLY,
                    cache_policy=no_cache,
                    origin_request_policy=all_but_host,
                ),
            },
        )
        config = {
            "region": self.region,
            "userPoolId": identity.pool.user_pool_id,
            "clientId": identity.client.user_pool_client_id,
            "apiBase": "/api/v1",
            "wsPath": "/ws",
            "stage": stage.name,
        }
        s3d.BucketDeployment(
            self,
            "Deploy",
            destination_bucket=bucket,
            distribution=self.distribution,
            sources=[s3d.Source.asset(web_asset()), s3d.Source.json_data("config.json", config)],
            memory_limit=512,
        )
        cdk.CfnOutput(self, "Url", value=f"https://{self.distribution.distribution_domain_name}")

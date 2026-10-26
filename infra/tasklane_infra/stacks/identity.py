"""Identity: Cognito user pool (admin-invite only, MFA optional until M9 — D-045), the auth-proxy app client and the
CloudFront origin secret (07 §7.4, D-050)."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_cognito as cognito
from aws_cdk import aws_iam as iam
from aws_cdk import aws_lambda as lambda_
from aws_cdk import aws_logs as logs
from aws_cdk import custom_resources as cr
from constructs import Construct

from tasklane_infra.config import Stage

# Generates the origin secret once and never overwrites it (a redeploy keeps CloudFront and the api λ in step).
ORIGIN_KEY_GENERATOR = """
import secrets, boto3
def handler(event, context):
    name = event["ResourceProperties"]["Name"]
    if event["RequestType"] == "Create":
        ssm = boto3.client("ssm")
        try:
            ssm.put_parameter(Name=name, Value=secrets.token_urlsafe(32), Type="String", Overwrite=False)
        except ssm.exceptions.ParameterAlreadyExists:
            pass
    return {"PhysicalResourceId": name}
"""


class IdentityStack(cdk.Stack):
    def __init__(self, scope: Construct, id: str, *, stage: Stage, **kw: object) -> None:
        super().__init__(scope, id, **kw)  # type: ignore[arg-type]
        self.pool = cognito.UserPool(
            self,
            "Pool",
            user_pool_name=f"tasklane-{stage.name}",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            sign_in_case_sensitive=False,
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_digits=True,
                require_lowercase=True,
                require_uppercase=True,
                require_symbols=False,
                temp_password_validity=cdk.Duration.days(3),
            ),
            mfa=cognito.Mfa.OPTIONAL,
            mfa_second_factor=cognito.MfaSecondFactor(otp=True, sms=False),
            account_recovery=cognito.AccountRecovery.EMAIL_ONLY,
            removal_policy=cdk.RemovalPolicy.RETAIN,
        )
        # Retired browser client (phase 1 of 2): no password flow any more (the SPA uses the auth proxy), kept only
        # because the api/edge stacks imported its id; its export is held until phase 2 deletes both.
        self.legacy_web_client = self.pool.add_client(
            "Web",
            user_pool_client_name=f"tasklane-{stage.name}-web",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(),
            prevent_user_existence_errors=True,
        )
        self.export_value(self.legacy_web_client.user_pool_client_id)
        # Auth proxy client (ADR-013): admin password auth from the api λ only; 30-day refresh (D-048), revocable
        # per browser (RevokeToken, D-052).
        self.proxy_client = self.pool.add_client(
            "Proxy",
            user_pool_client_name=f"tasklane-{stage.name}-proxy",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(admin_user_password=True),
            prevent_user_existence_errors=True,
            enable_token_revocation=True,
            access_token_validity=cdk.Duration.minutes(30),
            id_token_validity=cdk.Duration.minutes(30),
            refresh_token_validity=cdk.Duration.days(30),
        )
        self.issuer = f"https://cognito-idp.{self.region}.amazonaws.com/{self.pool.user_pool_id}"
        # CloudFront → API origin secret (07 §7.4) in an SSM String parameter (D-050), read by dynamic reference.
        param = f"/tasklane/{stage.name}/origin-secret"
        gen = lambda_.Function(
            self,
            "OriginSecretFn",
            runtime=lambda_.Runtime.PYTHON_3_13,
            architecture=lambda_.Architecture.ARM_64,
            handler="index.handler",
            code=lambda_.Code.from_inline(ORIGIN_KEY_GENERATOR),
            timeout=cdk.Duration.seconds(30),
        )
        gen.add_to_role_policy(
            iam.PolicyStatement(
                actions=["ssm:PutParameter"],
                resources=[f"arn:aws:ssm:{self.region}:{self.account}:parameter{param}"],
            )
        )
        provider = cr.Provider(
            self, "OriginSecretProvider", on_event_handler=gen, log_retention=logs.RetentionDays.ONE_WEEK
        )
        secret = cdk.CustomResource(
            self,
            "OriginSecret",
            service_token=provider.service_token,
            resource_type="Custom::OriginSecret",
            properties={"Name": param},
        )
        self.origin_secret_ref = f"{{{{resolve:ssm:{param}}}}}"
        self.origin_secret_resource = secret

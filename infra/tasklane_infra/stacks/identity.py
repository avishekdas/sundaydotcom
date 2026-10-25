"""Identity: Cognito user pool (admin-invite only). The auth proxy and MFA enforcement arrive in M1 (D-036)."""

from __future__ import annotations

import aws_cdk as cdk
from aws_cdk import aws_cognito as cognito
from constructs import Construct

from tasklane_infra.config import Stage


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
        self.client = self.pool.add_client(
            "Web",
            user_pool_client_name=f"tasklane-{stage.name}-web",
            generate_secret=False,
            auth_flows=cognito.AuthFlow(user_password=True),
            prevent_user_existence_errors=True,
            access_token_validity=cdk.Duration.minutes(30),
            id_token_validity=cdk.Duration.minutes(30),
            refresh_token_validity=cdk.Duration.days(1),
        )
        self.issuer = f"https://cognito-idp.{self.region}.amazonaws.com/{self.pool.user_pool_id}"

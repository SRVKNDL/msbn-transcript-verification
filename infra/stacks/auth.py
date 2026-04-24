"""Cognito auth for reviewer access."""

from aws_cdk import (
    aws_cognito as cognito,
)
from constructs import Construct


class AuthConstruct(Construct):
    """Cognito user pool and app client for the reviewer dashboard."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.user_pool = cognito.UserPool(
            self,
            "ReviewerPool",
            user_pool_name="msbn-reviewers",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=False),
            ),
            custom_attributes={
                "role": cognito.StringAttribute(mutable=True),
            },
            mfa=cognito.Mfa.OFF,
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_uppercase=True,
                require_lowercase=True,
                require_digits=True,
                require_symbols=True,
            ),
        )

        # SPA client: no secret, SRP auth, refresh tokens.
        # Auth flows:
        #   - SRP: primary client-side flow (challenge-response, never sends password)
        #   - Admin user password: server-side only, for admin-initiate-auth smoke tests
        #   - Refresh: token renewal
        # USER_PASSWORD_AUTH is intentionally excluded — it sends the password
        # in plaintext to Cognito. SRP is the correct client-side flow.
        self.user_pool_client = self.user_pool.add_client(
            "DashboardClient",
            user_pool_client_name="msbn-dashboard",
            auth_flows=cognito.AuthFlow(
                user_srp=True,
                admin_user_password=True,
            ),
            generate_secret=False,
            disable_o_auth=True,
        )

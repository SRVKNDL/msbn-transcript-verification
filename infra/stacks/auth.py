"""Auth construct: Cognito User Pool and client for reviewer authentication.

Cognito (architecture-plan.md Section 2.2):
  - User pool for reviewer authentication
  - Self-sign-up disabled (admin creates test accounts)
  - MFA optional for POC
  - Free at POC user counts (< 50,000 MAU)
"""

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

        # ── Cognito User Pool ─────────────────────────────────────────────────
        self.user_pool = cognito.UserPool(
            self,
            "ReviewerPool",
            user_pool_name="msbn-reviewers",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            standard_attributes=cognito.StandardAttributes(
                email=cognito.StandardAttribute(required=True, mutable=False),
            ),
            mfa=cognito.Mfa.OPTIONAL,
            password_policy=cognito.PasswordPolicy(
                min_length=12,
                require_uppercase=True,
                require_lowercase=True,
                require_digits=True,
                require_symbols=True,
            ),
        )

        # App client for the React dashboard (no secret — SPA cannot keep one).
        self.user_pool_client = self.user_pool.add_client(
            "DashboardClient",
            user_pool_client_name="msbn-dashboard",
            auth_flows=cognito.AuthFlow(
                user_srp=True,
                user_password=True,
            ),
            generate_secret=False,
        )

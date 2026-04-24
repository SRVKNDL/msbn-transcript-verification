"""Cognito auth for reviewer access."""

from aws_cdk import Stack, aws_cognito as cognito
from constructs import Construct


class AuthConstruct(Construct):
    """Cognito user pool and app client for the reviewer dashboard."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        callback_urls: list[str] | None = None,
        logout_urls: list[str] | None = None,
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

        # SPA client: no secret, browser password auth, SRP, refresh tokens.
        # Auth flows:
        #   - User password auth: in-page Cognito login over TLS
        #   - SRP: supported for future SDK-based auth
        #   - Admin user password: server-side only, for admin-initiate-auth smoke tests
        #   - Refresh: token renewal
        callback_urls = callback_urls or ["http://localhost:3000/"]
        logout_urls = logout_urls or ["http://localhost:3000/"]

        self.user_pool_client = self.user_pool.add_client(
            "DashboardClient",
            user_pool_client_name="msbn-dashboard",
            auth_flows=cognito.AuthFlow(
                user_password=True,
                user_srp=True,
                admin_user_password=True,
            ),
            generate_secret=False,
            o_auth=cognito.OAuthSettings(
                flows=cognito.OAuthFlows(authorization_code_grant=True),
                scopes=[
                    cognito.OAuthScope.OPENID,
                    cognito.OAuthScope.EMAIL,
                    cognito.OAuthScope.PROFILE,
                ],
                callback_urls=callback_urls,
                logout_urls=logout_urls,
            ),
        )

        stack = Stack.of(self)
        self.user_pool_domain = self.user_pool.add_domain(
            "DashboardDomain",
            cognito_domain=cognito.CognitoDomainOptions(
                domain_prefix=f"msbn-reviewers-{stack.account}",
            ),
        )

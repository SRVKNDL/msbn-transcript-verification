"""API construct: Cognito User Pool, API Gateway HTTP API, and JWT authorizer.

Cognito (architecture-plan.md Section 2.2):
  - User pool for reviewer authentication
  - Self-sign-up disabled (admin creates test accounts)
  - MFA optional for POC
  - Free at POC user counts (< 50,000 MAU)

API Gateway HTTP API (architecture-plan.md Section 2.1):
  - HTTP API (not REST API) for lower cost
  - JWT authorizer backed by Cognito
  - Routes proxy to DashboardApiLambda
  - CORS enabled for dashboard origin
"""

from aws_cdk import (
    CfnOutput,
    aws_apigatewayv2 as apigwv2,
    aws_apigatewayv2_authorizers as apigwv2_auth,
    aws_apigatewayv2_integrations as apigwv2_int,
    aws_cognito as cognito,
    aws_lambda as lambda_,
)
from constructs import Construct


class ApiConstruct(Construct):
    """API Gateway HTTP API and Cognito user pool for the reviewer dashboard."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        dashboard_api_lambda: lambda_.IFunction,
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
                min_length=8,
                require_uppercase=True,
                require_digits=True,
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

        # ── HTTP API ──────────────────────────────────────────────────────────
        self.http_api = apigwv2.HttpApi(
            self,
            "DashboardApi",
            api_name="msbn-dashboard-api",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=["*"],
                allow_methods=[
                    apigwv2.CorsHttpMethod.GET,
                    apigwv2.CorsHttpMethod.POST,
                    apigwv2.CorsHttpMethod.OPTIONS,
                ],
                allow_headers=["Content-Type", "Authorization"],
            ),
        )

        # ── JWT Authorizer ────────────────────────────────────────────────────
        authorizer = apigwv2_auth.HttpJwtAuthorizer(
            "CognitoAuthorizer",
            jwt_issuer=f"https://cognito-idp.us-east-1.amazonaws.com/{self.user_pool.user_pool_id}",
            jwt_audience=[self.user_pool_client.user_pool_client_id],
        )

        # ── Lambda Integration ────────────────────────────────────────────────
        integration = apigwv2_int.HttpLambdaIntegration(
            "DashboardApiIntegration",
            handler=dashboard_api_lambda,
        )

        # ── Routes ────────────────────────────────────────────────────────────
        routes = [
            ("GET", "/applications"),
            ("GET", "/applications/{id}"),
            ("POST", "/applications/{id}/decision"),
            ("GET", "/applications/{id}/audit"),
        ]
        method_map = {
            "GET": apigwv2.HttpMethod.GET,
            "POST": apigwv2.HttpMethod.POST,
        }

        for method, path in routes:
            self.http_api.add_routes(
                path=path,
                methods=[method_map[method]],
                integration=integration,
                authorizer=authorizer,
            )

        # ── Outputs ───────────────────────────────────────────────────────────
        CfnOutput(self, "ApiUrl", value=self.http_api.api_endpoint)
        CfnOutput(
            self, "UserPoolId", value=self.user_pool.user_pool_id
        )
        CfnOutput(
            self,
            "UserPoolClientId",
            value=self.user_pool_client.user_pool_client_id,
        )

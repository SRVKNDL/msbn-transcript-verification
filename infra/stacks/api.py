"""API construct: API Gateway HTTP API and JWT authorizer.

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
    """API Gateway HTTP API for the reviewer dashboard."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        dashboard_api_lambda: lambda_.IFunction,
        user_pool: cognito.IUserPool,
        user_pool_client: cognito.IUserPoolClient,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

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

        # ── Throttling ────────────────────────────────────────────────────────
        # POC-scale limits. Raise for production traffic.
        cfn_stage = self.http_api.default_stage.node.default_child
        cfn_stage.add_property_override("DefaultRouteSettings", {
            "ThrottlingBurstLimit": 50,
            "ThrottlingRateLimit": 25,
        })

        # ── JWT Authorizer ────────────────────────────────────────────────────
        authorizer = apigwv2_auth.HttpJwtAuthorizer(
            "CognitoAuthorizer",
            jwt_issuer=f"https://cognito-idp.us-east-1.amazonaws.com/{user_pool.user_pool_id}",
            jwt_audience=[user_pool_client.user_pool_client_id],
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

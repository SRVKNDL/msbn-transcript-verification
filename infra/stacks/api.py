"""API Gateway HTTP API for the dashboard."""

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
        prefill_lambda: lambda_.IFunction,
        user_pool: cognito.IUserPool,
        user_pool_client: cognito.IUserPoolClient,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.http_api = apigwv2.HttpApi(
            self,
            "DashboardApi",
            api_name="msbn-dashboard-api",
            cors_preflight=apigwv2.CorsPreflightOptions(
                allow_origins=["*"],
                allow_methods=[
                    apigwv2.CorsHttpMethod.GET,
                    apigwv2.CorsHttpMethod.POST,
                    apigwv2.CorsHttpMethod.DELETE,
                    apigwv2.CorsHttpMethod.OPTIONS,
                ],
                allow_headers=["Content-Type", "Authorization"],
            ),
        )

        # POC-scale limits. Raise before production traffic.
        cfn_stage = self.http_api.default_stage.node.default_child
        cfn_stage.add_property_override("DefaultRouteSettings", {
            "ThrottlingBurstLimit": 50,
            "ThrottlingRateLimit": 25,
        })

        authorizer = apigwv2_auth.HttpJwtAuthorizer(
            "CognitoAuthorizer",
            jwt_issuer=f"https://cognito-idp.us-east-1.amazonaws.com/{user_pool.user_pool_id}",
            jwt_audience=[user_pool_client.user_pool_client_id],
        )

        integration = apigwv2_int.HttpLambdaIntegration(
            "DashboardApiIntegration",
            handler=dashboard_api_lambda,
        )
        prefill_integration = apigwv2_int.HttpLambdaIntegration(
            "PrefillApiIntegration",
            handler=prefill_lambda,
        )

        routes = [
            ("GET", "/applications"),
            ("POST", "/uploads"),
            ("GET", "/applications/{id}"),
            ("DELETE", "/applications/{id}"),
            ("GET", "/applications/{id}/pages/{page}"),
            ("POST", "/applications/{id}/decision"),
            ("GET", "/applications/{id}/audit"),
        ]
        method_map = {
            "GET": apigwv2.HttpMethod.GET,
            "POST": apigwv2.HttpMethod.POST,
            "DELETE": apigwv2.HttpMethod.DELETE,
        }

        for method, path in routes:
            self.http_api.add_routes(
                path=path,
                methods=[method_map[method]],
                integration=integration,
                authorizer=authorizer,
            )

        prefill_routes = [
            ("POST", "/prefill-uploads"),
            ("POST", "/prefill"),
        ]
        for method, path in prefill_routes:
            self.http_api.add_routes(
                path=path,
                methods=[method_map[method]],
                integration=prefill_integration,
                authorizer=authorizer,
            )

        CfnOutput(self, "ApiUrl", value=self.http_api.api_endpoint)

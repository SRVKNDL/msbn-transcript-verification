"""MsbnApiStack: API Gateway + throttling + Dashboard API Lambda wiring.

Depends on MsbnComputeStack (for the Lambda) and MsbnAuthStack (for JWT authorizer).
"""

import aws_cdk as cdk
from aws_cdk import aws_cognito as cognito, aws_lambda as lambda_
from constructs import Construct

from stacks.api import ApiConstruct


class MsbnApiStack(cdk.Stack):
    """API Gateway HTTP API with Cognito JWT authorizer."""

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

        ApiConstruct(
            self,
            "Api",
            dashboard_api_lambda=dashboard_api_lambda,
            user_pool=user_pool,
            user_pool_client=user_pool_client,
        )

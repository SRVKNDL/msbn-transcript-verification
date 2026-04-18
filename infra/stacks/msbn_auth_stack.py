"""MsbnAuthStack: Cognito User Pool + Client.

Deployed second (or in parallel with Storage). No dependencies.
"""

import aws_cdk as cdk
from aws_cdk import CfnOutput
from constructs import Construct

from stacks.auth import AuthConstruct


class MsbnAuthStack(cdk.Stack):
    """Cognito user pool and app client for reviewer authentication."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        auth = AuthConstruct(self, "Auth")

        # Expose for cross-stack references.
        self.user_pool = auth.user_pool
        self.user_pool_client = auth.user_pool_client

        # Outputs for frontend configuration.
        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        CfnOutput(
            self,
            "UserPoolClientId",
            value=self.user_pool_client.user_pool_client_id,
        )

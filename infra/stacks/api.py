"""API construct: API Gateway HTTP API and Cognito user pool.

API Gateway (see architecture-plan.md Section 2.1):
  - HTTP API (not REST API) for lower cost
  - Routes proxy to DashboardApiLambda
  - JWT authorizer backed by Cognito

Cognito (see architecture-plan.md Section 2.2):
  - User pool for reviewer authentication
  - MFA support
  - Free at POC user counts (< 50,000 MAU)
"""

from constructs import Construct


class ApiConstruct(Construct):
    """API Gateway HTTP API and Cognito user pool for the reviewer dashboard."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # TODO: Create Cognito User Pool
        #   - Self-sign-up disabled (admin creates reviewer accounts)
        #   - MFA optional for POC
        #   - App client for the React dashboard

        # TODO: Create HTTP API (API Gateway v2)
        #   - JWT authorizer using the Cognito user pool
        #   - Default route -> DashboardApiLambda
        #   - CORS configured for dashboard origin

"""DashboardApiLambda: REST backend for the reviewer dashboard."""

import json
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event, context):
    """Handle API Gateway requests for the reviewer dashboard.

    Routes:
    - GET  /applications          List applications (filterable by status)
    - GET  /applications/{id}     Get application detail with flags
    - GET  /applications/{id}/pages/{page}  Presigned URL for page image
    - POST /applications/{id}/flags/{flag_id}  Confirm or override a flag
    - POST /applications/{id}/decision  Submit final decision
    """
    logger.info("DashboardApiLambda invoked: %s", json.dumps(event))

    # TODO: Route based on HTTP method + path
    # TODO: Authenticate via Cognito JWT (handled by API Gateway authorizer)
    # TODO: Implement each route against DynamoDB and S3

    return {
        "statusCode": 200,
        "headers": {"Content-Type": "application/json"},
        "body": json.dumps({"message": "stub"}),
    }

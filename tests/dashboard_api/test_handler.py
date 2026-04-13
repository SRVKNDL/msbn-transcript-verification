"""Smoke tests for DashboardApiLambda.

Verifies importability and stub response shape for API Gateway proxy events.
DynamoDB and S3 calls are not yet implemented.
"""

import importlib.util
import json
import os

_HERE = os.path.dirname(__file__)
_spec = importlib.util.spec_from_file_location(
    "dashboard_api_handler",
    os.path.join(_HERE, "../../services/dashboard_api/handler.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
handler = _mod.handler


def test_handler_returns_200(api_gateway_event, lambda_context):
    """Handler must return HTTP 200 for a GET /applications API Gateway event."""
    response = handler(api_gateway_event, lambda_context)
    assert response["statusCode"] == 200


def test_handler_returns_json_body(api_gateway_event, lambda_context):
    """Response body must be valid JSON."""
    response = handler(api_gateway_event, lambda_context)
    body = json.loads(response["body"])
    assert isinstance(body, dict)


def test_handler_returns_content_type_header(api_gateway_event, lambda_context):
    """Response must include Content-Type: application/json header."""
    response = handler(api_gateway_event, lambda_context)
    assert response.get("headers", {}).get("Content-Type") == "application/json"

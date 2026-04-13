"""Smoke tests for NotifyLambda.

Verifies importability and stub response shape. SNS publish calls are not
yet implemented.
"""

import importlib.util
import json
import os

_HERE = os.path.dirname(__file__)
_spec = importlib.util.spec_from_file_location(
    "notify_handler",
    os.path.join(_HERE, "../../services/notify/handler.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
handler = _mod.handler


def test_handler_returns_200(step_functions_event, lambda_context):
    """Handler must return HTTP 200 for a Step Functions notify event."""
    response = handler(step_functions_event, lambda_context)
    assert response["statusCode"] == 200


def test_handler_returns_json_body(step_functions_event, lambda_context):
    """Response body must be valid JSON."""
    response = handler(step_functions_event, lambda_context)
    body = json.loads(response["body"])
    assert isinstance(body, dict)

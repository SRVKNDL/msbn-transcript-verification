"""Smoke tests for IntakeLambda.

These tests verify that the handler is importable and returns a structurally
valid response for a minimal S3 event. No AWS calls are made — the handler
stubs are not yet wired to boto3.
"""

import importlib.util
import json
import os

_HERE = os.path.dirname(__file__)
_spec = importlib.util.spec_from_file_location(
    "intake_handler",
    os.path.join(_HERE, "../../services/intake/handler.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
handler = _mod.handler


def test_handler_returns_200(s3_event, lambda_context):
    """Handler must return HTTP 200 for a valid S3 event (stub phase)."""
    response = handler(s3_event, lambda_context)
    assert response["statusCode"] == 200


def test_handler_returns_json_body(s3_event, lambda_context):
    """Response body must be valid JSON."""
    response = handler(s3_event, lambda_context)
    body = json.loads(response["body"])
    assert isinstance(body, dict)

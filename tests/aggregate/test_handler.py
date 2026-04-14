"""Smoke tests for AggregationLambda.

Verifies importability and stub response shape. S3 reads, comparisons,
and DynamoDB writes are not yet implemented.
"""

import importlib.util
import os

_HERE = os.path.dirname(__file__)
_spec = importlib.util.spec_from_file_location(
    "aggregate_handler",
    os.path.join(_HERE, "../../services/aggregate/handler.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
handler = _mod.handler


def test_handler_returns_ok(step_functions_event, lambda_context):
    """Handler must return status ok for a Step Functions aggregation event."""
    response = handler(step_functions_event, lambda_context)
    assert response["status"] == "ok"


def test_handler_returns_dict(step_functions_event, lambda_context):
    """Handler must return a dict."""
    response = handler(step_functions_event, lambda_context)
    assert isinstance(response, dict)

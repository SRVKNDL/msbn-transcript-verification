"""Shared pytest fixtures for MSBN Lambda unit tests.

Each test module imports the Lambda handler directly (no deployment required).
AWS SDK calls are mocked at the boto3 level — no real AWS credentials needed.
"""

import pytest


@pytest.fixture
def lambda_context():
    """Minimal stand-in for the AWS Lambda context object."""

    class _Context:
        function_name = "test-function"
        memory_limit_in_mb = 128
        invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test"
        aws_request_id = "test-request-id"

    return _Context()


@pytest.fixture
def s3_event():
    """Minimal S3 ObjectCreated event, mimicking an intake upload."""
    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "msbn-transcripts-dev"},
                    "object": {"key": "raw/APP-001/TRANSCRIPT_sample.pdf"},
                }
            }
        ]
    }


@pytest.fixture
def step_functions_event():
    """Minimal event passed by Step Functions to a pipeline Lambda."""
    return {
        "application_id": "APP-001",
        "doc_type": "TRANSCRIPT",
        "s3_key": "raw/APP-001/TRANSCRIPT_sample.pdf",
    }


@pytest.fixture
def api_gateway_event():
    """Minimal API Gateway HTTP API proxy event for DashboardApiLambda."""
    return {
        "version": "2.0",
        "routeKey": "GET /applications",
        "rawPath": "/applications",
        "requestContext": {
            "http": {"method": "GET", "path": "/applications"},
            "authorizer": {"jwt": {"claims": {"sub": "reviewer-sub-001"}}},
        },
        "queryStringParameters": {"status": "READY_FOR_REVIEW"},
    }

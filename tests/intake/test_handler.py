"""Unit tests for IntakeLambda using moto-mocked AWS.

Coverage:
- DynamoDB item written with correct fields and key structure
- S3 key parsing: normal, nested, no-prefix, URL-encoded, and malformed inputs
- Structured log output includes applicationId
"""

import json
import logging
import os
import sys

import boto3
import pytest
from moto import mock_aws

# Fake credentials must be set before any boto3/botocore import so that moto
# does not attempt to contact real AWS endpoints.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("TABLE_NAME", "msbn-applications")

# Add the service directory to sys.path so the Lambda module can be imported
# as-is, matching the Lambda execution environment.
_HANDLER_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "../../services/intake")
)
if _HANDLER_DIR not in sys.path:
    sys.path.insert(0, _HANDLER_DIR)

import handler as _intake  # noqa: E402

handler = _intake.handler
_parse_s3_record = _intake._parse_s3_record

_TABLE_NAME = "msbn-applications"


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def dynamodb_table():
    """Moto-backed DynamoDB table for the duration of one test.

    The mock_aws() context manager is held open while the test runs (the
    fixture yields inside it).  Because moto patches at the botocore HTTP
    layer, the module-level _dynamodb resource in handler.py uses the mock
    even though it was constructed before this fixture started.
    """
    with mock_aws():
        dynamo = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamo.create_table(
            TableName=_TABLE_NAME,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        yield table


@pytest.fixture()
def uploads_s3_event():
    """S3 ObjectCreated event for a single PDF on the uploads/ prefix."""
    return {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "msbn-transcripts-dev"},
                    "object": {
                        "key": "uploads/TRANSCRIPT_sample.pdf",
                        "size": 204800,
                    },
                }
            }
        ]
    }


# ── DynamoDB correctness ───────────────────────────────────────────────────────


def test_dynamodb_item_written(dynamodb_table, uploads_s3_event, lambda_context):
    """Handler must create exactly one METADATA item with all required fields."""
    handler(uploads_s3_event, lambda_context)

    scan = dynamodb_table.scan()
    assert scan["Count"] == 1

    item = scan["Items"][0]
    assert item["SK"] == "METADATA"
    assert item["entity_type"] == "METADATA"
    assert item["status"] == "INTAKE_COMPLETE"
    assert item["originalFilename"] == "TRANSCRIPT_sample.pdf"
    assert item["s3Key"] == "uploads/TRANSCRIPT_sample.pdf"
    assert int(item["size_bytes"]) == 204800
    assert item["applicationId"]                            # non-empty
    assert item["PK"] == f"APP#{item['applicationId']}"    # key structure
    assert item["uploadedAt"]                               # non-empty ISO-8601


def test_response_includes_application_id(dynamodb_table, uploads_s3_event, lambda_context):
    """Response body must include applicationId and processed count."""
    response = handler(uploads_s3_event, lambda_context)
    assert response["statusCode"] == 200
    body = json.loads(response["body"])
    assert body["processed"] == 1
    app = body["applications"][0]
    assert app["applicationId"]
    assert app["s3Key"] == "uploads/TRANSCRIPT_sample.pdf"


def test_multiple_records_create_independent_items(dynamodb_table, lambda_context):
    """One invocation with two S3 records must produce two independent METADATA items."""
    multi_event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "msbn-transcripts-dev"},
                    "object": {"key": "uploads/doc_a.pdf", "size": 1024},
                }
            },
            {
                "s3": {
                    "bucket": {"name": "msbn-transcripts-dev"},
                    "object": {"key": "uploads/doc_b.pdf", "size": 2048},
                }
            },
        ]
    }
    response = handler(multi_event, lambda_context)
    body = json.loads(response["body"])
    assert body["processed"] == 2

    scan = dynamodb_table.scan()
    assert scan["Count"] == 2
    # Each item must have a distinct applicationId.
    app_ids = {item["applicationId"] for item in scan["Items"]}
    assert len(app_ids) == 2
    filenames = {item["originalFilename"] for item in scan["Items"]}
    assert filenames == {"doc_a.pdf", "doc_b.pdf"}


def test_empty_records_returns_200_no_writes(dynamodb_table, lambda_context):
    """An event with no Records must return 200 and write nothing to DynamoDB."""
    response = handler({"Records": []}, lambda_context)
    assert response["statusCode"] == 200
    assert dynamodb_table.scan()["Count"] == 0


# ── S3 key parsing ─────────────────────────────────────────────────────────────


def _record(key: str, size: int = 0) -> dict:
    """Build a minimal S3 event record."""
    return {
        "s3": {
            "bucket": {"name": "msbn-transcripts-dev"},
            "object": {"key": key, "size": size},
        }
    }


def test_s3_key_parses_uploads_prefix():
    """Standard uploads/ key must yield the bare filename."""
    _, key, _, filename = _parse_s3_record(_record("uploads/transcript.pdf"))
    assert key == "uploads/transcript.pdf"
    assert filename == "transcript.pdf"


def test_s3_key_parses_nested_path():
    """Nested path must use only the last component as the filename."""
    _, _, _, filename = _parse_s3_record(
        _record("uploads/2026/04/13/transcript.pdf")
    )
    assert filename == "transcript.pdf"


def test_s3_key_parses_no_prefix():
    """A flat key with no slashes must use the whole key as the filename."""
    _, _, _, filename = _parse_s3_record(_record("transcript.pdf"))
    assert filename == "transcript.pdf"


def test_s3_key_url_encoded_spaces():
    """URL-encoded spaces ('+') in the key must be decoded before storage."""
    _, key, _, filename = _parse_s3_record(
        _record("uploads/my+transcript+file.pdf")
    )
    assert key == "uploads/my transcript file.pdf"
    assert filename == "my transcript file.pdf"


def test_s3_key_trailing_slash_raises():
    """A key ending in '/' yields an empty filename, which must raise ValueError."""
    with pytest.raises(ValueError, match="filename"):
        _parse_s3_record(_record("uploads/subdir/"))


def test_s3_key_missing_key_field_raises():
    """Missing 's3.object.key' must raise ValueError."""
    bad_record = {"s3": {"bucket": {"name": "test"}, "object": {}}}
    with pytest.raises(ValueError, match="Malformed"):
        _parse_s3_record(bad_record)


def test_s3_key_missing_s3_field_raises():
    """Missing 's3' field entirely must raise ValueError."""
    with pytest.raises(ValueError, match="Malformed"):
        _parse_s3_record({})


# ── Structured logging ─────────────────────────────────────────────────────────


def test_log_includes_application_id(
    dynamodb_table, uploads_s3_event, lambda_context, caplog
):
    """Handler must emit at least one structured INFO log containing applicationId."""
    with caplog.at_level(logging.INFO):
        handler(uploads_s3_event, lambda_context)

    structured = []
    for message in caplog.messages:
        try:
            structured.append(json.loads(message))
        except (json.JSONDecodeError, TypeError):
            pass

    entries = [e for e in structured if "applicationId" in e]
    assert entries, f"No structured log with applicationId. All messages: {caplog.messages}"

    entry = entries[0]
    assert entry["applicationId"]
    assert entry["status"] == "INTAKE_COMPLETE"
    assert "s3Key" in entry

"""Unit tests for IntakeLambda using moto-mocked AWS.

Coverage:
- DynamoDB item written with correct fields and key structure
- S3 key parsing: normal, nested, no-prefix, URL-encoded, and malformed inputs
- Structured log output includes applicationId
- Step Functions execution is started with correct input and name
- Step Functions client errors are handled: logged and re-raised
"""

import json
import logging
import os
import sys

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

# Fake credentials must be set before any boto3/botocore import so that moto
# does not attempt to contact real AWS endpoints.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("TABLE_NAME", "msbn-applications")

# Fake state machine ARN used throughout this test module.  Must be set before
# importing the handler so that the module-level _STATE_MACHINE_ARN is populated.
_FAKE_SFN_ARN = (
    "arn:aws:states:us-east-1:123456789012:stateMachine:test-pipeline"
)
os.environ.setdefault("STATE_MACHINE_ARN", _FAKE_SFN_ARN)

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

# Minimal valid Step Functions state machine definition used by the test fixture.
_SFN_STUB_DEFINITION = json.dumps(
    {
        "Comment": "test stub",
        "StartAt": "Start",
        "States": {"Start": {"Type": "Pass", "End": True}},
    }
)


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def dynamodb_table():
    """Moto-backed DynamoDB table and Step Functions state machine for one test.

    The mock_aws() context manager patches at the botocore HTTP layer, so the
    module-level _dynamodb resource and _sfn client in handler.py both use the
    mock while the fixture is active, even though they were constructed before
    this fixture started.
    """
    with mock_aws():
        # DynamoDB table ───────────────────────────────────────────────────────
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

        # Step Functions state machine ──────────────────────────────────────────
        # Must exist in the mock before the handler calls start_execution.
        sfn_client = boto3.client("stepfunctions", region_name="us-east-1")
        sfn_client.create_state_machine(
            name="test-pipeline",
            definition=_SFN_STUB_DEFINITION,
            roleArn="arn:aws:iam::123456789012:role/test-role",
            type="STANDARD",
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
    assert item["status"] == "PROCESSING"
    assert item["submission_ts"] == item["uploadedAt"]
    assert item["originalFilename"] == "TRANSCRIPT_sample.pdf"
    assert item["s3_key"] == "uploads/TRANSCRIPT_sample.pdf"
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
    assert app["s3_key"] == "uploads/TRANSCRIPT_sample.pdf"


def test_upload_metadata_application_id_becomes_application_id(
    dynamodb_table, uploads_s3_event, lambda_context
):
    """Manual upload application ID must become the DynamoDB application ID."""
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="msbn-transcripts-dev")
    s3.put_object(
        Bucket="msbn-transcripts-dev",
        Key="uploads/TRANSCRIPT_sample.pdf",
        Body=b"%PDF-1.4",
        Metadata={
            "application_id": "APP-MANUAL-001",
            "applicant_name": "Jane Smith",
        },
    )

    response = handler(uploads_s3_event, lambda_context)
    assert response["statusCode"] == 200

    item = dynamodb_table.get_item(
        Key={"PK": "APP#APP-MANUAL-001", "SK": "METADATA"}
    )["Item"]
    assert item["applicationId"] == "APP-MANUAL-001"
    assert item["applicant_name"] == "Jane Smith"


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


def test_s3_key_trailing_slash_returns_empty_filename():
    """Placeholder folder objects are detected by an empty derived filename."""
    _, key, _, filename = _parse_s3_record(_record("uploads/subdir/"))
    assert key == "uploads/subdir/"
    assert filename == ""


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
    assert entry["status"] == "PROCESSING"
    assert "s3_key" in entry


# ── Step Functions integration ─────────────────────────────────────────────────


def test_sfn_execution_started_with_correct_input(
    dynamodb_table, uploads_s3_event, lambda_context
):
    """Handler must start a Step Functions execution with applicationId, s3_key, and bucket."""
    handler(uploads_s3_event, lambda_context)

    sfn_client = boto3.client("stepfunctions", region_name="us-east-1")
    executions = sfn_client.list_executions(stateMachineArn=_FAKE_SFN_ARN)[
        "executions"
    ]
    assert len(executions) == 1

    # Fetch full execution details to inspect the input.
    execution = sfn_client.describe_execution(
        executionArn=executions[0]["executionArn"]
    )
    payload = json.loads(execution["input"])

    assert payload["s3_key"] == "uploads/TRANSCRIPT_sample.pdf"
    assert payload["bucket"] == "msbn-transcripts-dev"
    assert "applicationId" in payload
    assert payload["pk"] == f"APP#{payload['applicationId']}"


def test_sfn_execution_name_matches_application_id(
    dynamodb_table, uploads_s3_event, lambda_context
):
    """Execution name must be the applicationId for idempotency and traceability."""
    response = handler(uploads_s3_event, lambda_context)
    body = json.loads(response["body"])
    application_id = body["applications"][0]["applicationId"]

    sfn_client = boto3.client("stepfunctions", region_name="us-east-1")
    executions = sfn_client.list_executions(stateMachineArn=_FAKE_SFN_ARN)[
        "executions"
    ]
    assert len(executions) == 1
    assert executions[0]["name"] == application_id


def test_sfn_client_error_logs_and_raises(
    dynamodb_table, uploads_s3_event, lambda_context, monkeypatch, caplog
):
    """If Step Functions raises a ClientError, handler must log it and re-raise.

    S3 event sources retry failed Lambda invocations, so re-raising is correct.
    The DynamoDB METADATA item is already written before the SFN call. Duplicate
    S3 notifications are handled separately via a conditional put guard.
    """
    def _raise(*args, **kwargs):
        raise ClientError(
            {"Error": {"Code": "StateMachineDoesNotExist", "Message": "not found"}},
            "StartExecution",
        )

    monkeypatch.setattr(_intake._sfn, "start_execution", _raise)

    with caplog.at_level(logging.ERROR):
        with pytest.raises(ClientError):
            handler(uploads_s3_event, lambda_context)

    error_logs = [
        json.loads(m)
        for m in caplog.messages
        if m.startswith("{") and "failed to start" in m
    ]
    assert error_logs, "Expected a structured error log for the SFN failure"
    assert "applicationId" in error_logs[0]
    assert "errorCode" in error_logs[0]


def test_duplicate_s3_event_does_not_reset_ready_item_to_processing(
    dynamodb_table, uploads_s3_event, lambda_context
):
    """A duplicate upload event must not overwrite an existing finished item."""
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="msbn-transcripts-dev")
    s3.put_object(
        Bucket="msbn-transcripts-dev",
        Key="uploads/TRANSCRIPT_sample.pdf",
        Body=b"%PDF-1.4",
        Metadata={"application_id": "APP-DUP-001"},
    )

    first = handler(uploads_s3_event, lambda_context)
    assert first["statusCode"] == 200

    dynamodb_table.update_item(
        Key={"PK": "APP#APP-DUP-001", "SK": "METADATA"},
        UpdateExpression="SET #st = :status",
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={":status": "READY_FOR_REVIEW"},
    )

    second = handler(uploads_s3_event, lambda_context)
    second_body = json.loads(second["body"])
    assert second["statusCode"] == 200
    assert second_body["applications"][0]["duplicate"] is True

    item = dynamodb_table.get_item(
        Key={"PK": "APP#APP-DUP-001", "SK": "METADATA"}
    )["Item"]
    assert item["status"] == "READY_FOR_REVIEW"

    sfn_client = boto3.client("stepfunctions", region_name="us-east-1")
    executions = sfn_client.list_executions(stateMachineArn=_FAKE_SFN_ARN)[
        "executions"
    ]
    assert len(executions) == 1


def test_placeholder_folder_object_is_skipped(dynamodb_table, lambda_context):
    """S3 folder placeholder objects under uploads/ must not start the pipeline."""
    event = {"Records": [_record("uploads/test-001/")]}

    response = handler(event, lambda_context)
    body = json.loads(response["body"])

    assert response["statusCode"] == 200
    assert body["processed"] == 1
    assert body["applications"] == [{"skipped": True, "s3_key": "uploads/test-001/"}]
    assert dynamodb_table.scan()["Count"] == 0

    sfn_client = boto3.client("stepfunctions", region_name="us-east-1")
    executions = sfn_client.list_executions(stateMachineArn=_FAKE_SFN_ARN)[
        "executions"
    ]
    assert executions == []

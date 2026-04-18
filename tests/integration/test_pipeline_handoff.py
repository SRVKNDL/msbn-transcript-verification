"""End-to-end pipeline handoff tests: Intake → Extract → Aggregate → Validate → QueueForReview.

These tests do not stand up a real Step Functions state machine (moto does not
execute JSONPath-based ResultPath merges), but they DO verify the contract at
every boundary — i.e., the output keys of one Lambda exactly match the input
keys the next Lambda reads. A future key-name rename or schema drift will
break one of these tests before production.

What's mocked / what's real:
- S3: moto (real API shape, in-memory).
- DynamoDB: moto.
- Step Functions: moto (Intake uses it only for ``start_execution``; we do not
  run the actual state machine).
- Bedrock: unittest.mock — ``extract_handler._bedrock`` is replaced with a
  MagicMock returning a canned Nova response so Extract writes a realistic
  per-page JSON to S3.
- ``convert_from_path`` is patched to return synthetic images so the test
  does not depend on poppler or any fixture PDF.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from io import BytesIO
from unittest.mock import MagicMock, patch

import boto3
import pytest
from moto import mock_aws
from PIL import Image

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("TABLE_NAME", "msbn-applications")
os.environ.setdefault("BUCKET_NAME", "msbn-transcripts-dev")
os.environ.setdefault("STATE_MACHINE_ARN",
                      "arn:aws:states:us-east-1:123456789012:stateMachine:msbn-test")

_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), "../.."))

_TABLE = "msbn-applications"
_BUCKET = "msbn-transcripts-dev"


# ── Handler loading ──────────────────────────────────────────────────────────
# Each handler is loaded by absolute path because several services define a
# top-level ``handler.py`` — importing by package name would collide.

def _load(module_name: str, relative_path: str, extra_sys_path: str | None = None):
    full_path = os.path.join(_ROOT, relative_path)
    if extra_sys_path:
        sys.path.insert(0, os.path.join(_ROOT, extra_sys_path))
    try:
        spec = importlib.util.spec_from_file_location(module_name, full_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    finally:
        if extra_sys_path:
            sys.path.pop(0)
    return mod


intake_mod = _load("intake_handler_int", "services/intake/handler.py")
extract_mod = _load(
    "extract_handler_int",
    "services/extract/handler.py",
    extra_sys_path="services/extract",
)
aggregate_mod = _load("aggregate_handler_int", "services/aggregate/handler.py")
rule_engine_mod = _load(
    "rule_engine_handler_int",
    "services/rule_engine/handler.py",
    extra_sys_path="services/rule_engine",
)
notify_mod = _load("notify_handler_int", "services/notify/handler.py")


# ── Canned Nova response (one clean page) ─────────────────────────────────────
# Every field in the vocabulary at "high" confidence so the rule engine has
# zero flags on the happy-path test and we can assert end-to-end success.

_CANNED_NOVA_PAGE: dict = {
    "seal_type": {
        "value": "embossed",
        "confidence": "high",
        "source_location": {"page_number": 1, "text_spans": ["Official Seal"]},
    },
    "seal_quality": {"value": "clear", "confidence": "high"},
    "print_technology": {"value": "laser", "confidence": "high"},
    "paper_size_format": {"value": "us_letter", "confidence": "high"},
    "text_alignment": {"value": "normal", "confidence": "high"},
    "document_provenance_appearance": {"value": "original", "confidence": "high"},
    "security_features_present": {
        "value": ["watermark", "serial_number"], "confidence": "high"
    },
    "security_features_assessable": {"value": "yes", "confidence": "high"},
    "grading_scale_format": {"value": "letter_grade_us", "confidence": "high"},
    "language_of_issue": {"value": "english", "confidence": "high"},
    "course_relevance": {"value": "nursing_standard", "confidence": "high"},
    "duplicate_courses_detected": {"value": "no", "confidence": "high"},
    "suspicious_course_names": {"value": [], "confidence": "high"},
    "gpa_arithmetic_consistency": {"value": "consistent", "confidence": "high"},
    "dates_chronology_ok": {"value": "yes", "confidence": "high"},
    "dates_chronology_issue": {"value": "none", "confidence": "high"},
    "program_duration_consistency": {
        "value": "consistent_with_degree", "confidence": "high"
    },
    "accreditation_claim": {"value": "ACEN", "confidence": "high"},
    "accreditation_claim_location": {
        "value": {"page_number": 1, "text_spans": ["Accredited by ACEN"]},
        "confidence": "high",
    },
    "diploma_mill_language_detected": {"value": "no", "confidence": "high"},
    "diploma_mill_phrases_found": {"value": [], "confidence": "high"},
    "institution_address_present": {"value": "yes", "confidence": "high"},
    "institution_phone_present": {"value": "yes", "confidence": "high"},
    "institution_website_present": {"value": "yes", "confidence": "high"},
    "graduation_confirmation_present": {"value": "yes", "confidence": "high"},
    "required_nursing_domains_present": {
        "value": ["adult_med_surg", "obstetrics", "pediatrics",
                  "psychiatric", "gerontology", "community_health"],
        "confidence": "high",
    },
}


def _bedrock_mock() -> MagicMock:
    mock = MagicMock()
    body = json.dumps({
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": json.dumps(_CANNED_NOVA_PAGE)}],
            }
        },
        "stopReason": "end_turn",
    }).encode("utf-8")
    mock.invoke_model.side_effect = lambda **kw: {"body": BytesIO(body)}
    return mock


# ── AWS fixture ───────────────────────────────────────────────────────────────


@pytest.fixture()
def aws_env(lambda_context):
    """Set up S3, DynamoDB, and a dummy Step Functions state machine."""
    # rule_engine_handler captures BUCKET_NAME at module import. If a previous
    # test file imported it with a different BUCKET_NAME env value, the stale
    # constant would point at a bucket we never create. Pin it to ours for
    # the duration of this test.
    rule_engine_mod.BUCKET_NAME = _BUCKET
    extract_mod.BUCKET_NAME = _BUCKET
    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=_BUCKET)

        dynamo = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamo.create_table(
            TableName=_TABLE,
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"},
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"},
                {"AttributeName": "status", "AttributeType": "S"},
                {"AttributeName": "submission_ts", "AttributeType": "S"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "GSI1-ReviewQueue",
                    "KeySchema": [
                        {"AttributeName": "status", "KeyType": "HASH"},
                        {"AttributeName": "submission_ts", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                },
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        sfn = boto3.client("stepfunctions", region_name="us-east-1")
        # moto's create_state_machine requires a minimal valid ASL definition
        # and an IAM role ARN (string check only — not actually assumed).
        sfn_resp = sfn.create_state_machine(
            name="msbn-test",
            definition=json.dumps({
                "StartAt": "Done",
                "States": {"Done": {"Type": "Pass", "End": True}},
            }),
            roleArn="arn:aws:iam::123456789012:role/msbn-test",
        )
        os.environ["STATE_MACHINE_ARN"] = sfn_resp["stateMachineArn"]
        # Point the intake module at the new state machine ARN.
        intake_mod._STATE_MACHINE_ARN = sfn_resp["stateMachineArn"]

        yield {"s3": s3, "table": table, "sfn": sfn}


# ── Helpers to run each stage with the same shape Step Functions would ───────


def _run_intake(s3_client, pdf_key: str) -> dict:
    """Invoke IntakeLambda with an S3 event, return the Step Functions input
    it emitted. Mirrors the JSON passed via start_execution(input=...)."""
    s3_event = {
        "Records": [{
            "s3": {
                "bucket": {"name": _BUCKET},
                "object": {"key": pdf_key, "size": 1024},
            }
        }]
    }
    result = intake_mod.handler(s3_event, _LC)
    assert result["statusCode"] == 200

    # Read back what Intake actually passed to start_execution so we test the
    # real handoff keys, not a hand-constructed dict.
    sfn = boto3.client("stepfunctions", region_name="us-east-1")
    executions = sfn.list_executions(
        stateMachineArn=os.environ["STATE_MACHINE_ARN"]
    )["executions"]
    assert len(executions) == 1
    exec_desc = sfn.describe_execution(executionArn=executions[0]["executionArn"])
    return json.loads(exec_desc["input"])


def _run_extract(sfn_input: dict) -> dict:
    """Invoke ExtractLambda with the SFN input dict Intake produced."""
    fake_image = Image.new("RGB", (850, 1100), color="white")
    mock = _bedrock_mock()
    with patch.object(extract_mod, "_bedrock", mock), \
         patch.object(extract_mod, "convert_from_path", return_value=[fake_image]):
        return extract_mod.handler(sfn_input, _LC)


def _run_aggregate(applicationId: str, extract_out: dict) -> dict:
    """Invoke AggregateLambda with the shaped input Step Functions would send
    per the infra/stacks/workflow.py TaskInput definition."""
    shaped = {
        "applicationId": applicationId,
        "extraction_s3_key": extract_out["extraction_s3_key"],
        "bucket": _BUCKET,
    }
    return aggregate_mod.handler(shaped, _LC)


def _run_validate(applicationId: str, aggregate_out: dict) -> dict:
    shaped = {
        "applicationId": applicationId,
        "aggregation_s3_key": aggregate_out["aggregation_s3_key"],
    }
    return rule_engine_mod.handler(shaped, _LC)


def _run_queue_for_review(applicationId: str, validate_out: dict) -> dict:
    shaped = {
        "applicationId": applicationId,
        "flag_count": validate_out["flag_count"],
    }
    return notify_mod.handler(shaped, _LC)


# Minimal Lambda context for direct invocation.
class _LambdaContext:
    function_name = "test-function"
    memory_limit_in_mb = 128
    invoked_function_arn = "arn:aws:lambda:us-east-1:123456789012:function:test"
    aws_request_id = "test-request-id"


_LC = _LambdaContext()


# ── Key-name contract tests ──────────────────────────────────────────────────


def test_intake_emits_s3_key_snake_case(aws_env):
    """Intake must emit s3_key (snake_case) in the Step Functions input so
    Extract — which reads event["s3_key"] — finds it."""
    pdf_key = "uploads/APP-KEY/transcript.pdf"
    aws_env["s3"].put_object(Bucket=_BUCKET, Key=pdf_key, Body=b"%PDF-1.4\n%EOF")

    sfn_input = _run_intake(aws_env["s3"], pdf_key)

    # Hard contract: the key must be exactly "s3_key", not "s3Key".
    assert "s3_key" in sfn_input
    assert "s3Key" not in sfn_input
    assert sfn_input["s3_key"] == pdf_key
    assert "applicationId" in sfn_input
    assert "bucket" in sfn_input


def test_extract_returns_extraction_s3_key(aws_env):
    """Extract must return extraction_s3_key (snake_case) for Aggregate to read
    via the workflow's ResultPath merge."""
    pdf_key = "uploads/APP-EXT/transcript.pdf"
    aws_env["s3"].put_object(Bucket=_BUCKET, Key=pdf_key, Body=b"pdf")

    sfn_input = _run_intake(aws_env["s3"], pdf_key)
    extract_out = _run_extract(sfn_input)

    assert "extraction_s3_key" in extract_out
    assert extract_out["extraction_s3_key"].startswith("processed/")
    assert extract_out["extraction_s3_key"].endswith(".json")


def test_aggregate_reads_extraction_s3_key(aws_env):
    """Aggregate must accept {applicationId, extraction_s3_key} and return
    {applicationId, aggregation_s3_key}."""
    pdf_key = "uploads/APP-AGG/transcript.pdf"
    aws_env["s3"].put_object(Bucket=_BUCKET, Key=pdf_key, Body=b"pdf")

    sfn_input = _run_intake(aws_env["s3"], pdf_key)
    extract_out = _run_extract(sfn_input)
    aggregate_out = _run_aggregate(sfn_input["applicationId"], extract_out)

    assert "aggregation_s3_key" in aggregate_out
    assert "applicationId" in aggregate_out
    assert aggregate_out["aggregation_s3_key"] == (
        f"processed/{sfn_input['applicationId']}/aggregation.json"
    )


def test_validate_reads_aggregation_s3_key(aws_env):
    """Validate must accept {applicationId, aggregation_s3_key} and return
    flag_count at the top level for QueueForReview."""
    pdf_key = "uploads/APP-VAL/transcript.pdf"
    aws_env["s3"].put_object(Bucket=_BUCKET, Key=pdf_key, Body=b"pdf")

    sfn_input = _run_intake(aws_env["s3"], pdf_key)
    extract_out = _run_extract(sfn_input)
    aggregate_out = _run_aggregate(sfn_input["applicationId"], extract_out)
    validate_out = _run_validate(sfn_input["applicationId"], aggregate_out)

    assert "flag_count" in validate_out
    assert isinstance(validate_out["flag_count"], int)
    assert "flags" in validate_out


def test_queue_for_review_accepts_flag_count(aws_env):
    """QueueForReview must accept {applicationId, flag_count} and update the
    METADATA record to READY_FOR_REVIEW."""
    pdf_key = "uploads/APP-QUE/transcript.pdf"
    aws_env["s3"].put_object(Bucket=_BUCKET, Key=pdf_key, Body=b"pdf")

    sfn_input = _run_intake(aws_env["s3"], pdf_key)
    extract_out = _run_extract(sfn_input)
    aggregate_out = _run_aggregate(sfn_input["applicationId"], extract_out)
    validate_out = _run_validate(sfn_input["applicationId"], aggregate_out)
    queue_out = _run_queue_for_review(sfn_input["applicationId"], validate_out)

    assert queue_out["status"] == "READY_FOR_REVIEW"
    assert queue_out["flag_count"] == validate_out["flag_count"]

    # Final DynamoDB state: METADATA must reflect READY_FOR_REVIEW.
    item = aws_env["table"].get_item(
        Key={"PK": f"APP#{sfn_input['applicationId']}", "SK": "METADATA"}
    )["Item"]
    assert item["status"] == "READY_FOR_REVIEW"
    assert int(item["flag_count"]) == validate_out["flag_count"]


# ── Full pipeline happy path ─────────────────────────────────────────────────


def test_full_pipeline_clean_transcript_zero_flags(aws_env):
    """End-to-end: a clean transcript must flow through every stage with zero
    flags fired. A regression in any boundary key name breaks this test."""
    pdf_key = "uploads/APP-E2E/transcript.pdf"
    aws_env["s3"].put_object(Bucket=_BUCKET, Key=pdf_key, Body=b"pdf")

    sfn_input = _run_intake(aws_env["s3"], pdf_key)
    extract_out = _run_extract(sfn_input)
    aggregate_out = _run_aggregate(sfn_input["applicationId"], extract_out)
    validate_out = _run_validate(sfn_input["applicationId"], aggregate_out)
    queue_out = _run_queue_for_review(sfn_input["applicationId"], validate_out)

    assert queue_out["status"] == "READY_FOR_REVIEW"
    # Clean transcript: no PHYS/CONT/PROG rules should fire.
    assert validate_out["flag_count"] == 0

    # Aggregation JSON exists at the expected S3 path, has applicationId,
    # and contains the flattened top-level fields.
    aggregation = json.loads(
        aws_env["s3"].get_object(
            Bucket=_BUCKET, Key=aggregate_out["aggregation_s3_key"]
        )["Body"].read()
    )
    assert aggregation["applicationId"] == sfn_input["applicationId"]
    assert aggregation["seal_type"] == "embossed"
    assert aggregation["accreditation_claim"] == "ACEN"
    assert sorted(aggregation["required_nursing_domains_present"]) == sorted([
        "adult_med_surg", "obstetrics", "pediatrics",
        "psychiatric", "gerontology", "community_health",
    ])


# ── GSI1-ReviewQueue queryability ────────────────────────────────────────────


def test_gsi1_review_queue_populated_after_pipeline(aws_env):
    """After QueueForReview, the application must appear in GSI1-ReviewQueue
    when queried with status=READY_FOR_REVIEW — the same query the Dashboard
    API's GET /applications uses.  This test would have caught the missing
    submission_ts bug."""
    from boto3.dynamodb.conditions import Key

    pdf_key = "uploads/APP-GSI/transcript.pdf"
    aws_env["s3"].put_object(Bucket=_BUCKET, Key=pdf_key, Body=b"pdf")

    sfn_input = _run_intake(aws_env["s3"], pdf_key)
    extract_out = _run_extract(sfn_input)
    aggregate_out = _run_aggregate(sfn_input["applicationId"], extract_out)
    validate_out = _run_validate(sfn_input["applicationId"], aggregate_out)
    _run_queue_for_review(sfn_input["applicationId"], validate_out)

    # Query GSI1 exactly as the Dashboard API does.
    result = aws_env["table"].query(
        IndexName="GSI1-ReviewQueue",
        KeyConditionExpression=Key("status").eq("READY_FOR_REVIEW"),
        ScanIndexForward=True,
    )

    assert result["Count"] >= 1
    app_ids = [item["applicationId"] for item in result["Items"]]
    assert sfn_input["applicationId"] in app_ids

"""Integration tests for RuleEngineLambda handler.

Tests run against moto-mocked S3 and DynamoDB — no real AWS credentials needed.

Coverage:
- Clean baseline aggregation.json produces zero flags
- Fraud-laden aggregation.json (Case B + diploma mill + cross-doc mismatches)
  produces multiple flags
- Each flag is persisted to DynamoDB with correct PK/SK and required fields
- Handler returns the correct summary shape
- source_location is preserved when present
- Missing aggregation.json causes the handler to propagate an exception
"""

import json
import os
import sys

import importlib.util

import boto3
import pytest
from moto import mock_aws

# Fake credentials before any boto3 import
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("TABLE_NAME", "msbn-applications")
os.environ.setdefault("BUCKET_NAME", "msbn-transcripts-test")

_HANDLER_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "../../services/rule_engine")
)
# Insert so the rules subpackage is importable by the handler module
if _HANDLER_DIR not in sys.path:
    sys.path.insert(0, _HANDLER_DIR)

# Import handler by absolute path to avoid collision with other service handler.py files
_spec = importlib.util.spec_from_file_location(
    "rule_engine_handler",
    os.path.join(_HANDLER_DIR, "handler.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)

from tests.rule_engine.fixtures import CLEAN_BASELINE, FRAUD_CASE_B  # noqa: E402

handler = _mod.handler

_TABLE_NAME = "msbn-applications"
_BUCKET_NAME = "msbn-transcripts-test"


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def aws_resources():
    """Moto-backed S3 bucket and DynamoDB table for one test."""
    with mock_aws():
        # S3
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket=_BUCKET_NAME)

        # DynamoDB
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
        yield {"s3": s3, "table": table}


def _put_aggregation(s3_client, agg: dict) -> str:
    """Upload an aggregation dict to the mock S3 bucket; return the S3 key."""
    app_id = agg["applicationId"]
    key = f"processed/{app_id}/aggregation.json"
    s3_client.put_object(
        Bucket=_BUCKET_NAME,
        Key=key,
        Body=json.dumps(agg).encode("utf-8"),
    )
    return key


def _make_event(app_id: str, s3_key: str) -> dict:
    return {"applicationId": app_id, "aggregation_s3_key": s3_key}


def _scan_flags(table, app_id: str) -> list[dict]:
    """Return all FLAG items for an application from DynamoDB."""
    result = table.query(
        KeyConditionExpression=boto3.dynamodb.conditions.Key("PK").eq(
            f"APP#{app_id}"
        )
        & boto3.dynamodb.conditions.Key("SK").begins_with("FLAG#"),
    )
    return result["Items"]


# ── Happy path: clean baseline fires zero flags ───────────────────────────────


def test_clean_baseline_produces_zero_flags(aws_resources, lambda_context):
    """A well-formed transcript with no anomalies must produce no flags."""
    s3_key = _put_aggregation(aws_resources["s3"], CLEAN_BASELINE)
    event = _make_event(CLEAN_BASELINE["applicationId"], s3_key)

    result = handler(event, lambda_context)

    assert result["applicationId"] == CLEAN_BASELINE["applicationId"]
    assert result["flag_count"] == 0
    assert result["flags"] == []

    db_flags = _scan_flags(aws_resources["table"], CLEAN_BASELINE["applicationId"])
    assert db_flags == []


# ── Fraud case: multiple flags fire ───────────────────────────────────────────


def test_fraud_case_b_produces_multiple_flags(aws_resources, lambda_context):
    """Fraud-laden aggregation.json must fire multiple flags."""
    s3_key = _put_aggregation(aws_resources["s3"], FRAUD_CASE_B)
    event = _make_event(FRAUD_CASE_B["applicationId"], s3_key)

    result = handler(event, lambda_context)

    assert result["flag_count"] > 5
    rule_codes = {f["rule_code"] for f in result["flags"]}
    # Check that representative rules across all single-document categories fired.
    # CROSS_001/002/003 are deferred to Phase 4 (transcript-only POC scope).
    assert "PHYS_001" in rule_codes
    assert "PHYS_002" in rule_codes
    assert "CONT_003" in rule_codes


# ── DynamoDB persistence ───────────────────────────────────────────────────────


def test_flags_written_to_dynamodb(aws_resources, lambda_context):
    """Every flag returned must be persisted as a DynamoDB FLAG item."""
    s3_key = _put_aggregation(aws_resources["s3"], FRAUD_CASE_B)
    event = _make_event(FRAUD_CASE_B["applicationId"], s3_key)

    result = handler(event, lambda_context)

    db_flags = _scan_flags(aws_resources["table"], FRAUD_CASE_B["applicationId"])
    assert len(db_flags) == result["flag_count"]


def test_dynamodb_flag_item_has_required_fields(aws_resources, lambda_context):
    """Each DynamoDB FLAG item must contain all required fields."""
    agg = {
        **CLEAN_BASELINE,
        "applicationId": "APP-FIELD-CHECK",
        "seal_quality": "pixelated",  # fire PHYS_001
    }
    s3_key = _put_aggregation(aws_resources["s3"], agg)
    result = handler(_make_event("APP-FIELD-CHECK", s3_key), lambda_context)

    assert result["flag_count"] >= 1
    db_flags = _scan_flags(aws_resources["table"], "APP-FIELD-CHECK")
    flag = db_flags[0]

    assert flag["PK"] == "APP#APP-FIELD-CHECK"
    assert flag["SK"].startswith("FLAG#")
    assert flag["entity_type"] == "FLAG"
    assert flag["applicationId"] == "APP-FIELD-CHECK"
    assert flag["rule_code"]
    assert flag["rule_description"]
    assert flag["severity"] in ("high", "medium", "low")
    assert flag["category"].startswith("SP-")
    assert flag["rationale"]
    assert flag["timestamp"]


def test_dynamodb_flag_sk_includes_rule_code(aws_resources, lambda_context):
    """SK must encode the rule code: FLAG#<rule_code>#<seq>."""
    agg = {**CLEAN_BASELINE, "applicationId": "APP-SK-CHECK", "seal_quality": "pixelated"}
    s3_key = _put_aggregation(aws_resources["s3"], agg)
    handler(_make_event("APP-SK-CHECK", s3_key), lambda_context)

    db_flags = _scan_flags(aws_resources["table"], "APP-SK-CHECK")
    phys_001 = next(f for f in db_flags if f["rule_code"] == "PHYS_001")
    assert "PHYS_001" in phys_001["SK"]


def test_source_location_stored_when_present(aws_resources, lambda_context):
    """If source_location is present in the flag, it must be stored in DynamoDB."""
    agg = {
        **CLEAN_BASELINE,
        "applicationId": "APP-SRC-LOC",
        "seal_quality": "pixelated",
        "seal_quality_source": {"page_number": 1, "text_spans": ["logo area"]},
    }
    s3_key = _put_aggregation(aws_resources["s3"], agg)
    handler(_make_event("APP-SRC-LOC", s3_key), lambda_context)

    db_flags = _scan_flags(aws_resources["table"], "APP-SRC-LOC")
    phys_001 = next(f for f in db_flags if f["rule_code"] == "PHYS_001")
    assert "source_location" in phys_001
    assert phys_001["source_location"]["page_number"] == 1


# ── Return value shape ─────────────────────────────────────────────────────────


def test_handler_return_shape(aws_resources, lambda_context):
    """Handler must return applicationId, flag_count, and flags list."""
    s3_key = _put_aggregation(aws_resources["s3"], CLEAN_BASELINE)
    result = handler(
        _make_event(CLEAN_BASELINE["applicationId"], s3_key), lambda_context
    )
    assert "applicationId" in result
    assert "flag_count" in result
    assert "flags" in result
    assert isinstance(result["flags"], list)
    assert result["flag_count"] == len(result["flags"])


def test_each_flag_in_return_has_required_keys(aws_resources, lambda_context):
    """Each flag dict in the return value must have the standard fields."""
    agg = {**CLEAN_BASELINE, "applicationId": "APP-KEYS-CHECK", "seal_quality": "pixelated"}
    s3_key = _put_aggregation(aws_resources["s3"], agg)
    result = handler(_make_event("APP-KEYS-CHECK", s3_key), lambda_context)

    assert result["flag_count"] >= 1
    for flag in result["flags"]:
        for key in ("rule_code", "rule_description", "severity", "category",
                    "rationale", "source_location", "timestamp"):
            assert key in flag, f"Missing key '{key}' in flag: {flag}"


# ── Error propagation ──────────────────────────────────────────────────────────


def test_missing_s3_key_raises(aws_resources, lambda_context):
    """If aggregation.json does not exist, handler must raise (not silently succeed)."""
    event = {
        "applicationId": "APP-MISSING",
        "aggregation_s3_key": "processed/APP-MISSING/aggregation.json",
    }
    with pytest.raises(Exception):
        handler(event, lambda_context)

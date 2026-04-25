"""Tests for DashboardApiLambda (services/dashboard_api/handler.py).

Covers:
- GET /applications: happy path, pagination (limit, cursor), empty queue
- GET /applications/{id}: full detail with flags, 404, missing ID
- POST /applications/{id}/decision: happy path, OVERRIDE requires notes,
  unknown ruleCode, missing fields, invalid decision values, 404
- GET /applications/{id}/audit: newest-first ordering, empty trail, 404
- Auth: missing reviewer email returns 403
- CORS headers on all responses
"""

import base64
import importlib.util
import json
import os
from urllib.parse import parse_qs, urlparse

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("TABLE_NAME", "msbn-applications")
os.environ.setdefault("BUCKET_NAME", "msbn-transcripts-test")

_HANDLER_PATH = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "../../services/dashboard_api/handler.py")
)
_spec = importlib.util.spec_from_file_location("dashboard_api_handler", _HANDLER_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
handler = _mod.handler

_TABLE_NAME = "msbn-applications"
_REVIEWER_EMAIL = "reviewer@msbn.ms.gov"


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_event(
    route_key: str,
    *,
    path_params: dict | None = None,
    query_params: dict | None = None,
    body: dict | None = None,
    email: str = _REVIEWER_EMAIL,
) -> dict:
    """Build an API Gateway HTTP API v2 proxy event."""
    event = {
        "version": "2.0",
        "routeKey": route_key,
        "rawPath": route_key.split(" ", 1)[-1] if " " in route_key else "/",
        "requestContext": {
            "http": {
                "method": route_key.split(" ", 1)[0] if " " in route_key else "GET",
                "path": route_key.split(" ", 1)[-1] if " " in route_key else "/",
            },
            "authorizer": {"jwt": {"claims": {"email": email, "sub": "sub-001"}}},
        },
    }
    if path_params:
        event["pathParameters"] = path_params
    if query_params:
        event["queryStringParameters"] = query_params
    if body is not None:
        event["body"] = json.dumps(body)
    return event


def _make_event_no_auth(route_key: str) -> dict:
    """Build an event with no authorizer claims."""
    return {
        "version": "2.0",
        "routeKey": route_key,
        "rawPath": "/applications",
        "requestContext": {"http": {"method": "GET", "path": "/applications"}},
    }


@pytest.fixture()
def dynamo_table():
    """Moto-backed DynamoDB table with GSI1-ReviewQueue for one test."""
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
        yield table


def _seed_application(table, app_id: str, **overrides) -> None:
    """Write a METADATA record with GSI1 attributes populated."""
    item = {
        "PK": f"APP#{app_id}",
        "SK": "METADATA",
        "entity_type": "METADATA",
        "applicationId": app_id,
        "status": "READY_FOR_REVIEW",
        "submission_ts": "2026-04-14T18:32:01+00:00",
        "uploadedAt": "2026-04-14T18:32:01+00:00",
        "applicant_name": "Jane Smith",
        "institution": "University of Southern Mississippi",
        "flag_count": 2,
        "high_severity_count": 1,
        "s3_key": "uploads/transcript_smith.pdf",
        "originalFilename": "transcript_smith.pdf",
    }
    item.update(overrides)
    table.put_item(Item=item)


def _seed_flag(
    table,
    app_id: str,
    rule_code: str = "CONT_005",
    seq: str = "001",
    severity: str = "High",
    rationale: str = "GPA mismatch",
) -> None:
    """Write a FLAG record."""
    table.put_item(
        Item={
            "PK": f"APP#{app_id}",
            "SK": f"FLAG#{rule_code}#{seq}",
            "entity_type": "FLAG",
            "rule_code": rule_code,
            "severity": severity,
            "rationale": rationale,
            "source_location": {"page_number": 2, "text_spans": ["Overall GPA: 3.4"]},
            "reviewer_status": "OPEN",
            "reviewer_id": None,
            "reviewer_ts": None,
            "reviewer_notes": None,
        }
    )


def _seed_document(table, app_id: str) -> None:
    """Write a DOCUMENT#TRANSCRIPT record."""
    table.put_item(
        Item={
            "PK": f"APP#{app_id}",
            "SK": "DOCUMENT#TRANSCRIPT",
            "entity_type": "DOCUMENT",
            "doc_type": "TRANSCRIPT",
            "status": "EXTRACTED",
            "s3_extraction_key": f"processed/{app_id}/extraction_TRANSCRIPT.json",
            "model_id": "amazon.nova-lite-v1:0",
            "page_count": 4,
        }
    )


def _seed_audit(table, app_id: str, timestamp: str, event_type: str = "STATUS_CHANGED") -> None:
    """Write an AUDIT record."""
    table.put_item(
        Item={
            "PK": f"APP#{app_id}",
            "SK": f"AUDIT#{timestamp}",
            "entity_type": "AUDIT",
            "actor": "system",
            "event_type": event_type,
            "previous_state": {"status": "EVALUATING"},
            "new_state": {"status": "READY_FOR_REVIEW"},
            "timestamp": timestamp,
            "applicationId": app_id,
        }
    )


def _parse_response(response: dict) -> dict:
    """Parse the JSON body from a Lambda response."""
    return json.loads(response["body"])


# ── Auth ──────────────────────────────────────────────────────────────────────


def test_missing_auth_returns_403(dynamo_table, lambda_context):
    """Requests without Cognito JWT claims must be rejected."""
    event = _make_event_no_auth("GET /applications")
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 403
    assert "reviewer identity" in _parse_response(resp)["error"].lower()


def test_cors_headers_on_every_response(dynamo_table, lambda_context):
    """Every response must include CORS headers."""
    event = _make_event("GET /applications")
    resp = handler(event, lambda_context)
    assert resp["headers"]["Access-Control-Allow-Origin"] == "*"
    assert "Authorization" in resp["headers"]["Access-Control-Allow-Headers"]


def test_options_returns_200(dynamo_table, lambda_context):
    """OPTIONS preflight must return 200 without requiring auth."""
    event = _make_event_no_auth("OPTIONS /applications")
    event["routeKey"] = "OPTIONS /applications"
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 200


# ── GET /applications ─────────────────────────────────────────────────────────


def test_list_applications_happy_path(dynamo_table, lambda_context):
    """List endpoint returns applications from the review queue."""
    _seed_application(dynamo_table, "APP-001")
    _seed_application(
        dynamo_table,
        "APP-002",
        applicant_name="John Doe",
        submission_ts="2026-04-15T10:00:00+00:00",
    )

    event = _make_event("GET /applications")
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 200

    body = _parse_response(resp)
    assert len(body["items"]) == 2
    assert body["items"][0]["applicationId"] == "APP-001"
    assert body["items"][1]["applicationId"] == "APP-002"


def test_list_applications_response_shape(dynamo_table, lambda_context):
    """Each item must have the expected fields."""
    _seed_application(dynamo_table, "APP-010")

    event = _make_event("GET /applications")
    body = _parse_response(handler(event, lambda_context))
    item = body["items"][0]

    assert item["applicationId"] == "APP-010"
    assert item["applicantName"] == "Jane Smith"
    assert item["institution"] == "University of Southern Mississippi"
    assert item["submittedAt"] is not None


def test_list_applications_missing_metadata_stays_blank(
    dynamo_table, lambda_context
):
    """Missing extracted values must not be replaced with fake display text."""
    _seed_application(
        dynamo_table,
        "APP-BLANK",
        applicant_name="",
        institution="",
        country="",
    )

    event = _make_event("GET /applications")
    body = _parse_response(handler(event, lambda_context))
    item = body["items"][0]

    assert item["applicantName"] == ""
    assert item["institution"] == ""
    assert item["country"] == ""
    assert item["flagCount"] == 2
    assert item["highestSeverity"] == "High"
    assert item["status"] == "READY_FOR_REVIEW"


def test_list_applications_empty_queue(dynamo_table, lambda_context):
    """Empty queue must return an empty items list."""
    event = _make_event("GET /applications")
    body = _parse_response(handler(event, lambda_context))
    assert body["items"] == []
    assert body["nextCursor"] is None


def test_list_applications_pagination_limit(dynamo_table, lambda_context):
    """Limit param restricts the number of returned items."""
    for i in range(5):
        _seed_application(
            dynamo_table,
            f"APP-P{i:02d}",
            submission_ts=f"2026-04-{14 + i}T10:00:00+00:00",
        )

    event = _make_event(
        "GET /applications", query_params={"limit": "2"}
    )
    body = _parse_response(handler(event, lambda_context))
    assert len(body["items"]) == 2
    assert body["nextCursor"] is not None


def test_list_applications_pagination_cursor(dynamo_table, lambda_context):
    """Cursor must allow fetching the next page."""
    for i in range(4):
        _seed_application(
            dynamo_table,
            f"APP-C{i:02d}",
            submission_ts=f"2026-04-{14 + i}T10:00:00+00:00",
        )

    # Page 1
    event1 = _make_event("GET /applications", query_params={"limit": "2"})
    body1 = _parse_response(handler(event1, lambda_context))
    assert len(body1["items"]) == 2
    cursor = body1["nextCursor"]
    assert cursor is not None

    # Page 2
    event2 = _make_event(
        "GET /applications", query_params={"limit": "2", "cursor": cursor}
    )
    body2 = _parse_response(handler(event2, lambda_context))
    assert len(body2["items"]) == 2

    # No overlap
    ids_page1 = {i["applicationId"] for i in body1["items"]}
    ids_page2 = {i["applicationId"] for i in body2["items"]}
    assert ids_page1.isdisjoint(ids_page2)


def test_list_applications_invalid_cursor(dynamo_table, lambda_context):
    """Invalid cursor must return 400."""
    event = _make_event(
        "GET /applications", query_params={"cursor": "not-base64-json"}
    )
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 400


def test_list_applications_invalid_limit(dynamo_table, lambda_context):
    """Non-integer limit must return 400."""
    event = _make_event(
        "GET /applications", query_params={"limit": "abc"}
    )
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 400


def test_list_highest_severity_no_flags(dynamo_table, lambda_context):
    """Applications with zero flags should have null highestSeverity."""
    _seed_application(dynamo_table, "APP-S00", flag_count=0, high_severity_count=0)
    body = _parse_response(
        handler(_make_event("GET /applications"), lambda_context)
    )
    assert body["items"][0]["highestSeverity"] is None


def test_list_highest_severity_medium(dynamo_table, lambda_context):
    """Applications with flags but no high-severity flags show Medium."""
    _seed_application(dynamo_table, "APP-S01", flag_count=3, high_severity_count=0)
    body = _parse_response(
        handler(_make_event("GET /applications"), lambda_context)
    )
    assert body["items"][0]["highestSeverity"] == "Medium"


# ── GET /applications/{id} ───────────────────────────────────────────────────


def test_get_application_happy_path(dynamo_table, lambda_context):
    """Detail endpoint returns metadata, extraction, and flags."""
    _seed_application(dynamo_table, "APP-D01")
    _seed_document(dynamo_table, "APP-D01")
    _seed_flag(dynamo_table, "APP-D01", "CONT_005", "001", "High")
    _seed_flag(dynamo_table, "APP-D01", "PHYS_001", "001", "Medium", "Seal pixelated")

    event = _make_event(
        "GET /applications/{id}", path_params={"id": "APP-D01"}
    )
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 200

    body = _parse_response(resp)
    assert body["applicationId"] == "APP-D01"
    assert body["metadata"]["status"] == "READY_FOR_REVIEW"
    assert body["extraction"]["doc_type"] == "TRANSCRIPT"
    assert len(body["flags"]) == 2


def test_get_application_includes_transcript_url(dynamo_table, lambda_context):
    """Detail endpoint returns a short-lived signed URL for the uploaded PDF."""
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="msbn-transcripts-test")
    s3.put_object(
        Bucket="msbn-transcripts-test",
        Key="uploads/transcript_smith.pdf",
        Body=b"%PDF-1.4",
        ContentType="application/pdf",
    )
    _seed_application(dynamo_table, "APP-D01")

    event = _make_event(
        "GET /applications/{id}", path_params={"id": "APP-D01"}
    )
    body = _parse_response(handler(event, lambda_context))

    parsed = urlparse(body["transcriptUrl"])
    assert parsed.netloc.startswith("msbn-transcripts-test.s3.")
    assert parsed.path.endswith("/uploads/transcript_smith.pdf")
    assert parse_qs(parsed.query)["Expires"]


def test_get_application_missing_transcript_url_is_null(dynamo_table, lambda_context):
    """Deleted S3 objects must not produce a broken preview URL."""
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="msbn-transcripts-test")
    _seed_application(dynamo_table, "APP-D01")

    event = _make_event(
        "GET /applications/{id}", path_params={"id": "APP-D01"}
    )
    body = _parse_response(handler(event, lambda_context))

    assert body["transcriptUrl"] is None


def test_get_application_flag_status_pending(dynamo_table, lambda_context):
    """OPEN reviewer_status must be mapped to PENDING in the response."""
    _seed_application(dynamo_table, "APP-D02")
    _seed_flag(dynamo_table, "APP-D02")

    event = _make_event(
        "GET /applications/{id}", path_params={"id": "APP-D02"}
    )
    body = _parse_response(handler(event, lambda_context))
    assert body["flags"][0]["status"] == "PENDING"


def test_get_application_no_extraction(dynamo_table, lambda_context):
    """Application without DOCUMENT#TRANSCRIPT should return null extraction."""
    _seed_application(dynamo_table, "APP-D03")

    event = _make_event(
        "GET /applications/{id}", path_params={"id": "APP-D03"}
    )
    body = _parse_response(handler(event, lambda_context))
    assert body["extraction"] is None


def test_get_application_no_flags(dynamo_table, lambda_context):
    """Application with zero flags should return empty flags list."""
    _seed_application(dynamo_table, "APP-D04")

    event = _make_event(
        "GET /applications/{id}", path_params={"id": "APP-D04"}
    )
    body = _parse_response(handler(event, lambda_context))
    assert body["flags"] == []


def test_get_application_404(dynamo_table, lambda_context):
    """Non-existent application must return 404."""
    event = _make_event(
        "GET /applications/{id}", path_params={"id": "NONEXISTENT"}
    )
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 404


def test_get_application_missing_id(dynamo_table, lambda_context):
    """Missing path parameter must return 400."""
    event = _make_event("GET /applications/{id}")
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 400


# ── POST /applications/{id}/decision ─────────────────────────────────────────


def _decision_body(
    flag_decisions: list | None = None,
    overall: str = "READY_FOR_LICENSING_REVIEW",
) -> dict:
    if flag_decisions is None:
        flag_decisions = [
            {"ruleCode": "CONT_005", "decision": "CONFIRM", "notes": ""}
        ]
    return {"flagDecisions": flag_decisions, "overallDecision": overall}


def test_decision_happy_path(dynamo_table, lambda_context):
    """Submitting a valid decision returns 200 with auditRecordIds."""
    _seed_application(dynamo_table, "APP-X01")
    _seed_flag(dynamo_table, "APP-X01", "CONT_005")

    event = _make_event(
        "POST /applications/{id}/decision",
        path_params={"id": "APP-X01"},
        body=_decision_body(),
    )
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 200

    body = _parse_response(resp)
    assert body["applicationId"] == "APP-X01"
    assert body["updatedAt"]
    # One per flag decision + one for overall decision
    assert len(body["auditRecordIds"]) == 2


def test_decision_updates_flag_status(dynamo_table, lambda_context):
    """After CONFIRM, FLAG reviewer_status must be CONFIRMED."""
    _seed_application(dynamo_table, "APP-X02")
    _seed_flag(dynamo_table, "APP-X02", "CONT_005")

    event = _make_event(
        "POST /applications/{id}/decision",
        path_params={"id": "APP-X02"},
        body=_decision_body(),
    )
    handler(event, lambda_context)

    flag = dynamo_table.get_item(
        Key={"PK": "APP#APP-X02", "SK": "FLAG#CONT_005#001"}
    )["Item"]
    assert flag["reviewer_status"] == "CONFIRMED"
    assert flag["reviewer_id"] == _REVIEWER_EMAIL
    assert flag["reviewer_ts"]


def test_decision_override_updates_flag(dynamo_table, lambda_context):
    """OVERRIDE decision must set reviewer_status to OVERRIDDEN."""
    _seed_application(dynamo_table, "APP-X03")
    _seed_flag(dynamo_table, "APP-X03", "PHYS_001")

    body = _decision_body(
        flag_decisions=[
            {
                "ruleCode": "PHYS_001",
                "decision": "OVERRIDE",
                "notes": "Seal is legitimate upon manual inspection",
            }
        ]
    )
    event = _make_event(
        "POST /applications/{id}/decision",
        path_params={"id": "APP-X03"},
        body=body,
    )
    handler(event, lambda_context)

    flag = dynamo_table.get_item(
        Key={"PK": "APP#APP-X03", "SK": "FLAG#PHYS_001#001"}
    )["Item"]
    assert flag["reviewer_status"] == "OVERRIDDEN"
    assert flag["reviewer_notes"] == "Seal is legitimate upon manual inspection"


def test_decision_updates_metadata_status(dynamo_table, lambda_context):
    """Overall decision must update METADATA status."""
    _seed_application(dynamo_table, "APP-X04")
    _seed_flag(dynamo_table, "APP-X04", "CONT_005")

    event = _make_event(
        "POST /applications/{id}/decision",
        path_params={"id": "APP-X04"},
        body=_decision_body(overall="RETURN_TO_APPLICANT"),
    )
    handler(event, lambda_context)

    meta = dynamo_table.get_item(
        Key={"PK": "APP#APP-X04", "SK": "METADATA"}
    )["Item"]
    assert meta["status"] == "RETURN_TO_APPLICANT"


def test_decision_writes_audit_records(dynamo_table, lambda_context):
    """Decision must write AUDIT records for each flag and the overall decision."""
    _seed_application(dynamo_table, "APP-X05")
    _seed_flag(dynamo_table, "APP-X05", "CONT_005")
    _seed_flag(dynamo_table, "APP-X05", "PHYS_001")

    body = _decision_body(
        flag_decisions=[
            {"ruleCode": "CONT_005", "decision": "CONFIRM", "notes": ""},
            {
                "ruleCode": "PHYS_001",
                "decision": "OVERRIDE",
                "notes": "Verified manually",
            },
        ],
        overall="READY_FOR_LICENSING_REVIEW",
    )
    event = _make_event(
        "POST /applications/{id}/decision",
        path_params={"id": "APP-X05"},
        body=body,
    )
    handler(event, lambda_context)

    audit_resp = dynamo_table.query(
        KeyConditionExpression=(
            boto3.dynamodb.conditions.Key("PK").eq("APP#APP-X05")
            & boto3.dynamodb.conditions.Key("SK").begins_with("AUDIT#")
        ),
    )
    # 2 flag decisions + 1 overall = 3 audit records
    assert len(audit_resp["Items"]) == 3

    event_types = {r["event_type"] for r in audit_resp["Items"]}
    assert "FLAG_CONFIRMED" in event_types
    assert "FLAG_OVERRIDDEN" in event_types
    assert "DECISION_SUBMITTED" in event_types


def test_decision_audit_records_have_reviewer(dynamo_table, lambda_context):
    """AUDIT records from decisions must have the reviewer email as actor."""
    _seed_application(dynamo_table, "APP-X06")
    _seed_flag(dynamo_table, "APP-X06", "CONT_005")

    event = _make_event(
        "POST /applications/{id}/decision",
        path_params={"id": "APP-X06"},
        body=_decision_body(),
    )
    handler(event, lambda_context)

    audit_resp = dynamo_table.query(
        KeyConditionExpression=(
            boto3.dynamodb.conditions.Key("PK").eq("APP#APP-X06")
            & boto3.dynamodb.conditions.Key("SK").begins_with("AUDIT#")
        ),
    )
    for rec in audit_resp["Items"]:
        assert rec["actor"] == _REVIEWER_EMAIL


def test_decision_override_without_notes_rejected(dynamo_table, lambda_context):
    """OVERRIDE without notes must return 400."""
    _seed_application(dynamo_table, "APP-X10")
    _seed_flag(dynamo_table, "APP-X10", "CONT_005")

    body = _decision_body(
        flag_decisions=[
            {"ruleCode": "CONT_005", "decision": "OVERRIDE", "notes": ""}
        ]
    )
    event = _make_event(
        "POST /applications/{id}/decision",
        path_params={"id": "APP-X10"},
        body=body,
    )
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 400
    assert "notes" in _parse_response(resp)["error"].lower()


def test_decision_override_without_notes_key_rejected(dynamo_table, lambda_context):
    """OVERRIDE with missing notes key must return 400."""
    _seed_application(dynamo_table, "APP-X11")
    _seed_flag(dynamo_table, "APP-X11", "CONT_005")

    body = _decision_body(
        flag_decisions=[{"ruleCode": "CONT_005", "decision": "OVERRIDE"}]
    )
    event = _make_event(
        "POST /applications/{id}/decision",
        path_params={"id": "APP-X11"},
        body=body,
    )
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 400


def test_decision_unknown_rule_code(dynamo_table, lambda_context):
    """Flag decision referencing a non-existent rule code must return 400."""
    _seed_application(dynamo_table, "APP-X12")
    _seed_flag(dynamo_table, "APP-X12", "CONT_005")

    body = _decision_body(
        flag_decisions=[
            {"ruleCode": "NONEXISTENT_001", "decision": "CONFIRM", "notes": ""}
        ]
    )
    event = _make_event(
        "POST /applications/{id}/decision",
        path_params={"id": "APP-X12"},
        body=body,
    )
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 400
    assert "NONEXISTENT_001" in _parse_response(resp)["error"]


def test_decision_invalid_overall_decision(dynamo_table, lambda_context):
    """Invalid overallDecision value must return 400."""
    _seed_application(dynamo_table, "APP-X13")
    _seed_flag(dynamo_table, "APP-X13", "CONT_005")

    body = _decision_body(overall="INVALID_STATUS")
    event = _make_event(
        "POST /applications/{id}/decision",
        path_params={"id": "APP-X13"},
        body=body,
    )
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 400
    assert "overallDecision" in _parse_response(resp)["error"]


def test_decision_invalid_flag_decision_value(dynamo_table, lambda_context):
    """Invalid flag decision value (not CONFIRM/OVERRIDE) must return 400."""
    _seed_application(dynamo_table, "APP-X14")
    _seed_flag(dynamo_table, "APP-X14", "CONT_005")

    body = _decision_body(
        flag_decisions=[
            {"ruleCode": "CONT_005", "decision": "APPROVE", "notes": ""}
        ]
    )
    event = _make_event(
        "POST /applications/{id}/decision",
        path_params={"id": "APP-X14"},
        body=body,
    )
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 400


def test_decision_missing_body(dynamo_table, lambda_context):
    """POST without body must return 400."""
    event = _make_event(
        "POST /applications/{id}/decision",
        path_params={"id": "APP-X15"},
    )
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 400


def test_decision_malformed_json(dynamo_table, lambda_context):
    """POST with invalid JSON body must return 400."""
    event = _make_event(
        "POST /applications/{id}/decision",
        path_params={"id": "APP-X16"},
    )
    event["body"] = "not-json"
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 400


def test_decision_empty_flag_decisions(dynamo_table, lambda_context):
    """Empty flagDecisions list must return 400."""
    _seed_application(dynamo_table, "APP-X17")

    body = {"flagDecisions": [], "overallDecision": "READY_FOR_LICENSING_REVIEW"}
    event = _make_event(
        "POST /applications/{id}/decision",
        path_params={"id": "APP-X17"},
        body=body,
    )
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 400


def test_decision_missing_rule_code(dynamo_table, lambda_context):
    """Flag decision without ruleCode must return 400."""
    _seed_application(dynamo_table, "APP-X18")

    body = _decision_body(
        flag_decisions=[{"decision": "CONFIRM", "notes": ""}]
    )
    event = _make_event(
        "POST /applications/{id}/decision",
        path_params={"id": "APP-X18"},
        body=body,
    )
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 400


def test_decision_404(dynamo_table, lambda_context):
    """Decision on non-existent application must return 404."""
    body = _decision_body()
    event = _make_event(
        "POST /applications/{id}/decision",
        path_params={"id": "NONEXISTENT"},
        body=body,
    )
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 404


def test_decision_multiple_flags_same_rule(dynamo_table, lambda_context):
    """Decision must update all FLAG records for the same rule code."""
    _seed_application(dynamo_table, "APP-X20")
    _seed_flag(dynamo_table, "APP-X20", "CONT_005", "001")
    _seed_flag(dynamo_table, "APP-X20", "CONT_005", "002")

    event = _make_event(
        "POST /applications/{id}/decision",
        path_params={"id": "APP-X20"},
        body=_decision_body(),
    )
    handler(event, lambda_context)

    for seq in ("001", "002"):
        flag = dynamo_table.get_item(
            Key={"PK": "APP#APP-X20", "SK": f"FLAG#CONT_005#{seq}"}
        )["Item"]
        assert flag["reviewer_status"] == "CONFIRMED"


# ── GET /applications/{id}/audit ─────────────────────────────────────────────


def test_audit_happy_path(dynamo_table, lambda_context):
    """Audit endpoint returns audit records for an application."""
    _seed_application(dynamo_table, "APP-A01")
    _seed_audit(dynamo_table, "APP-A01", "2026-04-14T18:32:01.000Z")
    _seed_audit(dynamo_table, "APP-A01", "2026-04-14T18:35:44.000Z")

    event = _make_event(
        "GET /applications/{id}/audit", path_params={"id": "APP-A01"}
    )
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 200

    body = _parse_response(resp)
    assert len(body["items"]) == 2


def test_audit_newest_first(dynamo_table, lambda_context):
    """Audit records must be sorted newest first."""
    _seed_application(dynamo_table, "APP-A02")
    _seed_audit(dynamo_table, "APP-A02", "2026-04-14T10:00:00.000Z")
    _seed_audit(dynamo_table, "APP-A02", "2026-04-14T20:00:00.000Z")

    event = _make_event(
        "GET /applications/{id}/audit", path_params={"id": "APP-A02"}
    )
    body = _parse_response(handler(event, lambda_context))

    assert body["items"][0]["timestamp"] == "2026-04-14T20:00:00.000Z"
    assert body["items"][1]["timestamp"] == "2026-04-14T10:00:00.000Z"


def test_audit_response_shape(dynamo_table, lambda_context):
    """Each audit item must have the expected fields."""
    _seed_application(dynamo_table, "APP-A03")
    _seed_audit(dynamo_table, "APP-A03", "2026-04-14T18:32:01.000Z")

    event = _make_event(
        "GET /applications/{id}/audit", path_params={"id": "APP-A03"}
    )
    body = _parse_response(handler(event, lambda_context))
    item = body["items"][0]

    assert "timestamp" in item
    assert "reviewer" in item
    assert "action" in item
    assert "ruleCode" in item
    assert "notes" in item


def test_audit_empty(dynamo_table, lambda_context):
    """Application with no audit records should return empty list."""
    _seed_application(dynamo_table, "APP-A04")

    event = _make_event(
        "GET /applications/{id}/audit", path_params={"id": "APP-A04"}
    )
    body = _parse_response(handler(event, lambda_context))
    assert body["items"] == []


def test_audit_404(dynamo_table, lambda_context):
    """Audit for non-existent application must return 404."""
    event = _make_event(
        "GET /applications/{id}/audit", path_params={"id": "NONEXISTENT"}
    )
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 404


# ── Unknown route ─────────────────────────────────────────────────────────────


def test_unknown_route_returns_404(dynamo_table, lambda_context):
    """Unknown route must return 404."""
    event = _make_event("GET /unknown")
    resp = handler(event, lambda_context)
    assert resp["statusCode"] == 404

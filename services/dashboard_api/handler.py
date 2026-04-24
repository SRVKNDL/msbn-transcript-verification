"""HTTP API handlers for the reviewer dashboard."""

import base64
import json
import logging
import os
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
_TABLE_NAME = os.environ.get("TABLE_NAME", "msbn-applications")

_CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")
_CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": _CORS_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,OPTIONS",
}

_VALID_OVERALL_DECISIONS = {
    "READY_FOR_LICENSING_REVIEW",
    "RETURN_TO_APPLICANT",
    "DENIED",
    "DEFERRED",
}

_VALID_FLAG_DECISIONS = {"CONFIRM", "OVERRIDE"}

_MAX_PAGE_SIZE = 100
_DEFAULT_PAGE_SIZE = 20


class _DecimalEncoder(json.JSONEncoder):
    """Convert DynamoDB Decimal values before JSON serialization."""

    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super().default(o)


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": _CORS_HEADERS,
        "body": json.dumps(body, cls=_DecimalEncoder),
    }


def _get_reviewer_email(event: dict) -> str | None:
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"]["email"]
    except (KeyError, TypeError):
        return None


# Router.


def handler(event: dict, context) -> dict:
    """Route API Gateway HTTP API v2 requests to endpoint handlers."""
    route_key = event.get("routeKey", "")

    logger.info(json.dumps({"routeKey": route_key, "action": "request_received"}))

    if route_key.startswith("OPTIONS"):
        return _response(200, {})

    reviewer_email = _get_reviewer_email(event)
    if not reviewer_email:
        return _response(403, {"error": "Missing reviewer identity"})

    table = _dynamodb.Table(_TABLE_NAME)
    path_params = event.get("pathParameters") or {}

    try:
        if route_key == "GET /applications":
            return _list_applications(event, table)

        if route_key == "GET /applications/{id}":
            return _get_application(path_params.get("id"), table)

        if route_key == "POST /applications/{id}/decision":
            return _post_decision(
                event, path_params.get("id"), reviewer_email, table
            )

        if route_key == "GET /applications/{id}/audit":
            return _get_audit(path_params.get("id"), table)

        return _response(404, {"error": f"Not found: {route_key}"})

    except Exception:
        logger.exception("Unhandled error in DashboardApiLambda")
        return _response(500, {"error": "Internal server error"})


# GET /applications.


def _list_applications(event: dict, table) -> dict:
    """Query GSI1-ReviewQueue for applications with status READY_FOR_REVIEW."""
    params = event.get("queryStringParameters") or {}

    try:
        limit = min(int(params.get("limit", str(_DEFAULT_PAGE_SIZE))), _MAX_PAGE_SIZE)
        if limit < 1:
            return _response(400, {"error": "limit must be >= 1"})
    except ValueError:
        return _response(400, {"error": "limit must be an integer"})

    cursor = params.get("cursor")

    query_kwargs = {
        "IndexName": "GSI1-ReviewQueue",
        "KeyConditionExpression": Key("status").eq("READY_FOR_REVIEW"),
        "ScanIndexForward": True,
        "Limit": limit,
    }

    if cursor:
        try:
            start_key = json.loads(base64.b64decode(cursor))
            query_kwargs["ExclusiveStartKey"] = start_key
        except (ValueError, json.JSONDecodeError):
            return _response(400, {"error": "Invalid cursor"})

    result = table.query(**query_kwargs)

    items = []
    for item in result.get("Items", []):
        high_count = int(item.get("high_severity_count", 0))
        flag_count = int(item.get("flag_count", 0))
        if high_count > 0:
            highest_severity = "High"
        elif flag_count > 0:
            highest_severity = "Medium"
        else:
            highest_severity = None

        items.append(
            {
                "applicationId": item.get("applicationId"),
                "applicantName": item.get("applicant_name"),
                "institution": item.get("institution"),
                "submittedAt": item.get("submission_ts") or item.get("uploadedAt"),
                "flagCount": flag_count,
                "highestSeverity": highest_severity,
                "status": item.get("status"),
            }
        )

    next_cursor = None
    last_key = result.get("LastEvaluatedKey")
    if last_key:
        next_cursor = base64.b64encode(
            json.dumps(last_key).encode()
        ).decode()

    return _response(200, {"items": items, "nextCursor": next_cursor})


# GET /applications/{id}.


def _get_application(app_id: str | None, table) -> dict:
    """Fetch METADATA, DOCUMENT#TRANSCRIPT, and all FLAG records."""
    if not app_id:
        return _response(400, {"error": "Missing application ID"})

    pk = f"APP#{app_id}"

    meta_resp = table.get_item(Key={"PK": pk, "SK": "METADATA"})
    if "Item" not in meta_resp:
        return _response(404, {"error": f"Application {app_id} not found"})

    metadata = meta_resp["Item"]

    doc_resp = table.get_item(Key={"PK": pk, "SK": "DOCUMENT#TRANSCRIPT"})
    extraction = doc_resp.get("Item")

    flag_resp = table.query(
        KeyConditionExpression=Key("PK").eq(pk) & Key("SK").begins_with("FLAG#"),
    )

    flags = []
    for f in flag_resp.get("Items", []):
        reviewer_status = f.get("reviewer_status", "OPEN")
        flags.append(
            {
                "ruleCode": f.get("rule_code"),
                "severity": f.get("severity"),
                "rationale": f.get("rationale"),
                "sourceLocation": f.get("source_location"),
                "status": "PENDING" if reviewer_status == "OPEN" else reviewer_status,
            }
        )

    return _response(
        200,
        {
            "applicationId": app_id,
            "metadata": metadata,
            "extraction": extraction,
            "flags": flags,
        },
    )


# POST /applications/{id}/decision.


def _post_decision(
    event: dict, app_id: str | None, reviewer_email: str, table
) -> dict:
    """Validate and apply flag decisions, write audit records, update status."""
    if not app_id:
        return _response(400, {"error": "Missing application ID"})

    body_str = event.get("body", "")
    if not body_str:
        return _response(400, {"error": "Missing request body"})

    try:
        body = json.loads(body_str)
    except json.JSONDecodeError:
        return _response(400, {"error": "Invalid JSON body"})

    flag_decisions = body.get("flagDecisions")
    overall_decision = body.get("overallDecision")

    if not flag_decisions or not isinstance(flag_decisions, list):
        return _response(
            400, {"error": "flagDecisions is required and must be a non-empty list"}
        )

    if not overall_decision or overall_decision not in _VALID_OVERALL_DECISIONS:
        return _response(
            400,
            {
                "error": (
                    f"overallDecision must be one of: "
                    f"{sorted(_VALID_OVERALL_DECISIONS)}"
                )
            },
        )

    # Validate each flag decision before writing anything.
    for fd in flag_decisions:
        rule_code = fd.get("ruleCode")
        decision = fd.get("decision")
        notes = fd.get("notes", "")

        if not rule_code:
            return _response(
                400, {"error": "Each flagDecision must have a ruleCode"}
            )
        if decision not in _VALID_FLAG_DECISIONS:
            return _response(
                400,
                {"error": f"decision must be CONFIRM or OVERRIDE, got: {decision}"},
            )
        if decision == "OVERRIDE" and not notes:
            return _response(
                400,
                {"error": f"Notes required when overriding flag {rule_code}"},
            )

    pk = f"APP#{app_id}"

    # Verify application exists.
    meta_resp = table.get_item(Key={"PK": pk, "SK": "METADATA"})
    if "Item" not in meta_resp:
        return _response(404, {"error": f"Application {app_id} not found"})

    now = datetime.now(timezone.utc).isoformat()
    audit_record_ids = []

    # Process each flag decision.
    for fd in flag_decisions:
        rule_code = fd["ruleCode"]
        decision = fd["decision"]
        notes = fd.get("notes", "")

        flag_resp = table.query(
            KeyConditionExpression=(
                Key("PK").eq(pk) & Key("SK").begins_with(f"FLAG#{rule_code}#")
            ),
        )

        if not flag_resp.get("Items"):
            return _response(
                400, {"error": f"No flags found for rule code: {rule_code}"}
            )

        new_status = "CONFIRMED" if decision == "CONFIRM" else "OVERRIDDEN"

        for flag_item in flag_resp["Items"]:
            table.update_item(
                Key={"PK": pk, "SK": flag_item["SK"]},
                UpdateExpression=(
                    "SET reviewer_status = :status,"
                    " reviewer_id = :reviewer,"
                    " reviewer_ts = :ts,"
                    " reviewer_notes = :notes"
                ),
                ExpressionAttributeValues={
                    ":status": new_status,
                    ":reviewer": reviewer_email,
                    ":ts": now,
                    ":notes": notes,
                },
            )

        event_type = "FLAG_CONFIRMED" if decision == "CONFIRM" else "FLAG_OVERRIDDEN"
        audit_sk = f"AUDIT#{now}#{uuid.uuid4().hex[:8]}"
        table.put_item(
            Item={
                "PK": pk,
                "SK": audit_sk,
                "entity_type": "AUDIT",
                "actor": reviewer_email,
                "event_type": event_type,
                "previous_state": {"reviewer_status": "OPEN"},
                "new_state": {
                    "reviewer_status": new_status,
                    "rule_code": rule_code,
                    "notes": notes,
                },
                "timestamp": now,
                "applicationId": app_id,
            }
        )
        audit_record_ids.append(audit_sk)

    # Update METADATA status.
    table.update_item(
        Key={"PK": pk, "SK": "METADATA"},
        UpdateExpression="SET #st = :status, last_updated_ts = :ts",
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={":status": overall_decision, ":ts": now},
    )

    # Write overall decision AUDIT record.
    decision_audit_sk = f"AUDIT#{now}#{uuid.uuid4().hex[:8]}"
    table.put_item(
        Item={
            "PK": pk,
            "SK": decision_audit_sk,
            "entity_type": "AUDIT",
            "actor": reviewer_email,
            "event_type": "DECISION_SUBMITTED",
            "previous_state": {"status": meta_resp["Item"].get("status")},
            "new_state": {
                "status": overall_decision,
                "flag_decisions": flag_decisions,
            },
            "timestamp": now,
            "applicationId": app_id,
        }
    )
    audit_record_ids.append(decision_audit_sk)

    logger.info(
        json.dumps(
            {
                "action": "decision_submitted",
                "applicationId": app_id,
                "overallDecision": overall_decision,
                "flagDecisionCount": len(flag_decisions),
                "reviewer": reviewer_email,
            }
        )
    )

    return _response(
        200,
        {
            "applicationId": app_id,
            "updatedAt": now,
            "auditRecordIds": audit_record_ids,
        },
    )


# ── GET /applications/{id}/audit ─────────────────────────────────────────────


def _get_audit(app_id: str | None, table) -> dict:
    """Return all AUDIT records for an application, newest first."""
    if not app_id:
        return _response(400, {"error": "Missing application ID"})

    pk = f"APP#{app_id}"

    meta_resp = table.get_item(Key={"PK": pk, "SK": "METADATA"})
    if "Item" not in meta_resp:
        return _response(404, {"error": f"Application {app_id} not found"})

    result = table.query(
        KeyConditionExpression=Key("PK").eq(pk) & Key("SK").begins_with("AUDIT#"),
        ScanIndexForward=False,
    )

    items = []
    for item in result.get("Items", []):
        new_state = item.get("new_state") or {}
        items.append(
            {
                "timestamp": item.get("timestamp"),
                "reviewer": item.get("actor"),
                "action": item.get("event_type"),
                "ruleCode": new_state.get("rule_code"),
                "notes": new_state.get("notes"),
            }
        )

    return _response(200, {"items": items})

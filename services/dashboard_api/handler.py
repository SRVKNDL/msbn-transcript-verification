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
_s3 = boto3.client("s3", region_name="us-east-1")
_TABLE_NAME = os.environ.get("TABLE_NAME", "msbn-applications")
_BUCKET_NAME = os.environ.get("BUCKET_NAME", "")

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


def _hours_since(ts: str | None) -> int:
    if not ts:
        return 0
    try:
        parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return 0
    return max(0, int((datetime.now(timezone.utc) - parsed).total_seconds() // 3600))


def _source_location_view(source_location: dict | None) -> dict:
    source_location = source_location or {}
    return {
        "page": source_location.get("page")
        or source_location.get("page_number")
        or 1,
        "spans": source_location.get("spans")
        or source_location.get("text_spans")
        or [],
    }


def _safe_practice_for(rule_code: str) -> str:
    if rule_code.startswith("CONT"):
        return "SP-5"
    if rule_code.startswith(("PHYS", "PROG")):
        return "SP-4"
    return "SP"


def _clean_text(value) -> str:
    return str(value or "").strip()[:120]


def _upload_metadata_from_body(body: dict) -> tuple[dict, dict]:
    details = body.get("applicationDetails") or {}
    if not isinstance(details, dict):
        details = {}

    fields = {
        "applicant_name": _clean_text(details.get("applicantName")),
        "institution": _clean_text(details.get("institution")),
        "country": _clean_text(details.get("country")),
        "program": _clean_text(details.get("program")),
    }
    metadata = {key: value for key, value in fields.items() if value}
    headers = {
        f"x-amz-meta-{key.replace('_', '-')}": value
        for key, value in metadata.items()
    }
    return metadata, headers


def _application_view(metadata: dict, document: dict | None = None) -> dict:
    submitted_at = metadata.get("submission_ts") or metadata.get("uploadedAt") or ""
    return {
        "applicationId": metadata.get("applicationId"),
        "applicantName": metadata.get("applicant_name") or "",
        "institution": metadata.get("institution") or "",
        "country": metadata.get("country") or "",
        "submittedAt": submitted_at,
        "ageHours": _hours_since(submitted_at),
        "flagCount": int(metadata.get("flag_count", 0)),
        "highestSeverity": _highest_severity(metadata),
        "status": metadata.get("status"),
        "caseRef": metadata.get("case_ref"),
        "licenseNumber": metadata.get("license_number") or "",
        "programYear": (
            metadata.get("program_year")
            or metadata.get("grad_year")
            or metadata.get("graduation_year")
            or ""
        ),
        "pageCount": int(
            (document or {}).get("page_count")
            or metadata.get("page_count")
            or metadata.get("document_count")
            or 0
        ),
    }


def _highest_severity(metadata: dict) -> str | None:
    high_count = int(metadata.get("high_severity_count", 0))
    flag_count = int(metadata.get("flag_count", 0))
    if high_count > 0:
        return "High"
    if flag_count > 0:
        return "Medium"
    return None


def _flag_view(flag: dict) -> dict:
    rule_code = flag.get("rule_code") or flag.get("ruleCode") or "UNKNOWN"
    reviewer_status = flag.get("reviewer_status", "OPEN")
    return {
        "ruleCode": rule_code,
        "ruleName": flag.get("rule_name") or rule_code,
        "severity": flag.get("severity") or "Low",
        "rationale": flag.get("rationale") or "No rationale provided.",
        "sourceLocation": _source_location_view(flag.get("source_location")),
        "status": "PENDING" if reviewer_status == "OPEN" else reviewer_status,
        "safePractice": flag.get("safe_practice") or _safe_practice_for(rule_code),
    }


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

        if route_key == "POST /uploads":
            return _create_upload_url(event)

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
        items.append(_application_view(item))

    next_cursor = None
    last_key = result.get("LastEvaluatedKey")
    if last_key:
        next_cursor = base64.b64encode(
            json.dumps(last_key).encode()
        ).decode()

    return _response(200, {"items": items, "nextCursor": next_cursor})


# POST /uploads.


def _create_upload_url(event: dict) -> dict:
    """Return a pre-signed S3 PUT URL for one transcript PDF."""
    if not _BUCKET_NAME:
        return _response(500, {"error": "Upload bucket is not configured"})

    body_str = event.get("body", "") or "{}"
    try:
        body = json.loads(body_str)
    except json.JSONDecodeError:
        return _response(400, {"error": "Invalid JSON body"})

    filename = str(body.get("filename") or "transcript.pdf").strip()
    content_type = str(body.get("contentType") or "application/pdf").strip()
    if not filename.lower().endswith(".pdf") or content_type != "application/pdf":
        return _response(400, {"error": "Only PDF transcripts are accepted"})

    upload_id = uuid.uuid4().hex
    safe_name = filename.rsplit("/", 1)[-1].replace("\\", "_")
    s3_key = f"uploads/{upload_id}/{safe_name}"
    metadata, metadata_headers = _upload_metadata_from_body(body)

    upload_url = _s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": _BUCKET_NAME,
            "Key": s3_key,
            "ContentType": "application/pdf",
            "Metadata": metadata,
        },
        ExpiresIn=900,
        HttpMethod="PUT",
    )

    return _response(
        200,
        {
            "uploadUrl": upload_url,
            "s3Key": s3_key,
            "expiresIn": 900,
            "metadataHeaders": metadata_headers,
        },
    )


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

    flags = [_flag_view(f) for f in flag_resp.get("Items", [])]

    return _response(
        200,
        {
            "applicationId": app_id,
            "application": _application_view(metadata, extraction),
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

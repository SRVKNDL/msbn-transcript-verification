"""HTTP API handlers for the reviewer dashboard."""

import base64
import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Key
from botocore.exceptions import ClientError

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
    "Access-Control-Allow-Methods": "GET,POST,DELETE,OPTIONS",
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
_COURSE_CODE_RE = re.compile(r"\b([A-Z]{2,5})\s*-?\s*(\d{3,4}[A-Z]?)\b")


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


def _clean_application_id(value) -> str:
    text = _clean_text(value)
    safe = "".join(
        char if char.isalnum() or char in "._-" else "-" for char in text
    )
    return safe.strip(".-_")[:80]


def _upload_metadata_from_body(body: dict) -> tuple[dict, dict]:
    details = body.get("applicationDetails") or {}
    if not isinstance(details, dict):
        details = {}

    fields = {
        "application_id": _clean_application_id(details.get("applicationId")),
        "applicant_name": _clean_text(details.get("applicantName")),
        "institution": _clean_text(details.get("institution")),
        "country": _clean_text(details.get("country")),
    }
    metadata = {key: value for key, value in fields.items() if value}
    headers = {f"x-amz-meta-{key}": value for key, value in metadata.items()}
    return metadata, headers


def _application_view(
    metadata: dict,
    document: dict | None = None,
    *,
    page_count: int | None = None,
) -> dict:
    submitted_at = metadata.get("submission_ts") or metadata.get("uploadedAt") or ""
    resolved_page_count = page_count
    if resolved_page_count is None:
        resolved_page_count = int(
            (document or {}).get("page_count")
            or metadata.get("page_count")
            or metadata.get("document_count")
            or 0
        )
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
        "originalFilename": metadata.get("originalFilename")
        or metadata.get("original_filename")
        or "",
        "programYear": (
            metadata.get("program_year")
            or metadata.get("grad_year")
            or metadata.get("graduation_year")
            or ""
        ),
        "pageCount": resolved_page_count,
    }


def _highest_severity(metadata: dict) -> str | None:
    high_count = int(metadata.get("high_severity_count", 0))
    flag_count = int(metadata.get("flag_count", 0))
    if high_count > 0:
        return "High"
    if flag_count > 0:
        return "Medium"
    return None


def _normalize_match_text(value) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _bbox_view(geometry: dict | None) -> dict | None:
    if not isinstance(geometry, dict):
        return None
    bbox = geometry.get("BoundingBox") or geometry.get("boundingBox") or geometry.get("bbox")
    if not isinstance(bbox, dict):
        return None
    try:
        left = float(bbox.get("Left"))
        top = float(bbox.get("Top"))
        width = float(bbox.get("Width"))
        height = float(bbox.get("Height"))
    except (TypeError, ValueError):
        return None
    if min(left, top, width, height) < 0:
        return None
    return {
        "left": left,
        "top": top,
        "width": width,
        "height": height,
    }


def _merge_bboxes(boxes: list[dict]) -> dict | None:
    resolved = [_bbox_view(box) for box in boxes]
    resolved = [box for box in resolved if box]
    if not resolved:
        return None
    left = min(box["left"] for box in resolved)
    top = min(box["top"] for box in resolved)
    right = max(box["left"] + box["width"] for box in resolved)
    bottom = max(box["top"] + box["height"] for box in resolved)
    return {
        "left": left,
        "top": top,
        "width": max(0.0, right - left),
        "height": max(0.0, bottom - top),
    }


def _textract_entries(textract_doc: dict | None) -> list[dict]:
    if not isinstance(textract_doc, dict):
        return []

    entries: list[dict] = []
    for page in textract_doc.get("pages") or []:
        if not isinstance(page, dict):
            continue
        page_number = int(page.get("page_number") or 1)

        for line in page.get("lines") or []:
            if not isinstance(line, dict):
                continue
            text = str(line.get("text") or "").strip()
            bbox = _bbox_view(line.get("geometry"))
            if text and bbox:
                entries.append({
                    "page": page_number,
                    "text": text,
                    "normalized": _normalize_match_text(text),
                    "matchType": "line",
                    "rect": bbox,
                })

        for table in page.get("tables") or []:
            if not isinstance(table, dict):
                continue
            cells_by_row: dict[int, list[dict]] = {}
            for cell in table.get("cells") or []:
                if not isinstance(cell, dict):
                    continue
                row_index = cell.get("row_index")
                if not isinstance(row_index, int):
                    continue
                cells_by_row.setdefault(row_index, []).append(cell)

            for row_index, cells in cells_by_row.items():
                ordered = sorted(
                    cells,
                    key=lambda item: item.get("column_index") or 0,
                )
                row_text = " ".join(
                    str(cell.get("text") or "").strip()
                    for cell in ordered
                    if str(cell.get("text") or "").strip()
                ).strip()
                row_bbox = _merge_bboxes([cell.get("geometry") for cell in ordered])
                if row_text and row_bbox:
                    entries.append({
                        "page": page_number,
                        "text": row_text,
                        "normalized": _normalize_match_text(row_text),
                        "matchType": "table_row",
                        "rect": row_bbox,
                    })

        for form in page.get("forms") or []:
            if not isinstance(form, dict):
                continue
            key_text = str(form.get("key") or "").strip()
            value_text = str(form.get("value") or "").strip()
            key_bbox = _bbox_view(form.get("key_geometry"))
            value_bbox = _merge_bboxes(form.get("value_geometry") or [])
            if key_text and key_bbox:
                entries.append({
                    "page": page_number,
                    "text": key_text,
                    "normalized": _normalize_match_text(key_text),
                    "matchType": "form_key",
                    "rect": key_bbox,
                })
            if value_text and value_bbox:
                entries.append({
                    "page": page_number,
                    "text": value_text,
                    "normalized": _normalize_match_text(value_text),
                    "matchType": "form_value",
                    "rect": value_bbox,
                })
            combined_text = " ".join(part for part in (key_text, value_text) if part).strip()
            combined_bbox = _merge_bboxes([form.get("key_geometry"), *(form.get("value_geometry") or [])])
            if combined_text and combined_bbox:
                entries.append({
                    "page": page_number,
                    "text": combined_text,
                    "normalized": _normalize_match_text(combined_text),
                    "matchType": "form_pair",
                    "rect": combined_bbox,
                })

        for layout in page.get("layouts") or []:
            if not isinstance(layout, dict):
                continue
            text = str(layout.get("text") or "").strip()
            bbox = _bbox_view(layout.get("geometry"))
            if text and bbox:
                entries.append({
                    "page": page_number,
                    "text": text,
                    "normalized": _normalize_match_text(text),
                    "matchType": "layout",
                    "rect": bbox,
                })

        for query in page.get("queries") or []:
            if not isinstance(query, dict):
                continue
            for answer in query.get("answers") or []:
                if not isinstance(answer, dict):
                    continue
                text = str(answer.get("text") or "").strip()
                bbox = _bbox_view(answer.get("geometry"))
                if text and bbox:
                    entries.append({
                        "page": page_number,
                        "text": text,
                        "normalized": _normalize_match_text(text),
                        "matchType": "query_answer",
                        "rect": bbox,
                    })
    return entries


def _match_textract_span(span: str, entries: list[dict]) -> list[dict]:
    normalized = _normalize_match_text(span)
    if not normalized:
        return []

    exact = [entry for entry in entries if entry["normalized"] == normalized]
    if exact:
        return exact

    containing = [
        entry
        for entry in entries
        if normalized in entry["normalized"] or entry["normalized"] in normalized
    ]
    return containing


def _highlight_target_for_source_location(
    source_location: dict | None,
    textract_doc: dict | None,
) -> dict | None:
    if not isinstance(source_location, dict) or not isinstance(textract_doc, dict):
        return None

    spans = [
        str(span).strip()
        for span in source_location.get("text_spans") or source_location.get("spans") or []
        if str(span or "").strip()
    ]
    if not spans:
        return None

    source_page = source_location.get("page_number") or source_location.get("page")
    try:
        source_page = int(source_page) if source_page is not None else None
    except (TypeError, ValueError):
        source_page = None

    entries = _textract_entries(textract_doc)
    matched_spans: list[str] = []
    unmatched_spans: list[str] = []
    page_targets: dict[int, dict] = {}

    for span in spans:
        matches = _match_textract_span(span, entries)
        if source_page is not None:
            page_filtered = [match for match in matches if match["page"] == source_page]
            if page_filtered:
                matches = page_filtered
        if not matches:
            unmatched_spans.append(span)
            continue

        matched_spans.append(span)
        for match in matches:
            target = page_targets.setdefault(
                match["page"],
                {"page": match["page"], "rects": [], "textSpans": [], "matchTypes": []},
            )
            if span not in target["textSpans"]:
                target["textSpans"].append(span)
            if match["matchType"] not in target["matchTypes"]:
                target["matchTypes"].append(match["matchType"])
            if match["rect"] not in target["rects"]:
                target["rects"].append(match["rect"])

    if not page_targets:
        return None

    ordered_targets = sorted(page_targets.values(), key=lambda item: item["page"])
    primary_page = source_page if isinstance(source_page, int) and source_page in page_targets else ordered_targets[0]["page"]
    primary_target = next(
        target for target in ordered_targets if target["page"] == primary_page
    )

    return {
        "type": "textract",
        "page": primary_page,
        "rects": primary_target["rects"],
        "textSpans": primary_target["textSpans"],
        "matchTypes": primary_target["matchTypes"],
        "pageTargets": ordered_targets,
        "matchedSpans": matched_spans,
        "unmatchedSpans": unmatched_spans,
    }


def _course_code(value: str | None) -> str | None:
    match = _COURSE_CODE_RE.search(str(value or "").upper())
    if not match:
        return None
    return f"{match.group(1)} {match.group(2)}"


def _course_source_locations_for_code(aggregation: dict | None, course_code: str) -> list[dict]:
    if not isinstance(aggregation, dict):
        return []

    locations: list[dict] = []
    for course in aggregation.get("courses") or []:
        if not isinstance(course, dict):
            continue
        current_code = _course_code(course.get("code") or course.get("course_code"))
        if current_code != course_code:
            continue
        source = course.get("source_location")
        if isinstance(source, dict):
            locations.append(source)
    return locations


def _fallback_source_location(flag: dict, aggregation: dict | None) -> dict | None:
    existing = flag.get("source_location")
    if isinstance(existing, dict):
        return existing

    rule_code = str(flag.get("rule_code") or flag.get("ruleCode") or "")
    rule_description = str(flag.get("rule_description") or flag.get("ruleName") or "")
    rationale = str(flag.get("rationale") or "")

    if rule_code in {"PROG_001", "PROG_002", "PROG_004"} or (
        rule_code == "CONT_004" and "duplicate course" in rule_description.lower()
    ):
        parsed_code = _course_code(rule_description) or _course_code(rationale)
        if parsed_code:
            sources = _course_source_locations_for_code(aggregation, parsed_code)
            spans: list[str] = []
            page_number = None
            for source in sources:
                if page_number is None and isinstance(source.get("page_number"), int):
                    page_number = source["page_number"]
                for span in source.get("text_spans") or []:
                    text = str(span).strip()
                    if text and text not in spans:
                        spans.append(text)
            if page_number is not None and spans:
                return {"page_number": page_number, "text_spans": spans}

    if rule_code == "PROG_003":
        for key in ("total_credit_hours_source", "total_credit_hours_stated_source"):
            source = aggregation.get(key) if isinstance(aggregation, dict) else None
            if isinstance(source, dict):
                return source

    return None


def _load_json_from_s3(key: str | None) -> dict | None:
    if not _BUCKET_NAME or not key:
        return None
    try:
        response = _s3.get_object(Bucket=_BUCKET_NAME, Key=key)
    except ClientError:
        logger.exception("DashboardApiLambda could not read JSON from S3", extra={"s3_key": key})
        return None
    try:
        return json.loads(response["Body"].read().decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        logger.exception("DashboardApiLambda found invalid JSON in S3", extra={"s3_key": key})
        return None


def _flag_view(
    flag: dict,
    *,
    source_location: dict | None = None,
    textract_doc: dict | None = None,
) -> dict:
    rule_code = flag.get("rule_code") or flag.get("ruleCode") or "UNKNOWN"
    reviewer_status = flag.get("reviewer_status", "OPEN")
    resolved_source = source_location if source_location is not None else flag.get("source_location")
    highlight_target = _highlight_target_for_source_location(resolved_source, textract_doc)
    return {
        "ruleCode": rule_code,
        "ruleName": flag.get("rule_name") or rule_code,
        "severity": flag.get("severity") or "Low",
        "rationale": flag.get("rationale") or "No rationale provided.",
        "sourceLocation": _source_location_view(resolved_source),
        "status": "PENDING" if reviewer_status == "OPEN" else reviewer_status,
        "safePractice": flag.get("safe_practice") or _safe_practice_for(rule_code),
        "highlightTarget": highlight_target,
    }


def _transcript_preview(metadata: dict) -> dict:
    s3_key = metadata.get("s3_key")
    if not _BUCKET_NAME:
        return {"url": None, "status": "BUCKET_NOT_CONFIGURED", "s3Key": s3_key}
    if not s3_key:
        return {"url": None, "status": "MISSING_S3_KEY", "s3Key": None}

    try:
        _s3.head_object(Bucket=_BUCKET_NAME, Key=s3_key)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "UNKNOWN")
        logger.warning(
            json.dumps(
                {
                    "action": "transcript_preview_missing",
                    "bucket": _BUCKET_NAME,
                    "s3_key": s3_key,
                    "error_code": error_code,
                }
            )
        )
        return {"url": None, "status": "S3_OBJECT_MISSING", "s3Key": s3_key}

    url = _s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": _BUCKET_NAME, "Key": s3_key},
        ExpiresIn=900,
        HttpMethod="GET",
    )
    return {"url": url, "status": "AVAILABLE", "s3Key": s3_key}


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

        if route_key == "GET /applications/{id}/pages/{page}":
            return _get_page_image(
                path_params.get("id"), path_params.get("page"), table
            )

        if route_key == "POST /applications/{id}/decision":
            return _post_decision(
                event, path_params.get("id"), reviewer_email, table
            )

        if route_key == "GET /applications/{id}/audit":
            return _get_audit(path_params.get("id"), table)

        if route_key == "DELETE /applications/{id}":
            return _delete_application(path_params.get("id"), table)

        return _response(404, {"error": f"Not found: {route_key}"})

    except Exception:
        logger.exception("Unhandled error in DashboardApiLambda")
        return _response(500, {"error": "Internal server error"})


# GET /applications.


def _list_applications(event: dict, table) -> dict:
    """Query GSI1-ReviewQueue for applications with requested statuses."""
    params = event.get("queryStringParameters") or {}

    try:
        limit = min(int(params.get("limit", str(_DEFAULT_PAGE_SIZE))), _MAX_PAGE_SIZE)
        if limit < 1:
            return _response(400, {"error": "limit must be >= 1"})
    except ValueError:
        return _response(400, {"error": "limit must be an integer"})

    statuses = [
        status.strip()
        for status in str(params.get("status") or "READY_FOR_REVIEW").split(",")
        if status.strip()
    ]
    if not statuses:
        return _response(400, {"error": "status must include at least one value"})

    cursor = params.get("cursor")
    if cursor and len(statuses) > 1:
        return _response(400, {"error": "cursor is only supported for one status"})

    if len(statuses) > 1:
        items = []
        for status in statuses:
            result = table.query(
                IndexName="GSI1-ReviewQueue",
                KeyConditionExpression=Key("status").eq(status),
                ScanIndexForward=True,
                Limit=limit,
            )
            items.extend(_application_view(item) for item in result.get("Items", []))

        items.sort(key=lambda item: item.get("submittedAt") or "")
        return _response(200, {"items": items[:limit], "nextCursor": None})

    query_kwargs = {
        "IndexName": "GSI1-ReviewQueue",
        "KeyConditionExpression": Key("status").eq(statuses[0]),
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
    textract_doc = _load_json_from_s3((extraction or {}).get("s3_textract_key"))
    aggregation = _load_json_from_s3(f"processed/{app_id}/aggregation.json")

    flag_resp = table.query(
        KeyConditionExpression=Key("PK").eq(pk) & Key("SK").begins_with("FLAG#"),
    )

    flags = [
        _flag_view(
            flag,
            source_location=_fallback_source_location(flag, aggregation),
            textract_doc=textract_doc,
        )
        for flag in flag_resp.get("Items", [])
    ]

    transcript_preview = _transcript_preview(metadata)
    page_count = _resolved_page_count(app_id, metadata, extraction)

    return _response(
        200,
        {
            "applicationId": app_id,
            "application": _application_view(
                metadata,
                extraction,
                page_count=page_count,
            ),
            "metadata": metadata,
            "extraction": extraction,
            "transcriptUrl": transcript_preview["url"],
            "transcriptPreviewStatus": transcript_preview["status"],
            "transcriptS3Key": transcript_preview["s3Key"],
            "flags": flags,
        },
    )


# GET /applications/{id}/pages/{page}.


def _get_page_image(app_id: str | None, page: str | None, table) -> dict:
    """Return a short-lived signed URL for a rendered transcript page image."""
    if not app_id:
        return _response(400, {"error": "Missing application ID"})

    try:
        page_num = int(page or "")
    except ValueError:
        return _response(400, {"error": "Page must be an integer"})

    if page_num < 1:
        return _response(400, {"error": "Page must be >= 1"})

    pk = f"APP#{app_id}"
    meta_resp = table.get_item(Key={"PK": pk, "SK": "METADATA"})
    if "Item" not in meta_resp:
        return _response(404, {"error": f"Application {app_id} not found"})

    doc_resp = table.get_item(Key={"PK": pk, "SK": "DOCUMENT#TRANSCRIPT"})
    page_count = _resolved_page_count(app_id, meta_resp["Item"], doc_resp.get("Item"))
    if page_count and page_num > page_count:
        return _response(
            404,
            {"error": f"Page {page_num} is outside transcript page count {page_count}"},
        )

    if not _BUCKET_NAME:
        return _response(500, {"error": "Transcript bucket is not configured"})

    image_key = f"processed/{app_id}/page_transcript_{page_num}.png"
    try:
        _s3.head_object(Bucket=_BUCKET_NAME, Key=image_key)
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code", "UNKNOWN")
        logger.warning(
            json.dumps(
                {
                    "action": "page_image_missing",
                    "bucket": _BUCKET_NAME,
                    "s3_key": image_key,
                    "error_code": error_code,
                }
            )
        )
        return _response(404, {"error": f"Page image not found: {page_num}"})

    url = _s3.generate_presigned_url(
        ClientMethod="get_object",
        Params={"Bucket": _BUCKET_NAME, "Key": image_key},
        ExpiresIn=300,
        HttpMethod="GET",
    )
    return _response(200, {"url": url, "s3Key": image_key, "expiresIn": 300})


def _resolved_page_count(
    app_id: str,
    metadata: dict,
    document: dict | None = None,
) -> int:
    page_count = int(
        (document or {}).get("page_count")
        or metadata.get("page_count")
        or metadata.get("document_count")
        or 0
    )
    if page_count:
        return page_count
    return _rendered_page_count(app_id)


def _rendered_page_count(app_id: str) -> int:
    if not _BUCKET_NAME:
        return 0

    prefix = f"processed/{app_id}/page_transcript_"
    try:
        response = _s3.list_objects_v2(Bucket=_BUCKET_NAME, Prefix=prefix)
    except ClientError:
        logger.exception(
            "DashboardApiLambda could not infer rendered page count",
            extra={"applicationId": app_id},
        )
        return 0

    max_page = 0
    for obj in response.get("Contents") or []:
        key = obj.get("Key", "")
        suffix = key.removeprefix(prefix).removesuffix(".png")
        try:
            max_page = max(max_page, int(suffix))
        except ValueError:
            continue
    return max_page


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


# DELETE /applications/{id}.


def _delete_application(app_id: str | None, table) -> dict:
    """Delete all DynamoDB records and S3 objects for an application."""
    if not app_id:
        return _response(400, {"error": "Missing application ID"})

    pk = f"APP#{app_id}"

    # Verify the application exists and grab metadata for the S3 key.
    meta_resp = table.get_item(Key={"PK": pk, "SK": "METADATA"})
    if "Item" not in meta_resp:
        return _response(404, {"error": f"Application {app_id} not found"})

    s3_key = meta_resp["Item"].get("s3_key")

    # Collect every item under this PK (METADATA, DOCUMENT#TRANSCRIPT,
    # FLAG#*, AUDIT#*, etc.) with pagination.
    all_items = []
    last_evaluated_key = None
    while True:
        query_kwargs: dict = {
            "KeyConditionExpression": Key("PK").eq(pk),
        }
        if last_evaluated_key:
            query_kwargs["ExclusiveStartKey"] = last_evaluated_key
        result = table.query(**query_kwargs)
        all_items.extend(result.get("Items", []))
        last_evaluated_key = result.get("LastEvaluatedKey")
        if not last_evaluated_key:
            break

    # Batch-delete all DynamoDB items. batch_writer handles the 25-item limit.
    with table.batch_writer() as batch:
        for item in all_items:
            batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})

    # Delete S3 objects when a bucket is configured.
    if _BUCKET_NAME:
        # Original uploaded transcript.
        if s3_key:
            try:
                _s3.delete_object(Bucket=_BUCKET_NAME, Key=s3_key)
            except ClientError:
                logger.warning(
                    json.dumps(
                        {"action": "s3_delete_failed", "key": s3_key}
                    )
                )

        # All processed objects (page images, extraction JSON, aggregation).
        prefix = f"processed/{app_id}/"
        try:
            paginator = _s3.get_paginator("list_objects_v2")
            for page in paginator.paginate(Bucket=_BUCKET_NAME, Prefix=prefix):
                objects = page.get("Contents") or []
                if objects:
                    _s3.delete_objects(
                        Bucket=_BUCKET_NAME,
                        Delete={
                            "Objects": [{"Key": obj["Key"]} for obj in objects]
                        },
                    )
        except ClientError:
            logger.warning(
                json.dumps(
                    {
                        "action": "s3_processed_delete_failed",
                        "prefix": prefix,
                        "applicationId": app_id,
                    }
                )
            )

    logger.info(
        json.dumps(
            {
                "action": "application_deleted",
                "applicationId": app_id,
                "dynamoItemsDeleted": len(all_items),
            }
        )
    )

    return _response(200, {"applicationId": app_id, "deleted": True})

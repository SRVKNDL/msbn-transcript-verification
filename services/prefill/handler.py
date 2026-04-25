"""Fast transcript identity prefill API.

This Lambda is intentionally separate from the authoritative extraction
workflow. It reads temporary preview PDFs from preview/*, tries embedded text
first, and only falls back to Nova Lite for the first one or two pages.
"""

import base64
import io
import json
import logging
import os
import re
import tempfile
import uuid

import boto3
from pdf2image import convert_from_path
from pypdf import PdfReader

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_s3 = boto3.client("s3", region_name="us-east-1")
_bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

_BUCKET_NAME = os.environ.get("BUCKET_NAME", "")
_BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")
_CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")
_MAX_BYTES = 25 * 1024 * 1024

_FIELDS = ("applicantName", "institution", "country")
_FIELD_LABELS = {
    "applicantName": (
        "student name",
        "applicant name",
        "candidate name",
        "name of student",
        "name",
    ),
    "institution": (
        "institution",
        "school",
        "college",
        "university",
        "issuing institution",
    ),
    "country": ("country", "country of issue", "country of study"),
}
_COUNTRIES = {
    "Australia",
    "Brazil",
    "Canada",
    "China",
    "France",
    "Germany",
    "Ghana",
    "India",
    "Ireland",
    "Jamaica",
    "Kenya",
    "Mexico",
    "Nigeria",
    "Philippines",
    "South Africa",
    "United Kingdom",
    "United States",
}

_CORS_HEADERS = {
    "Content-Type": "application/json",
    "Access-Control-Allow-Origin": _CORS_ORIGIN,
    "Access-Control-Allow-Headers": "Content-Type,Authorization",
    "Access-Control-Allow-Methods": "POST,OPTIONS",
}


def _response(status_code: int, body: dict) -> dict:
    return {
        "statusCode": status_code,
        "headers": _CORS_HEADERS,
        "body": json.dumps(body),
    }


def _get_reviewer_email(event: dict) -> str | None:
    try:
        return event["requestContext"]["authorizer"]["jwt"]["claims"]["email"]
    except (KeyError, TypeError):
        return None


def _parse_body(event: dict) -> tuple[dict | None, dict | None]:
    body_str = event.get("body") or "{}"
    if event.get("isBase64Encoded"):
        try:
            body_str = base64.b64decode(body_str).decode("utf-8")
        except ValueError:
            return None, {"error": "Invalid base64 body"}
    try:
        body = json.loads(body_str)
    except json.JSONDecodeError:
        return None, {"error": "Invalid JSON body"}
    if not isinstance(body, dict):
        return None, {"error": "JSON body must be an object"}
    return body, None


def _clean_text(value) -> str:
    return (
        str(value or "")
        .replace("\x00", " ")
        .replace("\r", "\n")
        .strip()
    )


def _clean_field(value) -> str:
    text = re.sub(r"\s+", " ", _clean_text(value))
    text = re.sub(r"^[\s:,\-]+|[\s:,\-]+$", "", text)
    return text[:120]


def _empty_fields() -> dict:
    return {field: "" for field in _FIELDS}


def _missing_fields(fields: dict) -> list[str]:
    return [field for field in _FIELDS if not _clean_field(fields.get(field))]


def _safe_preview_key(value: str) -> str:
    text = str(value or "")
    if not text.startswith("preview/") or text.endswith("/"):
        return ""
    if ".." in text or "\\" in text:
        return ""
    if not text.lower().endswith(".pdf"):
        return ""
    return text[:1024]


def _safe_filename(filename: str) -> str:
    name = str(filename or "transcript.pdf").rsplit("/", 1)[-1].replace("\\", "_")
    name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" ._")
    if not name.lower().endswith(".pdf"):
        name = f"{name or 'transcript'}.pdf"
    return name[:180]


def handler(event: dict, context) -> dict:
    route_key = event.get("routeKey", "")
    logger.info(json.dumps({"routeKey": route_key, "action": "request_received"}))

    if route_key.startswith("OPTIONS"):
        return _response(200, {})

    if not _get_reviewer_email(event):
        return _response(403, {"error": "Missing reviewer identity"})

    try:
        if route_key == "POST /prefill-uploads":
            return _create_prefill_upload(event)
        if route_key == "POST /prefill":
            return _extract_prefill(event)
        return _response(404, {"error": f"Not found: {route_key}"})
    except Exception:
        logger.exception("Unhandled error in PrefillLambda")
        return _response(500, {"error": "Internal server error"})


def _create_prefill_upload(event: dict) -> dict:
    if not _BUCKET_NAME:
        return _response(500, {"error": "Upload bucket is not configured"})

    body, error = _parse_body(event)
    if error:
        return _response(400, error)

    filename = _safe_filename(str(body.get("filename") or "transcript.pdf"))
    content_type = str(body.get("contentType") or "application/pdf").strip()
    try:
        size = int(body.get("size") or 0)
    except (TypeError, ValueError):
        return _response(400, {"error": "size must be an integer"})

    if content_type != "application/pdf" or not filename.lower().endswith(".pdf"):
        return _response(400, {"error": "Only PDF transcripts are accepted"})
    if size < 1 or size > _MAX_BYTES:
        return _response(400, {"error": "PDF size must be between 1 byte and 25 MB"})

    s3_key = f"preview/{uuid.uuid4().hex}/{filename}"
    upload_url = _s3.generate_presigned_url(
        ClientMethod="put_object",
        Params={
            "Bucket": _BUCKET_NAME,
            "Key": s3_key,
            "ContentType": "application/pdf",
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
        },
    )


def _extract_prefill(event: dict) -> dict:
    if not _BUCKET_NAME:
        return _response(500, {"error": "Upload bucket is not configured"})

    body, error = _parse_body(event)
    if error:
        return _response(400, error)

    s3_key = _safe_preview_key(str(body.get("s3Key") or ""))
    if not s3_key:
        return _response(400, {"error": "s3Key must be a preview PDF key"})

    try:
        head = _s3.head_object(Bucket=_BUCKET_NAME, Key=s3_key)
    except Exception:
        logger.warning(json.dumps({"event": "preview_pdf_missing", "s3_key": s3_key}))
        return _response(404, {"error": "Preview PDF not found"})

    if int(head.get("ContentLength") or 0) > _MAX_BYTES:
        return _response(400, {"error": "PDF exceeds 25 MB"})

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        local_pdf = tmp.name
    try:
        _s3.download_file(_BUCKET_NAME, s3_key, local_pdf)
        fields = _extract_fields_from_pdf(local_pdf)
    finally:
        try:
            os.unlink(local_pdf)
        except FileNotFoundError:
            pass

    return _response(
        200,
        {
            "fields": fields,
            "missingFields": _missing_fields(fields),
        },
    )


def _extract_fields_from_pdf(local_pdf: str) -> dict:
    fields = _extract_fields_from_text_pages(_extract_embedded_text_by_page(local_pdf))
    if not _missing_fields(fields):
        return fields

    for page_number in (1, 2):
        try:
            image_bytes = _render_pdf_page(local_pdf, page_number)
        except IndexError:
            break
        except Exception as exc:
            logger.warning(
                json.dumps({
                    "event": "preview_render_failed",
                    "page_number": page_number,
                    "error": str(exc),
                })
            )
            break

        nova_fields = _call_bedrock_for_page(image_bytes, page_number)
        for field, value in nova_fields.items():
            if not fields.get(field):
                fields[field] = _clean_field(value)
        if not _missing_fields(fields):
            break

    return {field: _clean_field(fields.get(field)) for field in _FIELDS}


def _extract_embedded_text_by_page(local_pdf: str) -> list[str]:
    try:
        reader = PdfReader(local_pdf)
    except Exception as exc:
        logger.info(json.dumps({"event": "embedded_text_open_failed", "error": str(exc)}))
        return []

    pages: list[str] = []
    for page in reader.pages[:2]:
        try:
            pages.append(_clean_text(page.extract_text() or ""))
        except Exception as exc:
            logger.info(
                json.dumps({"event": "embedded_text_page_failed", "error": str(exc)})
            )
            pages.append("")
    return pages


def _extract_fields_from_text_pages(pages: list[str]) -> dict:
    text = "\n".join(page for page in pages if page)
    fields = _empty_fields()
    if not text.strip():
        return fields

    for field, labels in _FIELD_LABELS.items():
        fields[field] = _extract_after_label(text, labels)

    if not fields["institution"]:
        fields["institution"] = _extract_institution_from_lines(text)
    if not fields["country"]:
        fields["country"] = _extract_country(text)

    return fields


def _extract_after_label(text: str, labels: tuple[str, ...]) -> str:
    for label in labels:
        pattern = rf"\b{re.escape(label)}\b\s*[:\-]?\s*([^\n\r]{{2,120}})"
        match = re.search(pattern, text, flags=re.IGNORECASE)
        value = _clean_field(match.group(1) if match else "")
        if value:
            return value
    return ""


def _extract_institution_from_lines(text: str) -> str:
    for raw_line in text.splitlines()[:20]:
        line = _clean_field(raw_line)
        if re.search(r"\b(university|college|school|institute|academy)\b", line, re.I):
            return line
    return ""


def _extract_country(text: str) -> str:
    for country in sorted(_COUNTRIES, key=len, reverse=True):
        if re.search(rf"\b{re.escape(country)}\b", text, flags=re.IGNORECASE):
            return country
    return ""


def _render_pdf_page(local_pdf: str, page_number: int) -> bytes:
    images = convert_from_path(
        local_pdf,
        first_page=page_number,
        last_page=page_number,
        dpi=150,
        fmt="png",
        single_file=True,
    )
    if not images:
        raise IndexError(f"PDF has no page {page_number}")
    buffer = io.BytesIO()
    images[0].save(buffer, format="PNG")
    return buffer.getvalue()


def _call_bedrock_for_page(image_bytes: bytes, page_number: int) -> dict:
    prompt = """Extract only these transcript identity fields from this page image:
applicantName, institution, country.

Rules:
- Use explicit visible text only.
- Do not infer country from an institution name alone.
- If a field is absent, use an empty string.
- Return valid JSON only with exactly these keys:
  {"applicantName": "", "institution": "", "country": ""}
"""
    body = json.dumps({
        "schemaVersion": "messages-v1",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "image": {
                            "format": "png",
                            "source": {
                                "bytes": base64.b64encode(image_bytes).decode("utf-8")
                            },
                        }
                    },
                    {"text": prompt},
                ],
            }
        ],
        "inferenceConfig": {
            "max_new_tokens": 300,
            "temperature": 0.0,
            "topP": 1.0,
        },
    })

    response = _bedrock.invoke_model(
        modelId=_BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )
    response_body = json.loads(response["body"].read())
    raw_text = response_body["output"]["message"]["content"][0]["text"]
    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError:
        logger.warning(
            json.dumps({
                "event": "prefill_nova_json_parse_error",
                "page_number": page_number,
                "raw_text_preview": raw_text[:300],
            })
        )
        return _empty_fields()

    if not isinstance(parsed, dict):
        return _empty_fields()
    return {field: _clean_field(parsed.get(field)) for field in _FIELDS}

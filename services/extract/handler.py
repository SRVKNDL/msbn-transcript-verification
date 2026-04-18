"""ExtractLambda — Session 2: Bedrock Nova per-page extraction.

Downloads a transcript PDF from S3, converts each page to a PNG image,
calls Amazon Nova (Lite by default) via Bedrock for structured field
extraction, validates response enum values, merges page-level results,
and writes the full extraction JSON to S3.

Step Functions input:
    {
        "applicationId": "<uuid>",
        "s3_key":        "uploads/<applicationId>/transcript.pdf",
        "bucket":        "<bucket-name>"
    }

Return value:
    {
        "applicationId":     "<uuid>",
        "page_count":        <int>,
        "extraction_s3_key": "processed/<applicationId>/extraction_transcript.json"
    }

S3 outputs written by this function:
    processed/<applicationId>/page_transcript_<n>.png   (one per page)
    processed/<applicationId>/extraction_transcript.json
"""

import base64
import datetime
import json
import logging
import os
import tempfile

import boto3
from pdf2image import convert_from_path

from prompt import PROMPT_VERSION, VOCABULARY, build_extraction_prompt

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Module-level clients.
# _s3: moto patches the botocore transport layer so this uses the mock in tests.
# _bedrock: patched directly in tests via unittest.mock.patch.object.
_s3 = boto3.client("s3")
_bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

BUCKET_NAME = os.environ.get("BUCKET_NAME", "")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-lite-v1:0")

# Fields whose vocabulary values are array elements, not the array itself.
_ARRAY_FIELDS = {
    "security_features_present",
    "suspicious_course_names",
    "diploma_mill_phrases_found",
    "required_nursing_domains_present",
}


def _validate_and_build_page_record(
    nova_response: dict,
    page_number: int,
    width: int,
    height: int,
) -> dict:
    """Flatten and validate Nova's per-field response into a page record.

    Nova returns each field wrapped as::

        {
          "field_name": {
            "value":           <str | list | dict>,
            "confidence":      "high" | "medium" | "low",
            "source_location": {"page_number": int, "text_spans": [str]}  # optional
          }
        }

    The returned flat record stores:
        field_name              → the extracted value
        field_name_confidence   → the confidence string
        field_name_source       → the source_location dict, with page_number stamped

    ``accreditation_claim_location`` is additionally mirrored as
    ``accreditation_claim_source`` so the rule engine's ``_src()`` helper finds
    it under the standard ``{field}_source`` key.
    """
    record: dict = {
        "page_number": page_number,
        "image_dimensions": {"width": width, "height": height},
    }

    for field, meta in nova_response.items():
        if not isinstance(meta, dict):
            logger.warning(
                json.dumps({
                    "event": "unexpected_field_shape",
                    "field": field,
                    "value_preview": str(meta)[:200],
                    "page_number": page_number,
                })
            )
            record[field] = meta
            continue

        value = meta.get("value")
        confidence = meta.get("confidence")
        source_location = meta.get("source_location")

        # Always stamp page_number into every source_location dict.
        if isinstance(source_location, dict):
            source_location["page_number"] = page_number

        # ── Enum validation ────────────────────────────────────────────────
        if field in VOCABULARY:
            allowed = VOCABULARY[field]
            if field in _ARRAY_FIELDS and isinstance(value, list):
                for item in value:
                    if item not in allowed:
                        logger.warning(
                            json.dumps({
                                "event": "unexpected_enum_value",
                                "field": field,
                                "value": item,
                                "allowed": sorted(allowed),
                                "page_number": page_number,
                            })
                        )
            elif not isinstance(value, (list, dict)) and value not in allowed:
                logger.warning(
                    json.dumps({
                        "event": "unexpected_enum_value",
                        "field": field,
                        "value": value,
                        "allowed": sorted(allowed),
                        "page_number": page_number,
                    })
                )

        if confidence is not None and confidence not in VOCABULARY["_confidence"]:
            logger.warning(
                json.dumps({
                    "event": "unexpected_confidence_value",
                    "field": field,
                    "confidence": confidence,
                    "page_number": page_number,
                })
            )

        # ── Store flattened fields ─────────────────────────────────────────
        record[field] = value
        if confidence is not None:
            record[f"{field}_confidence"] = confidence
        if source_location is not None:
            record[f"{field}_source"] = source_location

    # Mirror accreditation_claim_location as accreditation_claim_source so the
    # rule engine _src("accreditation_claim") finds it via the standard suffix.
    acc_loc = record.get("accreditation_claim_location")
    if isinstance(acc_loc, dict):
        record.setdefault("accreditation_claim_source", acc_loc)

    return record


def _call_bedrock_for_page(image_bytes: bytes, page_number: int) -> dict:
    """Invoke Bedrock Nova for one PNG image and return the parsed JSON dict.

    Raises ``ValueError`` if Nova's response cannot be parsed as JSON so the
    Lambda re-raises and Step Functions routes to the error state.
    """
    system_prompt, user_prompt = build_extraction_prompt()
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    body = json.dumps({
        "schemaVersion": "messages-v1",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "image": {
                            "format": "png",
                            "source": {"bytes": b64_image},
                        }
                    },
                    {"text": user_prompt},
                ],
            }
        ],
        "system": [{"text": system_prompt}],
        "inferenceConfig": {
            "max_new_tokens": 4096,
            "temperature": 0.0,
            "topP": 1.0,
        },
    })

    response = _bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )

    response_body = json.loads(response["body"].read())
    raw_text = response_body["output"]["message"]["content"][0]["text"]

    try:
        return json.loads(raw_text)
    except json.JSONDecodeError as exc:
        logger.error(
            json.dumps({
                "event": "nova_json_parse_error",
                "page_number": page_number,
                "error": str(exc),
                "raw_text_preview": raw_text[:500],
            })
        )
        raise ValueError(
            f"Nova response for page {page_number} is not valid JSON"
        ) from exc


def handler(event, context):
    """Extract structured data from a transcript PDF via Bedrock Nova.

    Raises on S3 download failure, PDF conversion failure, or Bedrock error
    so Step Functions retries the state and ultimately routes to the failure
    handler.
    """
    logger.info("ExtractLambda invoked: %s", json.dumps(event))

    application_id = event["applicationId"]
    s3_key = event["s3_key"]
    bucket = event.get("bucket") or BUCKET_NAME

    # ── 1. Download PDF from S3 ───────────────────────────────────────────────
    local_pdf = os.path.join(
        tempfile.gettempdir(), f"{application_id}_transcript.pdf"
    )
    try:
        _s3.download_file(bucket, s3_key, local_pdf)
    except Exception as exc:
        logger.error(
            json.dumps({
                "event": "download_failed",
                "applicationId": application_id,
                "s3_key": s3_key,
                "error": str(exc),
            })
        )
        raise

    # ── 2. Convert PDF pages to PNG images ────────────────────────────────────
    try:
        images = convert_from_path(local_pdf)
    except Exception as exc:
        logger.error(
            json.dumps({
                "event": "pdf_conversion_failed",
                "applicationId": application_id,
                "error": str(exc),
            })
        )
        raise
    finally:
        if os.path.exists(local_pdf):
            os.unlink(local_pdf)

    page_extractions = []

    for page_idx, img in enumerate(images, start=1):
        width, height = img.size

        # ── 3. Write page PNG to S3 ───────────────────────────────────────────
        img_key = f"processed/{application_id}/page_transcript_{page_idx}.png"
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            img.save(tmp.name, format="PNG")
            tmp_path = tmp.name
        try:
            with open(tmp_path, "rb") as fh:
                image_bytes = fh.read()
            _s3.upload_file(tmp_path, bucket, img_key)
        finally:
            os.unlink(tmp_path)

        # ── 4. Call Bedrock Nova for this page ────────────────────────────────
        nova_raw = _call_bedrock_for_page(image_bytes, page_idx)

        # ── 5. Validate enums and flatten into a page record ──────────────────
        page_record = _validate_and_build_page_record(
            nova_raw, page_idx, width, height
        )
        page_extractions.append(page_record)

    # ── 6. Write full extraction JSON to S3 ───────────────────────────────────
    extraction_key = f"processed/{application_id}/extraction_transcript.json"
    extraction_doc = {
        "schema_version": "1.0",
        "application_id": application_id,
        "document_type": "TRANSCRIPT",
        "page_count": len(images),
        "bedrock_model_id": BEDROCK_MODEL_ID,
        "prompt_version": PROMPT_VERSION,
        "extraction_ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "pages": page_extractions,
    }

    _s3.put_object(
        Bucket=bucket,
        Key=extraction_key,
        Body=json.dumps(extraction_doc, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    logger.info(
        json.dumps({
            "event": "extraction_complete",
            "applicationId": application_id,
            "page_count": len(images),
            "extraction_s3_key": extraction_key,
        })
    )

    return {
        "applicationId": application_id,
        "page_count": len(images),
        "extraction_s3_key": extraction_key,
    }

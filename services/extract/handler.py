"""Extract transcript PDFs into the JSON contract consumed by the rules."""

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

# Keep clients warm between Lambda invocations.
_s3 = boto3.client("s3")
_bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")

BUCKET_NAME = os.environ.get("BUCKET_NAME", "")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")
BEDROCK_MAX_NEW_TOKENS = int(os.environ.get("BEDROCK_MAX_NEW_TOKENS", "5000"))

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
    """Flatten Nova output and warn on enum drift without failing the run."""
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

        if isinstance(source_location, dict):
            source_location["page_number"] = page_number

        # Treat vocabulary drift as a data-quality warning, not a pipeline failure.
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

        # Store the field plus its optional confidence/source siblings.
        record[field] = value
        if confidence is not None:
            record[f"{field}_confidence"] = confidence
        if source_location is not None:
            record[f"{field}_source"] = source_location

    # Rule helpers expect the usual <field>_source shape.
    acc_loc = record.get("accreditation_claim_location")
    if isinstance(acc_loc, dict):
        record.setdefault("accreditation_claim_source", acc_loc)

    return record


def _call_bedrock_for_page(image_bytes: bytes, page_number: int) -> dict:
    """Run one page through Nova and parse the JSON response."""
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
            "max_new_tokens": BEDROCK_MAX_NEW_TOKENS,
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
    stop_reason = response_body.get("stopReason", "unknown")
    usage = response_body.get("usage") or {}

    try:
        return _parse_nova_json(raw_text)
    except json.JSONDecodeError as exc:
        logger.error(
            json.dumps({
                "event": "nova_json_parse_error",
                "page_number": page_number,
                "error": str(exc),
                "stop_reason": stop_reason,
                "input_tokens": usage.get("inputTokens"),
                "output_tokens": usage.get("outputTokens"),
                "raw_text_length": len(raw_text),
                "raw_text_preview": raw_text[:500],
            })
        )
        raise ValueError(
            f"Nova response for page {page_number} is not valid JSON"
        ) from exc


def _parse_nova_json(raw_text: str) -> dict:
    """Parse a Nova JSON object even when it is wrapped in prose/fences."""
    text = raw_text.strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = _parse_json_from_wrapped_text(text)

    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("Nova response JSON is not an object", text, 0)
    return parsed


def _parse_json_from_wrapped_text(text: str) -> dict:
    fenced = text
    if fenced.startswith("```"):
        fenced = fenced.removeprefix("```json").removeprefix("```").strip()
        if fenced.endswith("```"):
            fenced = fenced[:-3].strip()
        return json.loads(fenced)

    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _end_idx = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        return parsed

    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        return json.loads(text[first : last + 1])

    raise json.JSONDecodeError("No JSON object found in Nova response", text, 0)


def handler(event, context):
    """Download the PDF, extract each page, and persist the merged result."""
    logger.info("ExtractLambda invoked: %s", json.dumps(event))

    application_id = event["applicationId"]
    s3_key = event["s3_key"]
    bucket = event.get("bucket") or BUCKET_NAME

    # Download the source PDF to local Lambda storage.
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

    # Render once up front so each page can be stored and sent to Nova.
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

        # Persist the rendered page for reviewer highlighting.
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

        # Extract the page into the prompt schema.
        nova_raw = _call_bedrock_for_page(image_bytes, page_idx)

        # Convert Nova's nested field records into the downstream page shape.
        page_record = _validate_and_build_page_record(
            nova_raw, page_idx, width, height
        )
        page_extractions.append(page_record)

    # Write the document-level extraction payload for AggregationLambda.
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

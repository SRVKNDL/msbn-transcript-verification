"""ExtractLambda — Session 1: container infrastructure and handler skeleton.

Downloads a transcript PDF from S3, converts each page to a PNG image, writes
the images to S3, and produces a stub extraction JSON whose shape matches the
full extraction-vocabulary.md schema.  All field values are set to "STUB" or
null in Session 1; Session 2 replaces the stub with real Bedrock Nova calls.

Step Functions input:
    {
        "applicationId": "<uuid>",
        "s3_key":        "uploads/<applicationId>/transcript.pdf",
        "bucket":        "<bucket-name>"
    }

Return value:
    {
        "applicationId":    "<uuid>",
        "page_count":       <int>,
        "extraction_s3_key": "processed/<applicationId>/extraction_transcript.json"
    }

S3 outputs written by this function:
    processed/<applicationId>/page_transcript_<n>.png  (one per page)
    processed/<applicationId>/extraction_transcript.json

TODO (Session 2):
    - Add Bedrock Nova Lite invocation per page image.
    - Replace all "STUB" field values with real extracted values.
    - Add bedrock_model_id and prompt_version fields to the extraction document.
    - Add s3:GetObject on raw/ and Bedrock InvokeModel IAM permissions.
"""

import json
import logging
import os
import tempfile

import boto3
from pdf2image import convert_from_path

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Module-level client; moto patches the botocore transport layer so this client
# uses the mock automatically when tests run within a mock_aws() context.
_s3 = boto3.client("s3")

# Fallback bucket name from environment; tests override via the event payload.
BUCKET_NAME = os.environ.get("BUCKET_NAME", "")


def _stub_page_extraction(page_number: int, width: int, height: int) -> dict:
    """Return a stub extraction record for one page.

    The shape mirrors extraction-vocabulary.md Sections 1–3.  Every field is
    present so the rule engine can rely on key existence.  Session 2 populates
    real values from Bedrock Nova.
    """
    return {
        "page_number": page_number,
        "image_dimensions": {"width": width, "height": height},
        # ── Section 1 — Physical fields (feeds PHYS_ rules) ──────────────────
        "seal_type": "STUB",
        "seal_quality": "STUB",
        "print_technology": "STUB",
        "paper_size_format": "STUB",
        "text_alignment": "STUB",
        "document_provenance_appearance": "STUB",
        "security_features_present": [],
        "security_features_assessable": "STUB",
        # ── Section 2 — Content fields (feeds CONT_ rules) ───────────────────
        "grading_scale_format": "STUB",
        "language_of_issue": "STUB",
        "course_relevance": "STUB",
        "duplicate_courses_detected": "STUB",
        "suspicious_course_names": [],
        "gpa_arithmetic_consistency": "STUB",
        "dates_chronology_ok": "STUB",
        "dates_chronology_issue": "STUB",
        "program_duration_consistency": "STUB",
        # ── Section 3 — Program/institution fields (feeds PROG_ rules) ───────
        "accreditation_claim": None,
        "accreditation_claim_location": None,
        "diploma_mill_language_detected": "STUB",
        "diploma_mill_phrases_found": [],
        "institution_address_present": "STUB",
        "institution_phone_present": "STUB",
        "institution_website_present": "STUB",
        "graduation_confirmation_present": "STUB",
        "required_nursing_domains_present": [],
        # Session 2: Bedrock source_location metadata will be added here.
    }


def handler(event, context):
    """Extract structured data from a transcript PDF.

    Raises on S3 download failure or PDF conversion failure so Step Functions
    retries the state and ultimately routes to the failure handler.
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
        # Clean up the local PDF; /tmp space is limited in Lambda.
        if os.path.exists(local_pdf):
            os.unlink(local_pdf)

    page_extractions = []

    for page_idx, img in enumerate(images, start=1):
        width, height = img.size

        # ── 3. Write page image to S3 ─────────────────────────────────────────
        img_key = f"processed/{application_id}/page_transcript_{page_idx}.png"
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            img.save(tmp.name, format="PNG")
            tmp_path = tmp.name
        try:
            _s3.upload_file(tmp_path, bucket, img_key)
        finally:
            os.unlink(tmp_path)

        # ── 4. Build stub extraction record (Session 2: Bedrock call here) ────
        page_extractions.append(_stub_page_extraction(page_idx, width, height))

    # ── 5. Write extraction JSON to S3 ────────────────────────────────────────
    extraction_key = (
        f"processed/{application_id}/extraction_transcript.json"
    )
    extraction_doc = {
        "schema_version": "1.0",
        "application_id": application_id,
        "document_type": "TRANSCRIPT",
        "page_count": len(images),
        "pages": page_extractions,
        # TODO (Session 2): add bedrock_model_id, prompt_version, extraction_ts
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

"""Unit tests for ExtractLambda using moto-mocked AWS.

Coverage:
- PDF is downloaded from S3 (missing key raises an error)
- Pages are converted to images (correct number of page entries in output)
- Extraction JSON is written to S3 with the correct structure
- Per-page extraction shape matches extraction-vocabulary.md fields
- Page PNG images are written to S3 for each page
- Missing PDF (key does not exist) is handled gracefully — error re-raised
- Corrupt PDF (invalid content) is handled gracefully — error re-raised

Fixture PDF:
    tests/fixtures/real_transcripts/transcript-03-copiah-lincoln-cc.pdf
    (Copiah-Lincoln Community College — single-page, clean baseline)
"""

import importlib.util
import json
import os
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

# Fake AWS credentials must be set before any boto3 import so moto does not
# contact real AWS endpoints.
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
# Do NOT set BUCKET_NAME: the extract handler reads bucket from event["bucket"],
# so the env var is never needed here.  Setting it would pollute os.environ and
# shadow the rule_engine test's own setdefault("BUCKET_NAME", "msbn-transcripts-test"),
# causing NoSuchBucket failures there because the two tests use different buckets.

# Use a unique module name ("extract_handler") to avoid sys.modules['handler']
# collisions with the intake and other handler tests that share the same name.
_HERE = os.path.dirname(__file__)
_spec = importlib.util.spec_from_file_location(
    "extract_handler",
    os.path.join(_HERE, "../../services/extract/handler.py"),
)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
handler = _mod.handler

_BUCKET = "msbn-transcripts-dev"
_APP_ID = "APP-EXTRACT-TEST-001"
_PDF_KEY = f"uploads/{_APP_ID}/transcript.pdf"

_TRANSCRIPT_PDF = (
    Path(__file__).parent.parent
    / "fixtures/real_transcripts/transcript-03-copiah-lincoln-cc.pdf"
)


# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture()
def s3_bucket():
    """Moto-backed S3 bucket active for the duration of one test.

    mock_aws() patches at the botocore HTTP transport layer, so the module-level
    _s3 client in handler.py uses the mock automatically even though it was
    constructed before this fixture started.
    """
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=_BUCKET)
        yield client


@pytest.fixture()
def s3_with_transcript(s3_bucket):
    """S3 bucket pre-loaded with the real single-page transcript PDF."""
    s3_bucket.put_object(
        Bucket=_BUCKET,
        Key=_PDF_KEY,
        Body=_TRANSCRIPT_PDF.read_bytes(),
    )
    return s3_bucket


@pytest.fixture()
def extract_event():
    """Minimal Step Functions event for a transcript extraction."""
    return {
        "applicationId": _APP_ID,
        "s3_key": _PDF_KEY,
        "bucket": _BUCKET,
    }


# ── Handler return value ───────────────────────────────────────────────────────


def test_handler_returns_application_id(
    s3_with_transcript, extract_event, lambda_context
):
    """Handler must echo the applicationId from the event."""
    result = handler(extract_event, lambda_context)
    assert result["applicationId"] == _APP_ID


def test_handler_returns_page_count(
    s3_with_transcript, extract_event, lambda_context
):
    """Handler must return a positive integer page_count."""
    result = handler(extract_event, lambda_context)
    assert isinstance(result["page_count"], int)
    assert result["page_count"] >= 1


def test_handler_returns_extraction_s3_key(
    s3_with_transcript, extract_event, lambda_context
):
    """Handler must return the canonical extraction S3 key."""
    result = handler(extract_event, lambda_context)
    assert result["extraction_s3_key"] == (
        f"processed/{_APP_ID}/extraction_transcript.json"
    )


# ── Page count in extraction JSON ─────────────────────────────────────────────


def test_page_entries_match_pdf_page_count(
    s3_with_transcript, extract_event, lambda_context
):
    """Number of page objects in extraction JSON must equal the PDF page count."""
    result = handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    obj = s3.get_object(Bucket=_BUCKET, Key=result["extraction_s3_key"])
    extraction = json.loads(obj["Body"].read())

    assert extraction["page_count"] == result["page_count"]
    assert len(extraction["pages"]) == result["page_count"]


# ── Extraction JSON structure ──────────────────────────────────────────────────


def test_extraction_json_written_to_correct_key(
    s3_with_transcript, extract_event, lambda_context
):
    """Extraction JSON must be present at the canonical S3 key."""
    handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    # get_object raises NoSuchKey if the key doesn't exist — that's the assertion.
    obj = s3.get_object(
        Bucket=_BUCKET,
        Key=f"processed/{_APP_ID}/extraction_transcript.json",
    )
    assert len(obj["Body"].read()) > 0


def test_extraction_json_top_level_fields(
    s3_with_transcript, extract_event, lambda_context
):
    """Extraction JSON must contain schema_version, application_id, document_type,
    page_count, and pages."""
    handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    extraction = json.loads(
        s3.get_object(
            Bucket=_BUCKET,
            Key=f"processed/{_APP_ID}/extraction_transcript.json",
        )["Body"].read()
    )

    assert extraction["schema_version"] == "1.0"
    assert extraction["application_id"] == _APP_ID
    assert extraction["document_type"] == "TRANSCRIPT"
    assert isinstance(extraction["page_count"], int)
    assert isinstance(extraction["pages"], list)


def test_page_extraction_has_page_number_and_dimensions(
    s3_with_transcript, extract_event, lambda_context
):
    """First page entry must contain page_number=1 and positive integer dimensions."""
    handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    extraction = json.loads(
        s3.get_object(
            Bucket=_BUCKET,
            Key=f"processed/{_APP_ID}/extraction_transcript.json",
        )["Body"].read()
    )

    page = extraction["pages"][0]
    assert page["page_number"] == 1
    dims = page["image_dimensions"]
    assert isinstance(dims["width"], int) and dims["width"] > 0
    assert isinstance(dims["height"], int) and dims["height"] > 0


def test_page_extraction_has_physical_fields(
    s3_with_transcript, extract_event, lambda_context
):
    """Page entry must contain all Section 1 physical fields (feeds PHYS_ rules)."""
    handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    extraction = json.loads(
        s3.get_object(
            Bucket=_BUCKET,
            Key=f"processed/{_APP_ID}/extraction_transcript.json",
        )["Body"].read()
    )
    page = extraction["pages"][0]

    for field in (
        "seal_type",
        "seal_quality",
        "print_technology",
        "paper_size_format",
        "text_alignment",
        "document_provenance_appearance",
        "security_features_present",
        "security_features_assessable",
    ):
        assert field in page, f"Missing physical field: {field}"


def test_page_extraction_has_content_fields(
    s3_with_transcript, extract_event, lambda_context
):
    """Page entry must contain all Section 2 content fields (feeds CONT_ rules)."""
    handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    extraction = json.loads(
        s3.get_object(
            Bucket=_BUCKET,
            Key=f"processed/{_APP_ID}/extraction_transcript.json",
        )["Body"].read()
    )
    page = extraction["pages"][0]

    for field in (
        "grading_scale_format",
        "language_of_issue",
        "course_relevance",
        "duplicate_courses_detected",
        "suspicious_course_names",
        "gpa_arithmetic_consistency",
        "dates_chronology_ok",
        "dates_chronology_issue",
        "program_duration_consistency",
    ):
        assert field in page, f"Missing content field: {field}"


def test_page_extraction_has_program_fields(
    s3_with_transcript, extract_event, lambda_context
):
    """Page entry must contain all Section 3 program/institution fields
    (feeds PROG_ rules)."""
    handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    extraction = json.loads(
        s3.get_object(
            Bucket=_BUCKET,
            Key=f"processed/{_APP_ID}/extraction_transcript.json",
        )["Body"].read()
    )
    page = extraction["pages"][0]

    for field in (
        "accreditation_claim",
        "accreditation_claim_location",
        "diploma_mill_language_detected",
        "diploma_mill_phrases_found",
        "institution_address_present",
        "institution_phone_present",
        "institution_website_present",
        "graduation_confirmation_present",
        "required_nursing_domains_present",
    ):
        assert field in page, f"Missing program field: {field}"


# ── Page image S3 writes ───────────────────────────────────────────────────────


def test_page_images_written_to_s3(
    s3_with_transcript, extract_event, lambda_context
):
    """One non-empty PNG per PDF page must be written to processed/{appId}/."""
    result = handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    for page_num in range(1, result["page_count"] + 1):
        img_key = f"processed/{_APP_ID}/page_transcript_{page_num}.png"
        obj = s3.get_object(Bucket=_BUCKET, Key=img_key)
        assert len(obj["Body"].read()) > 0, f"Page image is empty: {img_key}"


# ── Error handling ─────────────────────────────────────────────────────────────


def test_missing_pdf_raises(s3_bucket, extract_event, lambda_context):
    """Handler must raise when the PDF key does not exist in S3.

    Step Functions retries the Extract state on re-raised exceptions before
    routing to the global failure handler.
    """
    # s3_bucket is empty — no PDF has been uploaded.
    with pytest.raises(Exception):
        handler(extract_event, lambda_context)


def test_corrupt_pdf_raises(s3_bucket, extract_event, lambda_context):
    """Handler must raise when the uploaded file is not a valid PDF.

    pdf2image/pdftoppm raises a PDFPageCountError (or similar) for non-PDF
    content; the handler propagates it so Step Functions can route to the
    failure state.
    """
    s3_bucket.put_object(
        Bucket=_BUCKET,
        Key=_PDF_KEY,
        Body=b"this is not a valid PDF file",
    )
    with pytest.raises(Exception):
        handler(extract_event, lambda_context)

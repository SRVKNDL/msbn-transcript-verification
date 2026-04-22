"""Unit tests for ExtractLambda — Session 2: Bedrock Nova integration.

Strategy
--------
- S3 is mocked via moto (mock_aws context).
- bedrock-runtime is NOT contacted.  ``_mod._bedrock`` is replaced with a
  ``MagicMock`` whose ``invoke_model`` side_effect returns a fresh ``BytesIO``
  wrapping the canned Nova fixture on every call.
- ``convert_from_path`` is NOT patched for happy-path tests; the real Copiah-
  Lincoln single-page PDF is used so image dimensions are realistic.
- Multi-page behaviour is tested by patching ``convert_from_path`` to return
  two synthetic PIL images, keeping the test self-contained.

Tests cover:
  (a) invoke_model called once per page
  (b) system prompt contains vocabulary enum values
  (c) response parsed into the correct flat field structure
  (d) invalid enum values trigger a WARNING log, not a crash
  (e) merged extraction document has the right page_count
  (f) bedrock_model_id and prompt_version appear in metadata
  (g) source_location.page_number is stamped correctly per page
  (h) extraction JSON written to S3 has the expected top-level shape

Fixture PDF:
    tests/fixtures/real_transcripts/transcript-03-copiah-lincoln-cc.pdf
    (Copiah-Lincoln Community College — single-page, clean baseline)
"""

import importlib.util
import json
import logging
import os
import sys
from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import boto3
import pytest
from moto import mock_aws
from PIL import Image

# ── AWS credential stubs (must precede any boto3 import) ─────────────────────
os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")

# ── Module loading ────────────────────────────────────────────────────────────
# handler.py does `from prompt import ...` as a relative sibling.  Add the
# services/extract directory to sys.path before exec_module so Python resolves
# the sibling correctly, then restore sys.path afterwards.

_HERE = os.path.dirname(__file__)
_EXTRACT_DIR = os.path.normpath(os.path.join(_HERE, "../../services/extract"))

sys.path.insert(0, _EXTRACT_DIR)
try:
    _spec = importlib.util.spec_from_file_location(
        "extract_handler",
        os.path.join(_EXTRACT_DIR, "handler.py"),
    )
    _mod = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(_mod)
finally:
    sys.path.pop(0)

handler = _mod.handler

# ── Test constants ────────────────────────────────────────────────────────────
_BUCKET = "msbn-transcripts-dev"
_APP_ID = "APP-EXTRACT-TEST-001"
_PDF_KEY = f"uploads/{_APP_ID}/transcript.pdf"

_TRANSCRIPT_PDF = (
    Path(__file__).parent.parent
    / "fixtures/real_transcripts/transcript-03-copiah-lincoln-cc.pdf"
)

# ── Canned Nova response ──────────────────────────────────────────────────────
# Represents a clean Mississippi-domestic single-page transcript as Nova would
# return it.  All enum values are from the extraction-vocabulary.md vocabulary.
_CANNED_NOVA_PAGE: dict = {
    # Section 1 — Physical fields
    "seal_type": {
        "value": "embossed",
        "confidence": "high",
        "source_location": {
            "page_number": 1,
            "text_spans": ["Official Seal of Copiah-Lincoln Community College"],
        },
    },
    "seal_quality": {
        "value": "clear",
        "confidence": "high",
        "source_location": {"page_number": 1, "text_spans": ["Official Seal"]},
    },
    "print_technology": {"value": "laser", "confidence": "high"},
    "paper_size_format": {"value": "us_letter", "confidence": "high"},
    "text_alignment": {"value": "normal", "confidence": "high"},
    "document_provenance_appearance": {"value": "original", "confidence": "high"},
    "security_features_present": {"value": [], "confidence": "medium"},
    "security_features_assessable": {"value": "yes", "confidence": "high"},
    # Section 2 — Content fields
    "grading_scale_format": {
        "value": "letter_grade_us",
        "confidence": "high",
        "source_location": {
            "page_number": 1,
            "text_spans": ["Grade Point: A=4.0, B=3.0, C=2.0, D=1.0, F=0.0"],
        },
    },
    "language_of_issue": {"value": "english", "confidence": "high"},
    "course_relevance": {"value": "nursing_standard", "confidence": "high"},
    "duplicate_courses_detected": {"value": "no", "confidence": "high"},
    "suspicious_course_names": {"value": [], "confidence": "high"},
    "gpa_arithmetic_consistency": {
        "value": "consistent",
        "confidence": "medium",
        "source_location": {
            "page_number": 1,
            "text_spans": ["Cumulative GPA: 3.75"],
        },
    },
    "dates_chronology_ok": {"value": "yes", "confidence": "high"},
    "dates_chronology_issue": {"value": "none", "confidence": "high"},
    "program_duration_consistency": {
        "value": "consistent_with_degree",
        "confidence": "high",
    },
    # Section 3 — Program/institution fields
    "accreditation_claim": {
        "value": "ACEN",
        "confidence": "high",
        "source_location": {
            "page_number": 1,
            "text_spans": ["Accredited by the Accreditation Commission for Education in Nursing (ACEN)"],
        },
    },
    "accreditation_claim_location": {
        "value": {
            "page_number": 1,
            "text_spans": ["Accredited by the Accreditation Commission for Education in Nursing (ACEN)"],
        },
        "confidence": "high",
    },
    "diploma_mill_language_detected": {"value": "no", "confidence": "high"},
    "diploma_mill_phrases_found": {"value": [], "confidence": "high"},
    "institution_address_present": {
        "value": "yes",
        "confidence": "high",
        "source_location": {
            "page_number": 1,
            "text_spans": ["P.O. Box 649, Wesson, MS 39191"],
        },
    },
    "institution_phone_present": {"value": "yes", "confidence": "high"},
    "institution_website_present": {"value": "yes", "confidence": "high"},
    "graduation_confirmation_present": {
        "value": "yes",
        "confidence": "high",
        "source_location": {
            "page_number": 1,
            "text_spans": ["Degree Conferred: Associate of Applied Science in Nursing"],
        },
    },
    "required_nursing_domains_present": {
        "value": ["adult_med_surg", "obstetrics", "pediatrics", "psychiatric"],
        "confidence": "medium",
    },
}


def _nova_response_body(page_data: dict | None = None) -> bytes:
    """Return a serialised Bedrock Nova invoke_model response body."""
    return json.dumps({
        "output": {
            "message": {
                "role": "assistant",
                "content": [{"text": json.dumps(page_data or _CANNED_NOVA_PAGE)}],
            }
        },
        "stopReason": "end_turn",
        "usage": {"inputTokens": 1234, "outputTokens": 567},
    }).encode("utf-8")


def _make_bedrock_mock(page_data: dict | None = None) -> MagicMock:
    """Return a MagicMock bedrock client whose invoke_model returns fresh BytesIO
    on every call (a consumed BytesIO would give empty reads on call 2+)."""
    mock_client = MagicMock()
    body_bytes = _nova_response_body(page_data)
    mock_client.invoke_model.side_effect = (
        lambda **kwargs: {"body": BytesIO(body_bytes)}
    )
    return mock_client


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def s3_bucket():
    """Moto-backed S3 bucket, active for the duration of one test."""
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


@pytest.fixture()
def bedrock_mock():
    """Replace _mod._bedrock with a mock that returns the canned Nova fixture."""
    mock_client = _make_bedrock_mock()
    with patch.object(_mod, "_bedrock", mock_client):
        yield mock_client


# ── (a) invoke_model called once per page ─────────────────────────────────────


def test_invoke_model_called_once_per_page(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """invoke_model must be called exactly once for a single-page transcript."""
    handler(extract_event, lambda_context)
    assert bedrock_mock.invoke_model.call_count == 1


def test_invoke_model_called_per_page_multi(
    s3_with_transcript, extract_event, lambda_context
):
    """invoke_model call count must match the number of pages (2-page case)."""
    fake_images = [
        Image.new("RGB", (850, 1100), color="white"),
        Image.new("RGB", (850, 1100), color="white"),
    ]
    mock_client = _make_bedrock_mock()
    with patch.object(_mod, "_bedrock", mock_client), \
         patch.object(_mod, "convert_from_path", return_value=fake_images):
        handler(extract_event, lambda_context)

    assert mock_client.invoke_model.call_count == 2


# ── (b) system prompt contains vocabulary enum values ─────────────────────────


def test_invoke_model_body_contains_system_prompt_enums(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """The body sent to invoke_model must embed vocabulary enum strings."""
    handler(extract_event, lambda_context)

    call_kwargs = bedrock_mock.invoke_model.call_args
    body = json.loads(call_kwargs.kwargs["body"])

    system_text = body["system"][0]["text"]
    # A sample of enum values that must appear in the system prompt.
    for token in ("high", "medium", "low", "source_location", "text_spans"):
        assert token in system_text, (
            f"Expected token '{token}' missing from system prompt"
        )


def test_invoke_model_body_contains_user_prompt_enums(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """The user message text must include vocabulary values from all 3 sections."""
    handler(extract_event, lambda_context)

    call_kwargs = bedrock_mock.invoke_model.call_args
    body = json.loads(call_kwargs.kwargs["body"])
    user_text = body["messages"][0]["content"][1]["text"]

    expected_tokens = [
        # Section 1
        "embossed", "stamped_ink", "laser", "us_letter",
        # Section 2
        "letter_grade_us", "nursing_standard", "enrollment_implausibly_early",
        # Section 3
        "adult_med_surg", "obstetrics", "diploma_mill_language_detected",
    ]
    for token in expected_tokens:
        assert token in user_text, (
            f"Vocabulary token '{token}' missing from user prompt"
        )


def test_invoke_model_body_treats_grad_date_as_completion_indicator(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """Prompt should explicitly count Grad Date / Degrees Earned as graduation evidence."""
    handler(extract_event, lambda_context)

    call_kwargs = bedrock_mock.invoke_model.call_args
    body = json.loads(call_kwargs.kwargs["body"])
    user_text = body["messages"][0]["content"][1]["text"]

    assert "Grad Date" in user_text
    assert "Degrees Earned" in user_text
    assert 'If any such indicator appears, return "yes".' in user_text


def test_invoke_model_body_guides_conservative_watermark_detection(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """Prompt should tell the model to avoid guessing on faint security features."""
    handler(extract_event, lambda_context)

    call_kwargs = bedrock_mock.invoke_model.call_args
    body = json.loads(call_kwargs.kwargs["body"])
    user_text = body["messages"][0]["content"][1]["text"]

    assert 'prefer security_features_assessable = "no"' in user_text
    assert "Use [] only when you" in user_text
    assert "can confidently conclude no listed feature is visible." in user_text


# ── (c) response parsed into the correct field structure ──────────────────────


def test_extraction_fields_parsed_from_nova_response(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """Fields from the canned Nova response must appear in the extraction JSON."""
    handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    extraction = json.loads(
        s3.get_object(
            Bucket=_BUCKET,
            Key=f"processed/{_APP_ID}/extraction_transcript.json",
        )["Body"].read()
    )
    page = extraction["pages"][0]

    assert page["seal_type"] == "embossed"
    assert page["grading_scale_format"] == "letter_grade_us"
    assert page["accreditation_claim"] == "ACEN"
    assert page["required_nursing_domains_present"] == [
        "adult_med_surg", "obstetrics", "pediatrics", "psychiatric"
    ]


def test_confidence_stored_per_field(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """Each field with a confidence value must produce a *_confidence sibling key."""
    handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    extraction = json.loads(
        s3.get_object(
            Bucket=_BUCKET,
            Key=f"processed/{_APP_ID}/extraction_transcript.json",
        )["Body"].read()
    )
    page = extraction["pages"][0]

    assert page.get("seal_type_confidence") == "high"
    assert page.get("grading_scale_format_confidence") == "high"
    assert page.get("gpa_arithmetic_consistency_confidence") == "medium"


def test_source_location_stored_per_field(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """Fields with source_location must produce a *_source sibling key."""
    handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    extraction = json.loads(
        s3.get_object(
            Bucket=_BUCKET,
            Key=f"processed/{_APP_ID}/extraction_transcript.json",
        )["Body"].read()
    )
    page = extraction["pages"][0]

    src = page.get("seal_type_source")
    assert src is not None
    assert isinstance(src.get("text_spans"), list)
    assert len(src["text_spans"]) > 0


def test_accreditation_claim_location_mirrored_as_source(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """accreditation_claim_location must also appear as accreditation_claim_source."""
    handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    extraction = json.loads(
        s3.get_object(
            Bucket=_BUCKET,
            Key=f"processed/{_APP_ID}/extraction_transcript.json",
        )["Body"].read()
    )
    page = extraction["pages"][0]

    assert page.get("accreditation_claim_source") is not None
    assert page["accreditation_claim_source"] == page["accreditation_claim_location"]


# ── (d) invalid enum values trigger WARNING, not a crash ─────────────────────


def test_invalid_enum_value_warns_not_crashes(
    s3_with_transcript, extract_event, lambda_context, caplog
):
    """An unexpected enum value from Nova must log a WARNING and not raise."""
    bad_page = dict(_CANNED_NOVA_PAGE)
    bad_page["seal_type"] = {"value": "NOT_A_REAL_ENUM", "confidence": "high"}

    mock_client = _make_bedrock_mock(page_data=bad_page)
    with patch.object(_mod, "_bedrock", mock_client), \
         caplog.at_level(logging.WARNING, logger="extract_handler"):
        result = handler(extract_event, lambda_context)

    # Handler must not raise — it returns normally.
    assert result["applicationId"] == _APP_ID

    warning_texts = " ".join(r.message for r in caplog.records)
    assert "NOT_A_REAL_ENUM" in warning_texts


def test_invalid_array_enum_element_warns_not_crashes(
    s3_with_transcript, extract_event, lambda_context, caplog
):
    """An unexpected element in an array field must log a WARNING and not raise."""
    bad_page = dict(_CANNED_NOVA_PAGE)
    bad_page["required_nursing_domains_present"] = {
        "value": ["adult_med_surg", "UNKNOWN_DOMAIN"],
        "confidence": "medium",
    }

    mock_client = _make_bedrock_mock(page_data=bad_page)
    with patch.object(_mod, "_bedrock", mock_client), \
         caplog.at_level(logging.WARNING, logger="extract_handler"):
        result = handler(extract_event, lambda_context)

    assert result["applicationId"] == _APP_ID
    warning_texts = " ".join(r.message for r in caplog.records)
    assert "UNKNOWN_DOMAIN" in warning_texts


# ── (e) merged extraction document has the right page_count ──────────────────


def test_page_count_matches_pdf(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """page_count in extraction JSON must equal the number of pages in pages[]."""
    result = handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    extraction = json.loads(
        s3.get_object(Bucket=_BUCKET, Key=result["extraction_s3_key"])["Body"].read()
    )

    assert extraction["page_count"] == result["page_count"]
    assert len(extraction["pages"]) == extraction["page_count"]


def test_page_count_multi_page(
    s3_with_transcript, extract_event, lambda_context
):
    """A 2-page PDF must produce page_count=2 and two page records."""
    fake_images = [
        Image.new("RGB", (850, 1100), color="white"),
        Image.new("RGB", (850, 1100), color="white"),
    ]
    mock_client = _make_bedrock_mock()
    with patch.object(_mod, "_bedrock", mock_client), \
         patch.object(_mod, "convert_from_path", return_value=fake_images):
        result = handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    extraction = json.loads(
        s3.get_object(Bucket=_BUCKET, Key=result["extraction_s3_key"])["Body"].read()
    )
    assert extraction["page_count"] == 2
    assert len(extraction["pages"]) == 2


# ── (f) bedrock_model_id and prompt_version appear in metadata ────────────────


def test_extraction_metadata_fields_present(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """Extraction JSON must contain bedrock_model_id, prompt_version, extraction_ts."""
    handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    extraction = json.loads(
        s3.get_object(
            Bucket=_BUCKET,
            Key=f"processed/{_APP_ID}/extraction_transcript.json",
        )["Body"].read()
    )

    assert extraction["bedrock_model_id"] == _mod.BEDROCK_MODEL_ID
    assert extraction["prompt_version"] == "1.0"
    assert "extraction_ts" in extraction
    assert extraction["extraction_ts"].endswith("+00:00")


# ── (g) source_location.page_number stamped correctly per page ────────────────


def test_source_location_page_number_single_page(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """source_location.page_number must equal 1 for a single-page transcript."""
    handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    extraction = json.loads(
        s3.get_object(
            Bucket=_BUCKET,
            Key=f"processed/{_APP_ID}/extraction_transcript.json",
        )["Body"].read()
    )
    page = extraction["pages"][0]

    # seal_type_source has a source_location in the canned fixture.
    assert page["seal_type_source"]["page_number"] == 1


def test_source_location_page_number_multi_page(
    s3_with_transcript, extract_event, lambda_context
):
    """source_location.page_number must reflect the actual page index, not always 1."""
    fake_images = [
        Image.new("RGB", (850, 1100), color="white"),
        Image.new("RGB", (850, 1100), color="white"),
    ]
    # Nova might return page_number=1 in the raw JSON for both pages; the handler
    # must overwrite it with the actual index (1-based).
    mock_client = _make_bedrock_mock()
    with patch.object(_mod, "_bedrock", mock_client), \
         patch.object(_mod, "convert_from_path", return_value=fake_images):
        handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    extraction = json.loads(
        s3.get_object(
            Bucket=_BUCKET,
            Key=f"processed/{_APP_ID}/extraction_transcript.json",
        )["Body"].read()
    )
    assert extraction["pages"][0]["seal_type_source"]["page_number"] == 1
    assert extraction["pages"][1]["seal_type_source"]["page_number"] == 2


# ── (h) extraction JSON written to S3 has expected top-level shape ─────────────


def test_extraction_json_top_level_shape(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """Extraction JSON must have schema_version, application_id, document_type,
    page_count, bedrock_model_id, prompt_version, extraction_ts, and pages."""
    handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    extraction = json.loads(
        s3.get_object(
            Bucket=_BUCKET,
            Key=f"processed/{_APP_ID}/extraction_transcript.json",
        )["Body"].read()
    )

    for key in (
        "schema_version",
        "application_id",
        "document_type",
        "page_count",
        "bedrock_model_id",
        "prompt_version",
        "extraction_ts",
        "pages",
    ):
        assert key in extraction, f"Missing top-level key: {key}"

    assert extraction["schema_version"] == "1.0"
    assert extraction["application_id"] == _APP_ID
    assert extraction["document_type"] == "TRANSCRIPT"
    assert isinstance(extraction["pages"], list)


def test_extraction_json_page_has_all_section_fields(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """Every Section 1/2/3 field must be present in the page record."""
    handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    extraction = json.loads(
        s3.get_object(
            Bucket=_BUCKET,
            Key=f"processed/{_APP_ID}/extraction_transcript.json",
        )["Body"].read()
    )
    page = extraction["pages"][0]

    expected_fields = [
        # Section 1
        "seal_type", "seal_quality", "print_technology", "paper_size_format",
        "text_alignment", "document_provenance_appearance",
        "security_features_present", "security_features_assessable",
        # Section 2
        "grading_scale_format", "language_of_issue", "course_relevance",
        "duplicate_courses_detected", "suspicious_course_names",
        "gpa_arithmetic_consistency", "dates_chronology_ok",
        "dates_chronology_issue", "program_duration_consistency",
        # Section 3
        "accreditation_claim", "accreditation_claim_location",
        "diploma_mill_language_detected", "diploma_mill_phrases_found",
        "institution_address_present", "institution_phone_present",
        "institution_website_present", "graduation_confirmation_present",
        "required_nursing_domains_present",
    ]
    for field in expected_fields:
        assert field in page, f"Missing field in page record: {field}"


# ── Retained from Session 1: S3 mechanics and error handling ─────────────────


def test_handler_returns_application_id(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    result = handler(extract_event, lambda_context)
    assert result["applicationId"] == _APP_ID


def test_handler_returns_page_count(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    result = handler(extract_event, lambda_context)
    assert isinstance(result["page_count"], int)
    assert result["page_count"] >= 1


def test_handler_returns_extraction_s3_key(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    result = handler(extract_event, lambda_context)
    assert result["extraction_s3_key"] == (
        f"processed/{_APP_ID}/extraction_transcript.json"
    )


def test_page_images_written_to_s3(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """One non-empty PNG per PDF page must be written to processed/{appId}/."""
    result = handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    for page_num in range(1, result["page_count"] + 1):
        img_key = f"processed/{_APP_ID}/page_transcript_{page_num}.png"
        obj = s3.get_object(Bucket=_BUCKET, Key=img_key)
        assert len(obj["Body"].read()) > 0, f"Page image is empty: {img_key}"


def test_page_extraction_has_page_number_and_dimensions(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
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


def test_missing_pdf_raises(s3_bucket, extract_event, lambda_context):
    """Handler must raise when the PDF key does not exist in S3."""
    mock_client = _make_bedrock_mock()
    with patch.object(_mod, "_bedrock", mock_client):
        with pytest.raises(Exception):
            handler(extract_event, lambda_context)


def test_corrupt_pdf_raises(s3_bucket, extract_event, lambda_context):
    """Handler must raise when the uploaded file is not a valid PDF."""
    s3_bucket.put_object(
        Bucket=_BUCKET,
        Key=_PDF_KEY,
        Body=b"this is not a valid PDF file",
    )
    mock_client = _make_bedrock_mock()
    with patch.object(_mod, "_bedrock", mock_client):
        with pytest.raises(Exception):
            handler(extract_event, lambda_context)

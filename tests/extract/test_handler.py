"""Unit tests for ExtractLambda — Bedrock Nova Pro integration.

Strategy
--------
- S3 is mocked via moto (mock_aws context).
- bedrock-runtime is NOT contacted.  ``_mod._bedrock`` is replaced with a
  ``MagicMock`` whose ``invoke_model`` side_effect returns a fresh ``BytesIO``
  wrapping the canned model fixture on every call.
- ``convert_from_path`` is patched for the default unit-test path so tests do
  not depend on an external Poppler installation.  The fake converter returns
  a deterministic single-page image for valid PDFs and raises for corrupt
  inputs.
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

# ── Canned model response ─────────────────────────────────────────────────────
# Represents a clean Mississippi-domestic single-page transcript as Nova Pro
# would return it.  All enum values are from the extraction-vocabulary.md vocabulary.
_CANNED_PAGE: dict = {
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

_CANNED_TEXTRACT: dict = {
    "job_id": "textract-job-123",
    "source_s3_key": _PDF_KEY,
    "feature_types": ["TABLES", "FORMS", "QUERIES", "SIGNATURES", "LAYOUT"],
    "analyze_document_model_version": "1.0",
    "document_metadata": {"Pages": 1},
    "job_status": "SUCCEEDED",
    "warnings": [],
    "pages": [
        {
            "page_number": 1,
            "raw_text": (
                "Copiah-Lincoln Community College\n"
                "Official Transcript\n"
                "Practical Nursing\n"
                "Grade Point: A=4.0, B=3.0, C=2.0, D=1.0, F=0.0\n"
                "Cumulative GPA: 4.00\n"
                "Total Credits: 16"
            ),
            "lines": [
                {
                    "text": "Copiah-Lincoln Community College",
                    "confidence": 99.0,
                    "geometry": {},
                }
            ],
            "words": [],
            "tables": [
                {
                    "id": "table-1",
                    "entity_types": ["STRUCTURED_TABLE"],
                    "confidence": 98.0,
                    "geometry": {},
                    "rows": [
                        ["Course", "Title", "Credit Hours", "Grade", "Quality Points"],
                        ["PNV 1116", "Practical Nursing Foundations", "16", "A", "64"],
                        ["Cumulative GPA", "4.00", "", "", ""],
                        ["Total Credits", "16", "", "", ""],
                    ],
                    "cells": [],
                    "titles": [],
                    "footers": [],
                }
            ],
            "forms": [
                {
                    "key": "Student",
                    "value": "Jane Applicant",
                    "key_confidence": 97.0,
                    "value_confidence": 97.0,
                    "key_geometry": {},
                    "value_geometry": [],
                }
            ],
            "layouts": [
                {
                    "id": "layout-1",
                    "type": "LAYOUT_TITLE",
                    "text": "Official Transcript",
                    "confidence": 98.0,
                    "geometry": {},
                }
            ],
            "queries": [
                {
                    "alias": "institution",
                    "question": "What institution issued this transcript?",
                    "pages": [],
                    "answers": [
                        {
                            "text": "Copiah-Lincoln Community College",
                            "confidence": 99.0,
                            "geometry": {},
                        }
                    ],
                }
            ],
            "signatures": [
                {
                    "id": "sig-1",
                    "confidence": 96.0,
                    "geometry": {},
                }
            ],
        }
    ],
}

_BULKY_TEXTRACT_PAGE: dict = {
    "page_number": 1,
    "raw_text": "A" * 20000,
    "lines": [
        {"text": f"Line {idx}", "confidence": 99.0, "geometry": {"bbox": idx}}
        for idx in range(400)
    ],
    "words": [
        {"text": f"word{idx}", "confidence": 99.0, "geometry": {"bbox": idx}}
        for idx in range(1000)
    ],
    "tables": [
        {
            "titles": ["Courses"],
            "footers": [],
            "entity_types": ["STRUCTURED_TABLE"],
            "confidence": 98.0,
            "geometry": {"bbox": table_idx},
            "rows": [[f"cell {row_idx}-{col_idx}" for col_idx in range(8)]
                     for row_idx in range(200)],
            "cells": [
                {"text": "x", "geometry": {"bbox": row_idx}}
                for row_idx in range(200)
            ],
        }
        for table_idx in range(20)
    ],
    "forms": [
        {
            "key": f"Key {idx}",
            "value": "B" * 1000,
            "key_confidence": 99.0,
            "value_confidence": 99.0,
            "key_geometry": {"bbox": idx},
            "value_geometry": [{"bbox": idx}],
        }
        for idx in range(120)
    ],
    "layouts": [
        {
            "type": "LAYOUT_TEXT",
            "text": "C" * 1000,
            "confidence": 99.0,
            "geometry": {"bbox": idx},
        }
        for idx in range(200)
    ],
    "queries": [],
    "signatures": [{"id": "sig", "confidence": 96.0, "geometry": {"bbox": 1}}],
}


def _model_response_body(page_data: dict | None = None) -> bytes:
    """Return a serialised Bedrock Nova Pro invoke_model response body."""
    return _model_response_body_from_text(json.dumps(page_data or _CANNED_PAGE))


def _model_response_body_from_text(text: str, stop_reason: str = "end_turn") -> bytes:
    """Return a serialised Bedrock Nova Pro invoke_model response body with custom text."""
    return json.dumps({
        "output": {"message": {"role": "assistant", "content": [{"text": text}]}},
        "stopReason": stop_reason,
        "usage": {"inputTokens": 1234, "outputTokens": 567},
    }).encode("utf-8")


def _make_bedrock_mock(page_data: dict | None = None) -> MagicMock:
    """Return a MagicMock bedrock client whose invoke_model returns fresh BytesIO
    on every call (a consumed BytesIO would give empty reads on call 2+)."""
    mock_client = MagicMock()
    body_bytes = _model_response_body(page_data)
    mock_client.invoke_model.side_effect = (
        lambda **kwargs: {"body": BytesIO(body_bytes)}
    )
    return mock_client


def _fake_convert_from_path(pdf_path: str):
    """Return a deterministic image for valid PDFs without requiring Poppler."""
    pdf_bytes = Path(pdf_path).read_bytes()
    if not pdf_bytes.startswith(b"%PDF-"):
        raise ValueError("Unable to get page count. Is poppler installed and in PATH?")
    return [Image.new("RGB", (850, 1100), color="white")]


def _make_bedrock_text_mock(text: str, stop_reason: str = "end_turn") -> MagicMock:
    """Return a MagicMock bedrock client whose text is controlled by the test."""
    mock_client = MagicMock()
    body_bytes = _model_response_body_from_text(text, stop_reason=stop_reason)
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
    """Replace _mod._bedrock with a mock that returns the canned model fixture."""
    mock_client = _make_bedrock_mock()
    with patch.object(_mod, "_bedrock", mock_client):
        yield mock_client


@pytest.fixture(autouse=True)
def patched_pdf_conversion():
    """Keep extract unit tests independent of the host Poppler toolchain."""
    with patch.object(_mod, "convert_from_path", side_effect=_fake_convert_from_path):
        yield


@pytest.fixture(autouse=True)
def patched_textract_analysis():
    """Keep extract unit tests independent of the live Textract API."""
    with patch.object(
        _mod,
        "_analyze_transcript_with_textract",
        side_effect=lambda *args, **kwargs: json.loads(json.dumps(_CANNED_TEXTRACT)),
    ):
        yield


def _bedrock_bodies(mock_client: MagicMock) -> list[dict]:
    return [
        json.loads(call_kwargs.kwargs["body"])
        for call_kwargs in mock_client.invoke_model.call_args_list
    ]


def _visual_bedrock_body(mock_client: MagicMock) -> dict:
    for body in _bedrock_bodies(mock_client):
        content = body["messages"][0]["content"]
        if any("image" in item for item in content):
            return body
    raise AssertionError("No image-based Nova invocation found")


def _textract_structuring_body(mock_client: MagicMock) -> dict:
    for body in _bedrock_bodies(mock_client):
        content = body["messages"][0]["content"]
        if content and all("image" not in item for item in content):
            return body
    raise AssertionError("No Textract-only Nova invocation found")


# ── (a) invoke_model called once per page ─────────────────────────────────────


def test_invoke_model_called_once_per_page(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """Each page gets one visual call and one Textract-only structuring call."""
    handler(extract_event, lambda_context)
    assert bedrock_mock.invoke_model.call_count == 2


def test_invoke_model_called_per_page_multi(
    s3_with_transcript, extract_event, lambda_context
):
    """invoke_model call count must match visual + structuring calls per page."""
    fake_images = [
        Image.new("RGB", (850, 1100), color="white"),
        Image.new("RGB", (850, 1100), color="white"),
    ]
    mock_client = _make_bedrock_mock()
    with patch.object(_mod, "_bedrock", mock_client), \
         patch.object(_mod, "convert_from_path", return_value=fake_images):
        handler(extract_event, lambda_context)

    assert mock_client.invoke_model.call_count == 4


# ── (b) system prompt contains vocabulary enum values ─────────────────────────


def test_invoke_model_body_contains_system_prompt_enums(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """The body sent to invoke_model must embed vocabulary enum strings."""
    handler(extract_event, lambda_context)

    body = _visual_bedrock_body(bedrock_mock)

    # Nova Pro format: system is an array of {"text": "..."} objects.
    system_arr = body["system"]
    assert isinstance(system_arr, list) and len(system_arr) == 1
    system_text = system_arr[0]["text"]
    assert isinstance(system_text, str)
    # A sample of enum values that must appear in the system prompt.
    for token in ("high", "medium", "low", "source_location", "text_spans"):
        assert token in system_text, (
            f"Expected token '{token}' missing from system prompt"
        )


def test_invoke_model_body_contains_user_prompt_enums(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """The user message text must include only visual/physical extraction fields."""
    handler(extract_event, lambda_context)

    body = _visual_bedrock_body(bedrock_mock)
    # Nova Pro format: content[1] is {"text": ...}
    user_text = body["messages"][0]["content"][1]["text"]

    prompt_text = user_text.split("=== TEXTRACT_CONTEXT_JSON ===", 1)[0]
    expected_tokens = [
        "embossed", "stamped_ink", "laser", "us_letter",
        "overlapping_text_detected", "identity_redaction_detected",
        "suspected_alteration_fields",
    ]
    for token in expected_tokens:
        assert token in prompt_text, (
            f"Vocabulary token '{token}' missing from user prompt"
        )
    for token in ("courses", "final_cum_gpa_stated", "total_credit_hours"):
        assert token not in prompt_text


def test_invoke_model_uses_configured_output_cap(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """Extractor should request the configured max_tokens budget."""
    handler(extract_event, lambda_context)

    body = _visual_bedrock_body(bedrock_mock)

    assert body["inferenceConfig"]["max_new_tokens"] == _mod.BEDROCK_MAX_NEW_TOKENS


def test_model_json_parser_accepts_markdown_fence(
    s3_with_transcript, extract_event, lambda_context
):
    """Model may occasionally wrap valid JSON in markdown despite the prompt."""
    text = "```json\n" + json.dumps(_CANNED_PAGE) + "\n```"
    mock_client = _make_bedrock_text_mock(text)

    with patch.object(_mod, "_bedrock", mock_client):
        result = handler(extract_event, lambda_context)

    assert result["applicationId"] == _APP_ID


def test_model_json_parser_accepts_preamble(
    s3_with_transcript, extract_event, lambda_context
):
    """Model may occasionally prefix valid JSON with a short acknowledgement."""
    text = "Here is the JSON:\n" + json.dumps(_CANNED_PAGE)
    mock_client = _make_bedrock_text_mock(text)

    with patch.object(_mod, "_bedrock", mock_client):
        result = handler(extract_event, lambda_context)

    assert result["applicationId"] == _APP_ID



def test_invoke_model_body_guides_conservative_watermark_detection(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """Prompt should tell the model to avoid guessing on faint security features."""
    handler(extract_event, lambda_context)

    body = _visual_bedrock_body(bedrock_mock)
    user_text = body["messages"][0]["content"][1]["text"]

    assert 'prefer security_features_assessable = "no"' in user_text
    assert "Use [] only when you" in user_text
    assert "can confidently conclude no listed feature is visible." in user_text


def test_invoke_model_body_contains_textract_context(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """The prompt should include Textract evidence for the current page."""
    handler(extract_event, lambda_context)

    body = _visual_bedrock_body(bedrock_mock)
    user_text = body["messages"][0]["content"][1]["text"]

    assert "TEXTRACT_CONTEXT_JSON" in user_text
    assert "Copiah-Lincoln Community College" in user_text
    assert "STRUCTURED_TABLE" in user_text
    assert "SIGNATURES" in user_text


def test_textract_structuring_call_is_text_only_and_academic(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """The second Nova call uses Textract JSON only to structure academic data."""
    handler(extract_event, lambda_context)

    body = _textract_structuring_body(bedrock_mock)
    content = body["messages"][0]["content"]
    assert len(content) == 1
    assert "image" not in content[0]

    system_text = body["system"][0]["text"]
    user_text = content[0]["text"]
    assert "Do NOT use page-image visual reasoning" in system_text
    assert "courses" in user_text
    assert "final_cum_gpa_stated" in user_text
    assert "TEXTRACT_CONTEXT_JSON" in user_text
    assert "Copiah-Lincoln Community College" in user_text


def test_textract_context_for_nova_omits_token_heavy_fields():
    """Prompt context must not include full geometry, words, or cell objects."""
    context = _mod._textract_context_for_page(
        {
            "feature_types": ["TABLES", "FORMS", "QUERIES", "SIGNATURES", "LAYOUT"],
            "document_metadata": {"Pages": 1},
            "pages": [_BULKY_TEXTRACT_PAGE],
        },
        1,
    )

    page = context["page"]

    assert "words" not in page
    assert "cells" not in page["tables"][0]
    assert "geometry" not in page["lines"][0]
    assert "geometry" not in page["tables"][0]
    assert "key_geometry" not in page["forms"][0]
    assert "geometry" not in page["layouts"][0]
    assert "geometry" not in page["signatures"][0]
    assert len(page["raw_text"]) < len(_BULKY_TEXTRACT_PAGE["raw_text"])
    assert len(page["tables"]) == _mod.NOVA_TEXTRACT_MAX_TABLES
    assert len(page["tables"][0]["rows"]) == _mod.NOVA_TEXTRACT_MAX_TABLE_ROWS
    assert page["omitted_for_prompt_size"]["words"] == 1000


def test_textract_query_answers_are_verified_against_page_evidence():
    page = {
        "raw_text": "Official Transcript\nStudent: Jane Applicant\nInstitution: Delta College",
        "lines": [],
        "tables": [],
        "forms": [],
        "layouts": [],
        "queries": [
            {
                "alias": "applicant_name",
                "answers": [{"text": "Jane Applicant", "confidence": 99.0}],
            },
            {
                "alias": "country",
                "answers": [{"text": "Canada", "confidence": 99.0}],
            },
        ],
    }

    _mod._verify_queries_against_page_evidence(page)

    applicant = page["queries"][0]["answers"][0]
    country = page["queries"][1]["answers"][0]
    assert applicant["verified"] is True
    assert country["verified"] is False

    context = _mod._compact_textract_page_for_nova(page)
    assert context["queries"][0]["answers"][0]["text"] == "Jane Applicant"
    assert context["queries"][1]["answers"] == []


def test_issuing_institution_prefers_header_over_issued_to_recipient():
    page = {
        "raw_text": (
            "NORTHEAST\n"
            "MISSISSIPPI COMMUNITY COLLEGE\n"
            "ADMISSIONS AND RECORDS\n"
            "Issued To: MISSISSIPPI BOARD OF NURSING\n"
            "RIDGELAND, MS 39157"
        ),
        "lines": [
            {"text": "NORTHEAST", "confidence": 99.0},
            {"text": "MISSISSIPPI COMMUNITY COLLEGE", "confidence": 99.0},
            {"text": "ADMISSIONS AND RECORDS", "confidence": 99.0},
            {"text": "Issued To: MISSISSIPPI BOARD OF NURSING", "confidence": 99.0},
            {"text": "RIDGELAND, MS 39157", "confidence": 99.0},
        ],
        "tables": [],
        "forms": [],
        "layouts": [],
        "queries": [
            {
                "alias": "institution",
                "answers": [
                    {
                        "text": "MISSISSIPPI BOARD OF NURSING",
                        "confidence": 76.0,
                        "verified": True,
                    }
                ],
            }
        ],
    }

    assert _mod._extract_issuing_institution_from_textract(page) == (
        "Northeast Mississippi Community College",
        "NORTHEAST MISSISSIPPI COMMUNITY COLLEGE",
    )
    assert _mod._is_recipient_institution_answer(
        page,
        "MISSISSIPPI BOARD OF NURSING",
    ) is True


def test_textract_backed_fields_use_header_institution_not_recipient_query():
    page = {
        "page_number": 1,
        "raw_text": (
            "NORTHEAST\n"
            "MISSISSIPPI COMMUNITY COLLEGE\n"
            "Issued To: MISSISSIPPI BOARD OF NURSING"
        ),
        "lines": [
            {"text": "NORTHEAST", "confidence": 99.0},
            {"text": "MISSISSIPPI COMMUNITY COLLEGE", "confidence": 99.0},
            {"text": "Issued To: MISSISSIPPI BOARD OF NURSING", "confidence": 99.0},
        ],
        "tables": [],
        "forms": [],
        "layouts": [],
        "queries": [
            {
                "alias": "institution",
                "answers": [
                    {
                        "text": "MISSISSIPPI BOARD OF NURSING",
                        "confidence": 76.0,
                        "verified": True,
                    }
                ],
            }
        ],
        "signatures": [],
    }
    record = {"page_number": 1}

    _mod._apply_textract_backed_page_fields(
        record,
        {"pages": [page]},
        1,
        Image.new("RGB", (850, 1100), color="white"),
    )

    assert record["institution"] == "Northeast Mississippi Community College"
    assert record["institution_source"]["text_spans"] == [
        "NORTHEAST MISSISSIPPI COMMUNITY COLLEGE"
    ]


def test_course_code_parser_rejects_term_and_month_rows():
    assert _mod._find_course_code("Fall 2024") is None
    assert _mod._find_course_code("Only Admit: Fall 2024") is None
    assert _mod._find_course_code("High School for Transfers 21-MAY-2022") is None
    assert _mod._find_course_code("NUR 1118 Nursing Fundamentals") == "NUR 1118"


def test_academic_table_parser_does_not_turn_terms_into_courses():
    page = {
        "page_number": 1,
        "raw_text": "",
        "tables": [
            {
                "rows": [
                    ["Course", "Title", "Credit Hours", "Grade", "Quality Points"],
                    ["Fall 2024", "", "", "", ""],
                    ["Only Admit:", "Fall 2024", "", "", ""],
                    ["High School:", "High School for Transfers 21-MAY-2022", "", "", ""],
                    ["NUR 1118", "Nursing Fundamentals", "8.00", "B", "24.00"],
                    ["Fall 2025", "", "", "", ""],
                    ["NUR 2449", "Nursing Care of the Adult II", "9.00", "IN PROGRESS", ""],
                ],
            }
        ],
        "lines": [],
        "forms": [],
        "layouts": [],
        "queries": [],
    }

    parsed = _mod._extract_academic_tables(page, 1)
    codes = [course["course_code"] for course in parsed["courses"]]

    assert codes == ["NUR 1118", "NUR 2449"]
    assert all(not code.startswith(("FALL", "MAY")) for code in codes)
    assert [semester["term"] for semester in parsed["semesters"]] == [
        "Fall 2024",
        "Fall 2025",
    ]


def test_nova_textract_academic_response_requires_textract_evidence():
    page = _CANNED_TEXTRACT["pages"][0]
    normalized = _mod._normalize_nova_academic_response_shape(
        {
            "final_cum_gpa_stated": {
                "value": 3.2,
                "confidence": "high",
                "source_location": {
                    "page_number": 1,
                    "text_spans": ["Final GPA: 3.20"],
                },
            }
        },
        page,
        1,
    )

    assert normalized == {}


def test_nova_textract_academic_response_can_fill_deterministic_gap():
    page = _CANNED_TEXTRACT["pages"][0]
    normalized = _mod._normalize_nova_academic_response_shape(
        {
            "courses": {
                "value": [
                    {
                        "code": "PNV 1116",
                        "course_code": "PNV 1116",
                        "name": "Practical Nursing Foundations",
                        "course_title": "Practical Nursing Foundations",
                        "credit_hours": 16,
                        "grade": "A",
                        "grade_points": 64,
                        "semester": 1,
                        "retake_marker": False,
                        "transfer_marker": False,
                        "source_location": {
                            "page_number": 1,
                            "text_spans": [
                                "PNV 1116 Practical Nursing Foundations 16 A 64"
                            ],
                        },
                    }
                ],
                "confidence": "high",
                "source_location": {
                    "page_number": 1,
                    "text_spans": [
                        "PNV 1116 Practical Nursing Foundations 16 A 64"
                    ],
                },
            }
        },
        page,
        1,
    )
    record = {"page_number": 1}

    _mod._apply_nova_textract_academic_fields(record, normalized, 1)

    assert record["courses"][0]["code"] == "PNV 1116"
    assert record["courses_confidence"] == "medium"
    assert record["courses_source"]["method"] == "nova_textract_interpreter"


def test_nova_textract_academic_conflict_is_preserved_for_review():
    page = _CANNED_TEXTRACT["pages"][0]
    normalized = _mod._normalize_nova_academic_response_shape(
        {
            "final_cum_gpa_stated": {
                "value": 4.0,
                "confidence": "high",
                "source_location": {
                    "page_number": 1,
                    "text_spans": ["Cumulative GPA: 4.00"],
                },
            }
        },
        page,
        1,
    )
    record = {
        "page_number": 1,
        "final_cum_gpa_stated": 3.2,
        "final_cum_gpa_stated_confidence": "high",
    }

    _mod._apply_nova_textract_academic_fields(record, normalized, 1)

    assert record["final_cum_gpa_stated"] == 3.2
    conflict = record["academic_extraction_conflicts"][0]
    assert conflict["field"] == "final_cum_gpa_stated"
    assert conflict["nova_textract_value"] == 4


def test_nova_response_wrapper_is_unwrapped():
    normalized = _mod._normalize_nova_response_shape(
        {
            "fields": {
                "seal_type": {
                    "value": "embossed",
                    "confidence": "high",
                    "source_location": None,
                }
            }
        },
        1,
    )
    assert "seal_type" in normalized


def test_generic_nova_field_record_is_ignored():
    normalized = _mod._normalize_nova_response_shape(
        {"value": None, "confidence": "low", "source_location": None},
        1,
    )
    assert normalized == {}


def test_identity_redaction_bar_detection():
    img = Image.new("RGB", (1000, 1200), "white")
    for x in range(120, 360):
        for y in range(190, 210):
            img.putpixel((x, y), (0, 0, 0))

    assert _mod._detect_identity_redaction_marks(img) is True


# ── (c) response parsed into the correct field structure ──────────────────────


def test_extraction_fields_parsed_from_nova_response(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """Visual fields come from Nova; academic rows come from Textract tables."""
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
    assert page["courses"][0]["code"] == "PNV 1116"
    assert page["courses"][0]["credit_hours"] == 16
    assert page["courses"][0]["grade"] == "A"
    assert page["final_cum_gpa_stated"] == 4
    assert page["total_credit_hours"] == 16
    assert page["program_type"] == "ms_practical_nursing"
    assert "accreditation_claim" not in page


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
    assert page.get("courses_confidence") == "high"
    assert page.get("final_cum_gpa_stated_confidence") == "high"
    assert page.get("total_credit_hours_confidence") == "high"


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


def test_nova_non_visual_fields_are_ignored(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """Nova output cannot author academic/program fields."""
    handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    extraction = json.loads(
        s3.get_object(
            Bucket=_BUCKET,
            Key=f"processed/{_APP_ID}/extraction_transcript.json",
        )["Body"].read()
    )
    page = extraction["pages"][0]

    assert "accreditation_claim" not in page
    assert "accreditation_claim_source" not in page
    assert "required_nursing_domains_present" not in page


# ── (d) invalid enum values trigger WARNING, not a crash ─────────────────────


def test_invalid_enum_value_warns_not_crashes(
    s3_with_transcript, extract_event, lambda_context, caplog
):
    """An unexpected enum value from the model must log a WARNING and not raise."""
    bad_page = dict(_CANNED_PAGE)
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
    bad_page = dict(_CANNED_PAGE)
    bad_page["security_features_present"] = {
        "value": ["watermark", "UNKNOWN_SECURITY_FEATURE"],
        "confidence": "medium",
    }

    mock_client = _make_bedrock_mock(page_data=bad_page)
    with patch.object(_mod, "_bedrock", mock_client), \
         caplog.at_level(logging.WARNING, logger="extract_handler"):
        result = handler(extract_event, lambda_context)

    assert result["applicationId"] == _APP_ID
    warning_texts = " ".join(r.message for r in caplog.records)
    assert "UNKNOWN_SECURITY_FEATURE" in warning_texts


def test_markdown_wrapped_model_json_is_recovered():
    raw_text = f"```json\n{json.dumps(_CANNED_PAGE, indent=2)}\n```"

    parsed = _mod._parse_model_json_object(raw_text)

    assert parsed == _CANNED_PAGE


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
    """Extraction JSON must contain model, prompt, Textract, and timestamp metadata."""
    handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    extraction = json.loads(
        s3.get_object(
            Bucket=_BUCKET,
            Key=f"processed/{_APP_ID}/extraction_transcript.json",
        )["Body"].read()
    )

    assert extraction["bedrock_model_id"] == _mod.BEDROCK_MODEL_ID
    assert extraction["prompt_version"] == _mod.PROMPT_VERSION
    assert extraction["textract_s3_key"] == f"processed/{_APP_ID}/textract_TRANSCRIPT.json"
    assert extraction["textract"]["feature_types"] == [
        "TABLES", "FORMS", "QUERIES", "SIGNATURES", "LAYOUT"
    ]
    assert "extraction_ts" in extraction
    assert extraction["extraction_ts"].endswith("+00:00")


def test_textract_json_written_to_s3(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """The normalized Textract evidence package must be persisted for audit."""
    result = handler(extract_event, lambda_context)

    s3 = boto3.client("s3", region_name="us-east-1")
    textract_doc = json.loads(
        s3.get_object(Bucket=_BUCKET, Key=result["textract_s3_key"])["Body"].read()
    )

    assert textract_doc["job_id"] == "textract-job-123"
    assert textract_doc["pages"][0]["raw_text"]
    assert textract_doc["pages"][0]["tables"][0]["rows"][1] == [
        "PNV 1116", "Practical Nursing Foundations", "16", "A", "64"
    ]
    assert textract_doc["pages"][0]["signatures"][0]["id"] == "sig-1"


def test_document_record_written_with_page_count(
    s3_with_transcript, bedrock_mock, extract_event, lambda_context
):
    """Extract should publish DOCUMENT#TRANSCRIPT metadata for the dashboard."""
    table_name = "msbn-applications"
    dynamo = boto3.resource("dynamodb", region_name="us-east-1")
    table = dynamo.create_table(
        TableName=table_name,
        KeySchema=[
            {"AttributeName": "PK", "KeyType": "HASH"},
            {"AttributeName": "SK", "KeyType": "RANGE"},
        ],
        AttributeDefinitions=[
            {"AttributeName": "PK", "AttributeType": "S"},
            {"AttributeName": "SK", "AttributeType": "S"},
        ],
        BillingMode="PAY_PER_REQUEST",
    )

    with patch.object(_mod, "TABLE_NAME", table_name):
        handler(extract_event, lambda_context)

    item = table.get_item(
        Key={"PK": f"APP#{_APP_ID}", "SK": "DOCUMENT#TRANSCRIPT"}
    )["Item"]
    assert item["page_count"] == 1
    assert item["s3_extraction_key"] == f"processed/{_APP_ID}/extraction_transcript.json"
    assert item["s3_textract_key"] == f"processed/{_APP_ID}/textract_TRANSCRIPT.json"


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
    # The model might return page_number=1 in the raw JSON for both pages; the handler
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
        "textract_s3_key",
        "textract",
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
    """Page records combine Nova visual findings with Textract academic fields."""
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
        "seal_type", "seal_quality", "print_technology", "paper_size_format",
        "text_alignment", "document_provenance_appearance",
        "security_features_present", "security_features_assessable",
        "courses", "final_cum_gpa_stated", "total_credit_hours",
        "program_type", "grading_scale_format",
    ]
    for field in expected_fields:
        assert field in page, f"Missing field in page record: {field}"

    for field in (
        "course_relevance",
        "duplicate_courses_detected",
        "gpa_arithmetic_consistency",
        "accreditation_claim",
        "required_nursing_domains_present",
    ):
        assert field not in page


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

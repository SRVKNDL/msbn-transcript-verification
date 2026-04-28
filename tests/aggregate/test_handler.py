"""Tests for AggregationLambda.

Verifies the handler flattens per-page extraction JSON into a document-level
aggregation.json:

- Reads ``processed/{appId}/extraction_transcript.json`` from S3.
- For scalar/enum fields: picks the value from the page with the highest
  confidence; matching ``_source`` and ``_confidence`` are copied.
- For array fields (security_features_present, suspicious_course_names,
  diploma_mill_phrases_found, required_nursing_domains_present):
  unions values across all pages, deduplicated.
- Writes ``processed/{appId}/aggregation.json``.
- Returns {"applicationId", "aggregation_s3_key"}.
"""

import importlib.util
import json
import os
import sys

import boto3
import pytest
from moto import mock_aws

os.environ.setdefault("AWS_ACCESS_KEY_ID", "testing")
os.environ.setdefault("AWS_SECRET_ACCESS_KEY", "testing")
os.environ.setdefault("AWS_DEFAULT_REGION", "us-east-1")
os.environ.setdefault("BUCKET_NAME", "msbn-transcripts-test")

_HERE = os.path.dirname(__file__)
_HANDLER_PATH = os.path.normpath(
    os.path.join(_HERE, "../../services/aggregate/handler.py")
)
_spec = importlib.util.spec_from_file_location("aggregate_handler", _HANDLER_PATH)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
handler = _mod.handler

_BUCKET = "msbn-transcripts-test"


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture()
def s3_bucket():
    with mock_aws():
        client = boto3.client("s3", region_name="us-east-1")
        client.create_bucket(Bucket=_BUCKET)
        yield client


def _put_extraction(s3_client, app_id: str, pages: list[dict]) -> str:
    key = f"processed/{app_id}/extraction_transcript.json"
    doc = {
        "schema_version": "1.0",
        "application_id": app_id,
        "document_type": "TRANSCRIPT",
        "page_count": len(pages),
        "textract_s3_key": f"processed/{app_id}/textract_TRANSCRIPT.json",
        "textract": {
            "feature_types": ["TABLES", "FORMS", "QUERIES", "SIGNATURES", "LAYOUT"],
            "document_metadata": {"Pages": len(pages)},
            "pages": [{"page_number": 1, "raw_text": "Official Transcript"}],
        },
        "bedrock_model_id": "amazon.nova-pro-v1:0",
        "prompt_version": "1.0",
        "extraction_ts": "2026-04-16T00:00:00Z",
        "pages": pages,
    }
    s3_client.put_object(
        Bucket=_BUCKET, Key=key, Body=json.dumps(doc).encode("utf-8")
    )
    return key


def _make_event(app_id: str, extraction_key: str) -> dict:
    return {
        "applicationId": app_id,
        "extraction_s3_key": extraction_key,
        "bucket": _BUCKET,
    }


def _read_aggregation(s3_client, aggregation_key: str) -> dict:
    obj = s3_client.get_object(Bucket=_BUCKET, Key=aggregation_key)
    return json.loads(obj["Body"].read().decode("utf-8"))


# ── Return shape ──────────────────────────────────────────────────────────────


def test_handler_returns_application_id_and_key(s3_bucket, lambda_context):
    pages = [{"page_number": 1, "seal_type": "embossed",
              "seal_type_confidence": "high"}]
    extraction_key = _put_extraction(s3_bucket, "APP-R1", pages)

    result = handler(_make_event("APP-R1", extraction_key), lambda_context)

    assert result["applicationId"] == "APP-R1"
    assert result["aggregation_s3_key"] == "processed/APP-R1/aggregation.json"


# ── S3 read ───────────────────────────────────────────────────────────────────


def test_handler_reads_extraction_from_s3(s3_bucket, lambda_context):
    pages = [{"page_number": 1, "seal_type": "embossed",
              "seal_type_confidence": "high"}]
    extraction_key = _put_extraction(s3_bucket, "APP-R2", pages)

    handler(_make_event("APP-R2", extraction_key), lambda_context)

    # Aggregation must now exist at the expected key.
    aggregation = _read_aggregation(
        s3_bucket, "processed/APP-R2/aggregation.json"
    )
    assert aggregation["applicationId"] == "APP-R2"
    assert aggregation["seal_type"] == "embossed"


# ── S3 write ──────────────────────────────────────────────────────────────────


def test_aggregation_written_to_correct_s3_path(s3_bucket, lambda_context):
    pages = [{"page_number": 1, "course_relevance": "nursing_standard",
              "course_relevance_confidence": "high"}]
    extraction_key = _put_extraction(s3_bucket, "APP-W1", pages)

    result = handler(_make_event("APP-W1", extraction_key), lambda_context)

    # The handler's return value and the actual S3 object must agree.
    s3_bucket.get_object(Bucket=_BUCKET, Key=result["aggregation_s3_key"])


# ── Flatten: single page ──────────────────────────────────────────────────────


def test_single_page_flattens_to_top_level(s3_bucket, lambda_context):
    pages = [{
        "page_number": 1,
        "seal_type": "embossed",
        "seal_type_confidence": "high",
        "seal_type_source": {"page_number": 1, "text_spans": ["Official Seal"]},
        "grading_scale_format": "letter_grade_us",
        "grading_scale_format_confidence": "high",
        "accreditation_claim": "ACEN",
        "accreditation_claim_confidence": "high",
    }]
    extraction_key = _put_extraction(s3_bucket, "APP-F1", pages)

    handler(_make_event("APP-F1", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-F1/aggregation.json")
    assert agg["seal_type"] == "embossed"
    assert agg["seal_type_confidence"] == "high"
    assert agg["seal_type_source"]["page_number"] == 1
    assert agg["grading_scale_format"] == "letter_grade_us"
    assert agg["accreditation_claim"] == "ACEN"


def test_textract_evidence_is_preserved(s3_bucket, lambda_context):
    pages = [{"page_number": 1, "seal_type": "embossed",
              "seal_type_confidence": "high"}]
    extraction_key = _put_extraction(s3_bucket, "APP-TEXTRACT", pages)

    handler(_make_event("APP-TEXTRACT", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-TEXTRACT/aggregation.json")
    assert agg["textract_s3_key"] == "processed/APP-TEXTRACT/textract_TRANSCRIPT.json"
    assert agg["textract"]["feature_types"] == [
        "TABLES", "FORMS", "QUERIES", "SIGNATURES", "LAYOUT"
    ]
    assert agg["textract"]["pages"][0]["raw_text"] == "Official Transcript"


# ── Pick highest confidence for enum fields ──────────────────────────────────


def test_highest_confidence_wins_for_enum_fields(s3_bucket, lambda_context):
    """If two pages give different values for the same field, pick the one
    with the higher confidence."""
    pages = [
        {
            "page_number": 1,
            "seal_type": "unclear",
            "seal_type_confidence": "low",
            "seal_type_source": {"page_number": 1, "text_spans": ["blurry"]},
        },
        {
            "page_number": 2,
            "seal_type": "embossed",
            "seal_type_confidence": "high",
            "seal_type_source": {"page_number": 2, "text_spans": ["crisp seal"]},
        },
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-C1", pages)

    handler(_make_event("APP-C1", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-C1/aggregation.json")
    assert agg["seal_type"] == "embossed"
    assert agg["seal_type_confidence"] == "high"
    # Source must come from the winning page, not the losing one.
    assert agg["seal_type_source"]["page_number"] == 2
    assert agg["seal_type_source"]["text_spans"] == ["crisp seal"]


def test_medium_beats_low_for_enum_fields(s3_bucket, lambda_context):
    pages = [
        {"page_number": 1, "course_relevance": "unclear",
         "course_relevance_confidence": "low"},
        {"page_number": 2, "course_relevance": "nursing_standard",
         "course_relevance_confidence": "medium"},
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-C2", pages)

    handler(_make_event("APP-C2", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-C2/aggregation.json")
    assert agg["course_relevance"] == "nursing_standard"
    assert agg["course_relevance_confidence"] == "medium"


def test_confidence_tie_earlier_page_wins(s3_bucket, lambda_context):
    """When two pages have equal confidence, the earlier page wins."""
    pages = [
        {"page_number": 1, "language_of_issue": "english",
         "language_of_issue_confidence": "high"},
        {"page_number": 2, "language_of_issue": "spanish",
         "language_of_issue_confidence": "high"},
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-C3", pages)

    handler(_make_event("APP-C3", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-C3/aggregation.json")
    assert agg["language_of_issue"] == "english"


# ── Array field merging ──────────────────────────────────────────────────────


def test_required_nursing_domains_merged_across_pages(s3_bucket, lambda_context):
    pages = [
        {
            "page_number": 1,
            "required_nursing_domains_present": ["adult_med_surg", "obstetrics"],
            "required_nursing_domains_present_confidence": "high",
        },
        {
            "page_number": 2,
            "required_nursing_domains_present": ["pediatrics", "psychiatric"],
            "required_nursing_domains_present_confidence": "medium",
        },
        {
            "page_number": 3,
            "required_nursing_domains_present": ["obstetrics", "community_health"],
            "required_nursing_domains_present_confidence": "high",
        },
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-A1", pages)

    handler(_make_event("APP-A1", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-A1/aggregation.json")
    merged = agg["required_nursing_domains_present"]
    # Dedup: "obstetrics" must appear only once.
    assert sorted(merged) == sorted([
        "adult_med_surg", "obstetrics", "pediatrics",
        "psychiatric", "community_health",
    ])


def test_suspicious_course_names_merged(s3_bucket, lambda_context):
    pages = [
        {
            "page_number": 1,
            "suspicious_course_names": ["Bandaging"],
        },
        {
            "page_number": 2,
            "suspicious_course_names": ["Theater techniques", "Bandaging"],
        },
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-A2", pages)

    handler(_make_event("APP-A2", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-A2/aggregation.json")
    assert sorted(agg["suspicious_course_names"]) == sorted(
        ["Bandaging", "Theater techniques"]
    )


def test_diploma_mill_phrases_merged(s3_bucket, lambda_context):
    pages = [
        {"page_number": 1,
         "diploma_mill_phrases_found": ["No Need To Study"]},
        {"page_number": 2,
         "diploma_mill_phrases_found": ["life experience degree"]},
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-A3", pages)

    handler(_make_event("APP-A3", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-A3/aggregation.json")
    assert sorted(agg["diploma_mill_phrases_found"]) == sorted(
        ["No Need To Study", "life experience degree"]
    )


def test_security_features_merged_and_deduped(s3_bucket, lambda_context):
    pages = [
        {"page_number": 1,
         "security_features_present": ["watermark", "hologram"]},
        {"page_number": 2,
         "security_features_present": ["hologram", "serial_number"]},
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-A4", pages)

    handler(_make_event("APP-A4", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-A4/aggregation.json")
    # Order-insensitive comparison because union preserves first-seen order.
    assert sorted(agg["security_features_present"]) == sorted(
        ["watermark", "hologram", "serial_number"]
    )


def test_empty_arrays_produce_empty_aggregated_array(s3_bucket, lambda_context):
    pages = [
        {"page_number": 1, "suspicious_course_names": []},
        {"page_number": 2, "suspicious_course_names": []},
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-A5", pages)

    handler(_make_event("APP-A5", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-A5/aggregation.json")
    assert agg["suspicious_course_names"] == []


# ── applicationId ─────────────────────────────────────────────────────────────


def test_application_id_included_in_aggregation(s3_bucket, lambda_context):
    pages = [{"page_number": 1, "seal_type": "embossed",
              "seal_type_confidence": "high"}]
    extraction_key = _put_extraction(s3_bucket, "APP-ID-1", pages)

    handler(_make_event("APP-ID-1", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-ID-1/aggregation.json")
    assert agg["applicationId"] == "APP-ID-1"


# ── Missing extraction JSON ──────────────────────────────────────────────────


def test_missing_extraction_raises(s3_bucket, lambda_context):
    """If extraction_transcript.json does not exist, the handler must raise so
    Step Functions can retry or fail."""
    event = _make_event("APP-MISSING", "processed/APP-MISSING/extraction_transcript.json")

    with pytest.raises(Exception):
        handler(event, lambda_context)


# ── Tampering boolean: any-true aggregation ───────────────────────────────────


def test_tampering_bool_any_true_propagates(s3_bucket, lambda_context):
    """If page 1 says overlapping_text_detected=False (high) and page 2 says
    True (medium), the aggregated value must be True — not suppressed by the
    higher-confidence False."""
    pages = [
        {
            "page_number": 1,
            "overlapping_text_detected": False,
            "overlapping_text_detected_confidence": "high",
        },
        {
            "page_number": 2,
            "overlapping_text_detected": True,
            "overlapping_text_detected_confidence": "medium",
        },
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-TB1", pages)

    handler(_make_event("APP-TB1", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-TB1/aggregation.json")
    assert agg["overlapping_text_detected"] is True


def test_identity_redaction_boolean_any_true_propagates(s3_bucket, lambda_context):
    pages = [
        {"page_number": 1, "identity_redaction_detected": False},
        {
            "page_number": 2,
            "identity_redaction_detected": True,
            "identity_redaction_detected_confidence": "high",
            "identity_redaction_detected_source": {
                "page_number": 2,
                "text_spans": ["Black redaction mark"],
            },
        },
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-IDENTITY-REDACTION", pages)

    handler(_make_event("APP-IDENTITY-REDACTION", extraction_key), lambda_context)

    agg = _read_aggregation(
        s3_bucket, "processed/APP-IDENTITY-REDACTION/aggregation.json"
    )
    assert agg["identity_redaction_detected"] is True
    assert agg["identity_redaction_detected_source"]["page_number"] == 2


def test_tampering_bool_all_false_stays_false(s3_bucket, lambda_context):
    """When no page reports True for a tampering boolean, result is False."""
    pages = [
        {
            "page_number": 1,
            "mixed_fonts_detected": False,
            "mixed_fonts_detected_confidence": "high",
        },
        {
            "page_number": 2,
            "mixed_fonts_detected": False,
            "mixed_fonts_detected_confidence": "medium",
        },
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-TB2", pages)

    handler(_make_event("APP-TB2", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-TB2/aggregation.json")
    assert agg["mixed_fonts_detected"] is False


def test_tampering_bool_source_from_true_page(s3_bucket, lambda_context):
    """When True propagates, the source metadata comes from the True page."""
    pages = [
        {
            "page_number": 1,
            "compressed_numbers_detected": False,
            "compressed_numbers_detected_confidence": "high",
            "compressed_numbers_detected_source": {
                "page_number": 1, "text_spans": ["GPA 3.0"],
            },
        },
        {
            "page_number": 2,
            "compressed_numbers_detected": True,
            "compressed_numbers_detected_confidence": "medium",
            "compressed_numbers_detected_source": {
                "page_number": 2, "text_spans": ["credit hours column"],
            },
        },
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-TB3", pages)

    handler(_make_event("APP-TB3", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-TB3/aggregation.json")
    assert agg["compressed_numbers_detected"] is True
    assert agg["compressed_numbers_detected_source"]["page_number"] == 2


def test_all_tampering_fields_use_any_true(s3_bucket, lambda_context):
    """Verify all six tampering boolean fields propagate True correctly."""
    tampering_fields = [
        "overlapping_text_detected",
        "compressed_numbers_detected",
        "mixed_fonts_detected",
        "correction_artifacts_present",
        "obliteration_marks_detected",
        "mixed_ink_colors_in_field",
    ]
    for field in tampering_fields:
        pages = [
            {"page_number": 1, field: False, f"{field}_confidence": "high"},
            {"page_number": 2, field: True, f"{field}_confidence": "low"},
        ]
        extraction_key = _put_extraction(s3_bucket, f"APP-TAF-{field[:6]}", pages)
        handler(_make_event(f"APP-TAF-{field[:6]}", extraction_key), lambda_context)
        agg = _read_aggregation(
            s3_bucket, f"processed/APP-TAF-{field[:6]}/aggregation.json"
        )
        assert agg[field] is True, (
            f"{field}: expected True when any page reports True, got {agg[field]}"
        )


# ── document_page_count from extraction metadata ─────────────────────────────


def test_document_page_count_from_extraction_metadata(s3_bucket, lambda_context):
    """document_page_count in aggregation must equal page_count from extraction
    metadata, not any value the model returned per page."""
    pages = [
        {"page_number": 1, "seal_type": "embossed"},
        {"page_number": 2, "seal_type": "absent"},
        {"page_number": 3, "seal_type": "absent"},
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-PC1", pages)

    handler(_make_event("APP-PC1", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-PC1/aggregation.json")
    assert agg["document_page_count"] == 3


def test_document_page_count_overrides_stale_model_value(s3_bucket, lambda_context):
    """Even if a page record contains a model-extracted document_page_count,
    the aggregation must use the authoritative metadata value."""
    pages = [
        {
            "page_number": 1,
            "document_page_count": 99,        # stale model output
            "document_page_count_confidence": "high",
        },
        {"page_number": 2, "seal_type": "laser"},
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-PC2", pages)

    handler(_make_event("APP-PC2", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-PC2/aggregation.json")
    # extraction metadata has page_count=2 (len(pages)); model's 99 is ignored.
    assert agg["document_page_count"] == 2


# ── seal_present_on_pages derived deterministically ──────────────────────────


def test_seal_present_on_pages_derived_from_seal_type(s3_bucket, lambda_context):
    """seal_present_on_pages must list only pages where seal_type is a positive
    value (embossed / stamped_ink / printed_flat / sticker_foil)."""
    pages = [
        {"page_number": 1, "seal_type": "embossed"},
        {"page_number": 2, "seal_type": "absent"},
        {"page_number": 3, "seal_type": "stamped_ink"},
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-SP1", pages)

    handler(_make_event("APP-SP1", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-SP1/aggregation.json")
    assert agg["seal_present_on_pages"] == [1, 3]


def test_seal_present_on_pages_empty_when_no_seal(s3_bucket, lambda_context):
    """When no page has a positive seal_type, seal_present_on_pages is []."""
    pages = [
        {"page_number": 1, "seal_type": "absent"},
        {"page_number": 2, "seal_type": "unclear"},
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-SP2", pages)

    handler(_make_event("APP-SP2", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-SP2/aggregation.json")
    assert agg["seal_present_on_pages"] == []


def test_seal_present_on_pages_ignores_stale_model_array(s3_bucket, lambda_context):
    """If per-page data contains a stale seal_present_on_pages from the model,
    the aggregation must ignore it and derive the value from seal_type."""
    pages = [
        {
            "page_number": 1,
            "seal_type": "absent",
            "seal_present_on_pages": [1, 2, 3],  # stale model output
        },
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-SP3", pages)

    handler(_make_event("APP-SP3", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-SP3/aggregation.json")
    # seal_type is absent → derived result is [], not the stale [1, 2, 3].
    assert agg["seal_present_on_pages"] == []


# ── print_technology_per_page derived deterministically ──────────────────────


def test_print_technology_per_page_derived_from_pages(s3_bucket, lambda_context):
    """print_technology_per_page must be built from each page's print_technology
    in page order, not taken from a model-supplied array."""
    pages = [
        {"page_number": 1, "print_technology": "laser"},
        {"page_number": 2, "print_technology": "inkjet"},
        {"page_number": 3, "print_technology": "laser"},
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-PT1", pages)

    handler(_make_event("APP-PT1", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-PT1/aggregation.json")
    assert agg["print_technology_per_page"] == ["laser", "inkjet", "laser"]


def test_print_technology_per_page_unclear_fallback(s3_bucket, lambda_context):
    """If a page has no print_technology, its slot uses 'unclear'."""
    pages = [
        {"page_number": 1, "print_technology": "laser"},
        {"page_number": 2},   # no print_technology key
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-PT2", pages)

    handler(_make_event("APP-PT2", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-PT2/aggregation.json")
    assert agg["print_technology_per_page"] == ["laser", "unclear"]


def test_print_technology_per_page_ignores_stale_model_array(s3_bucket, lambda_context):
    """If per-page data has a stale print_technology_per_page array from the
    model, the aggregation must derive the value from per-page print_technology."""
    pages = [
        {
            "page_number": 1,
            "print_technology": "laser",
            "print_technology_per_page": ["typewriter", "photocopy"],  # stale
        },
    ]
    extraction_key = _put_extraction(s3_bucket, "APP-PT3", pages)

    handler(_make_event("APP-PT3", extraction_key), lambda_context)

    agg = _read_aggregation(s3_bucket, "processed/APP-PT3/aggregation.json")
    assert agg["print_technology_per_page"] == ["laser"]

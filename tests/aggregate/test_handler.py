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

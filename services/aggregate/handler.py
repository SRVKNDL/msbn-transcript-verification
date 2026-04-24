"""Flatten per-page extraction into the rule engine input document."""

import json
import logging
import os

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_s3 = boto3.client("s3")

_BUCKET_NAME = os.environ.get("BUCKET_NAME", "")

# Highest confidence wins when the same scalar field appears on multiple pages.
# Missing or unknown confidence ranks below "low".
_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}

# These fields collect evidence across pages instead of picking one winner.
_ARRAY_FIELDS = frozenset({
    "security_features_present",
    "suspicious_course_names",
    "diploma_mill_phrases_found",
    "required_nursing_domains_present",
})

# Per-page bookkeeping, not extraction fields.
_PAGE_META_KEYS = frozenset({"page_number", "image_dimensions"})


def handler(event, context):
    """Read extraction JSON and write the flattened aggregation document."""

    application_id = event["applicationId"]
    extraction_key = event["extraction_s3_key"]
    bucket = event.get("bucket") or _BUCKET_NAME

    logger.info(json.dumps({
        "event": "aggregate_start",
        "applicationId": application_id,
        "extraction_s3_key": extraction_key,
    }))

    # Load the per-page extraction written by ExtractLambda.
    obj = _s3.get_object(Bucket=bucket, Key=extraction_key)
    extraction = json.loads(obj["Body"].read().decode("utf-8"))

    pages = extraction.get("pages", [])

    # Collapse page-level values into one document-level record.
    aggregation = _flatten_pages(pages)
    aggregation["applicationId"] = application_id

    # Store the RuleEngineLambda input under the application prefix.
    aggregation_key = f"processed/{application_id}/aggregation.json"
    _s3.put_object(
        Bucket=bucket,
        Key=aggregation_key,
        Body=json.dumps(aggregation, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    logger.info(json.dumps({
        "event": "aggregate_complete",
        "applicationId": application_id,
        "aggregation_s3_key": aggregation_key,
        "page_count": len(pages),
    }))

    return {
        "applicationId": application_id,
        "aggregation_s3_key": aggregation_key,
    }


def _flatten_pages(pages: list[dict]) -> dict:
    """Collapse per-page records into one flat document-level dict."""
    # Sibling keys travel with their base field; they are not merged directly.
    field_names: set[str] = set()
    for page in pages:
        for key in page.keys():
            if key in _PAGE_META_KEYS:
                continue
            if key.endswith("_confidence") or key.endswith("_source"):
                continue
            field_names.add(key)

    out: dict = {}
    for field in sorted(field_names):
        if field in _ARRAY_FIELDS:
            _merge_array_field(field, pages, out)
        else:
            _pick_highest_confidence(field, pages, out)

    return out


def _pick_highest_confidence(field: str, pages: list[dict], out: dict) -> None:
    """Copy the highest-confidence page value and its metadata into ``out``."""
    best_page = None
    best_rank = -1
    for page in pages:
        if field not in page:
            continue
        confidence = page.get(f"{field}_confidence")
        rank = _CONFIDENCE_RANK.get(confidence, 0)
        if rank > best_rank:
            best_rank = rank
            best_page = page

    if best_page is None:
        return

    out[field] = best_page[field]
    confidence = best_page.get(f"{field}_confidence")
    if confidence is not None:
        out[f"{field}_confidence"] = confidence
    source = best_page.get(f"{field}_source")
    if source is not None:
        out[f"{field}_source"] = source


def _merge_array_field(field: str, pages: list[dict], out: dict) -> None:
    """Merge an array field across pages while preserving first-seen order."""
    merged: list = []
    seen: set = set()
    merged_spans: list[str] = []
    first_source_page: int | None = None
    best_confidence_rank = -1
    best_confidence: str | None = None

    for page in pages:
        value = page.get(field)
        if not isinstance(value, list) or not value:
            continue

        for item in value:
            # Vocabulary array fields are strings, so the item is the dedup key.
            if item in seen:
                continue
            seen.add(item)
            merged.append(item)

        confidence = page.get(f"{field}_confidence")
        rank = _CONFIDENCE_RANK.get(confidence, 0)
        if rank > best_confidence_rank:
            best_confidence_rank = rank
            best_confidence = confidence

        source = page.get(f"{field}_source")
        if isinstance(source, dict):
            spans = source.get("text_spans") or []
            if spans:
                merged_spans.extend(spans)
            if first_source_page is None:
                first_source_page = source.get("page_number")

    out[field] = merged
    if best_confidence is not None:
        out[f"{field}_confidence"] = best_confidence
    if first_source_page is not None or merged_spans:
        out[f"{field}_source"] = {
            "page_number": first_source_page,
            "text_spans": merged_spans,
        }

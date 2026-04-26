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
    "suspected_alteration_fields",
})

# Object-array fields that are merged across pages by appending (not deduplicating).
_OBJECT_ARRAY_FIELDS = frozenset({
    "courses",
    "semesters",
    "programs",
    "leave_of_absence_markers",
})

# Tampering boolean fields: aggregated with "any true" so that a single page
# reporting True cannot be suppressed by False values on other pages.
_TAMPERING_BOOL_FIELDS = frozenset({
    "overlapping_text_detected",
    "compressed_numbers_detected",
    "mixed_fonts_detected",
    "correction_artifacts_present",
    "obliteration_marks_detected",
    "mixed_ink_colors_in_field",
})

# Fields derived deterministically after the main flatten loop.
# Skipped in the normal per-page merge to prevent stale model output from
# overriding the computed values.
#   seal_present_on_pages      — derived from per-page seal_type
#   print_technology_per_page  — derived from per-page print_technology
#   document_page_count        — injected from extraction metadata in handler()
_SKIP_IN_FLATTEN_FIELDS = frozenset({
    "seal_present_on_pages",
    "print_technology_per_page",
    "document_page_count",
})

# Per-page bookkeeping, not extraction fields.
_PAGE_META_KEYS = frozenset({"page_number", "image_dimensions"})

# seal_type values that indicate the seal is actually present on a page.
_SEAL_PRESENT_VALUES = frozenset({
    "embossed", "stamped_ink", "printed_flat", "sticker_foil",
})


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

    # document_page_count comes from extraction metadata, not per-page model
    # output. The extractor already knows the true count from len(images).
    page_count = extraction.get("page_count")
    if page_count is not None:
        aggregation["document_page_count"] = page_count

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
        if field in _SKIP_IN_FLATTEN_FIELDS:
            # Derived deterministically below; skip any per-page model value.
            continue
        if field in _TAMPERING_BOOL_FIELDS:
            _merge_any_true_bool(field, pages, out)
        elif field in _ARRAY_FIELDS:
            _merge_array_field(field, pages, out)
        elif field in _OBJECT_ARRAY_FIELDS:
            _merge_object_array_field(field, pages, out)
        else:
            _pick_highest_confidence(field, pages, out)

    # Derive document-level physical fields from per-page observations.
    _derive_seal_present_on_pages(pages, out)
    _derive_print_technology_per_page(pages, out)

    _apply_field_aliases(out)
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


def _merge_any_true_bool(field: str, pages: list[dict], out: dict) -> None:
    """Aggregate a tampering boolean: any page True propagates to document level.

    The source metadata is taken from the first True page; if no page is True,
    falls back to the highest-confidence False page.
    """
    true_page: dict | None = None
    best_false_page: dict | None = None
    best_false_rank = -1

    for page in pages:
        if field not in page:
            continue
        value = page[field]
        confidence = page.get(f"{field}_confidence")
        rank = _CONFIDENCE_RANK.get(confidence, 0)

        if value is True:
            if true_page is None:
                true_page = page  # first True page wins for source metadata
        else:
            if rank > best_false_rank:
                best_false_rank = rank
                best_false_page = page

    winner = true_page if true_page is not None else best_false_page
    if winner is None:
        return

    out[field] = true_page is not None
    confidence = winner.get(f"{field}_confidence")
    if confidence is not None:
        out[f"{field}_confidence"] = confidence
    source = winner.get(f"{field}_source")
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


def _merge_object_array_field(field: str, pages: list[dict], out: dict) -> None:
    """Merge object-array fields (courses, semesters, etc.) across pages."""
    merged: list = []
    for page in pages:
        value = page.get(field)
        if not isinstance(value, list):
            continue
        page_number = page.get("page_number")
        for item in value:
            if isinstance(item, dict):
                # Tag each object with the page it came from for source tracing.
                entry = dict(item)
                if page_number is not None:
                    entry.setdefault("source_location", {
                        "page_number": page_number,
                        "text_spans": [],
                    })
                merged.append(entry)
    out[field] = merged


def _derive_seal_present_on_pages(pages: list[dict], out: dict) -> None:
    """Derive seal_present_on_pages from per-page seal_type observations.

    A seal is considered present when seal_type is one of the positive enum
    values (embossed, stamped_ink, printed_flat, sticker_foil). Pages with
    absent or unclear seal_type do not contribute.
    """
    pages_with_seal: list[int] = []
    for page in sorted(pages, key=lambda p: p.get("page_number") or 0):
        page_num = page.get("page_number")
        if page_num is not None and page.get("seal_type") in _SEAL_PRESENT_VALUES:
            pages_with_seal.append(page_num)
    out["seal_present_on_pages"] = pages_with_seal


def _derive_print_technology_per_page(pages: list[dict], out: dict) -> None:
    """Derive print_technology_per_page from per-page print_technology values.

    Pages are emitted in page_number order. If a page has no print_technology,
    "unclear" is used as the fallback to keep the list length equal to page count.
    """
    sorted_pages = sorted(pages, key=lambda p: p.get("page_number") or 0)
    out["print_technology_per_page"] = [
        (page.get("print_technology") or "unclear") for page in sorted_pages
    ]


def _apply_field_aliases(out: dict) -> None:
    """Map extraction field names to the names downstream rules expect."""
    # courses: normalize course_code → code for PROG_001–004
    courses = out.get("courses")
    if isinstance(courses, list):
        for course in courses:
            if not isinstance(course, dict):
                continue
            # Prefer "code" if Nova provided it; fall back to "course_code".
            if "code" not in course and "course_code" in course:
                course["code"] = course["course_code"]

    # total_credit_hours_stated → total_credit_hours for PROG_003
    if "total_credit_hours" not in out and "total_credit_hours_stated" in out:
        out["total_credit_hours"] = out["total_credit_hours_stated"]

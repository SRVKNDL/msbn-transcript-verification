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
    "academic_extraction_conflicts",
})

_TAMPERING_BOOLEAN_FIELDS = frozenset({
    "identity_redaction_detected",
    "overlapping_text_detected",
    "compressed_numbers_detected",
    "mixed_fonts_detected",
    "correction_artifacts_present",
    "obliteration_marks_detected",
    "mixed_ink_colors_in_field",
})

_POSITIVE_SEAL_TYPES = frozenset({
    "embossed",
    "stamped_ink",
    "printed_flat",
    "sticker_foil",
})

_POSITIVE_SEAL_QUALITIES = frozenset({
    "clear",
    "degraded",
    "pixelated",
})

_REGISTRAR_DETECTED_RANK = {
    "yes": 3,
    "unclear": 2,
    "no": 1,
}

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
    aggregation = _flatten_pages(pages, page_count=extraction.get("page_count"))
    aggregation["applicationId"] = application_id
    if isinstance(extraction.get("textract"), dict):
        aggregation["textract"] = extraction["textract"]
    if extraction.get("textract_s3_key"):
        aggregation["textract_s3_key"] = extraction["textract_s3_key"]

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


def _flatten_pages(pages: list[dict], page_count: int | None = None) -> dict:
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
        elif field in _OBJECT_ARRAY_FIELDS:
            _merge_object_array_field(field, pages, out)
        elif field in _TAMPERING_BOOLEAN_FIELDS:
            _merge_tampering_boolean(field, pages, out)
        elif field == "registrar_block":
            _pick_registrar_block(field, pages, out)
        elif field == "seal_type":
            _pick_preferred_scalar(field, pages, out, _seal_type_rank)
        elif field == "seal_quality":
            _pick_preferred_scalar(field, pages, out, _seal_quality_rank)
        elif field == "seal_visible_text":
            _pick_preferred_scalar(field, pages, out, _seal_visible_text_rank)
        else:
            _pick_highest_confidence(field, pages, out)

    _apply_document_level_derivations(out, pages, page_count)
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


def _pick_preferred_scalar(field: str, pages: list[dict], out: dict, rank_value) -> None:
    """Pick a scalar using field-specific evidence quality before confidence."""
    best_page = None
    best_score: tuple[int, int, int] | None = None
    for index, page in enumerate(pages):
        if field not in page:
            continue
        confidence = page.get(f"{field}_confidence")
        score = (
            rank_value(page.get(field)),
            _CONFIDENCE_RANK.get(confidence, 0),
            -index,
        )
        if best_score is None or score > best_score:
            best_score = score
            best_page = page

    if best_page is None:
        return

    _copy_field_from_page(field, best_page, out)


def _pick_registrar_block(field: str, pages: list[dict], out: dict) -> None:
    """Prefer positive registrar evidence over per-page negative findings."""
    best_page = None
    best_score: tuple[int, int, int, int] | None = None
    for index, page in enumerate(pages):
        block = page.get(field)
        if not isinstance(block, dict):
            continue
        confidence = page.get(f"{field}_confidence")
        score = (
            _REGISTRAR_DETECTED_RANK.get(block.get("detected"), 0),
            _registrar_block_completeness(block),
            _CONFIDENCE_RANK.get(confidence, 0),
            -index,
        )
        if best_score is None or score > best_score:
            best_score = score
            best_page = page

    if best_page is None:
        return

    _copy_field_from_page(field, best_page, out)


def _copy_field_from_page(field: str, page: dict, out: dict) -> None:
    out[field] = page[field]
    confidence = page.get(f"{field}_confidence")
    if confidence is not None:
        out[f"{field}_confidence"] = confidence
    source = page.get(f"{field}_source")
    if source is not None:
        out[f"{field}_source"] = source


def _seal_type_rank(value) -> int:
    if value in _POSITIVE_SEAL_TYPES:
        return 3
    if value == "unclear":
        return 2
    if value == "absent":
        return 1
    return 0


def _seal_quality_rank(value) -> int:
    if value in _POSITIVE_SEAL_QUALITIES:
        return 3
    if value == "unclear":
        return 2
    if value == "absent":
        return 1
    return 0


def _seal_visible_text_rank(value) -> int:
    return 2 if isinstance(value, str) and value.strip() else 1


def _registrar_block_completeness(block: dict) -> int:
    score = 0
    if block.get("signature_present") == "yes":
        score += 4
    if block.get("name_text"):
        score += 3
    if block.get("title_text"):
        score += 2
    if block.get("contact_info_text"):
        score += 1
    if block.get("location") not in (None, "none"):
        score += 1
    return score


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


def _merge_tampering_boolean(field: str, pages: list[dict], out: dict) -> None:
    """Tampering indicators are true if any page reports true."""
    true_page = next((page for page in pages if page.get(field) is True), None)
    if true_page is not None:
        out[field] = True
        confidence = true_page.get(f"{field}_confidence")
        if confidence is not None:
            out[f"{field}_confidence"] = confidence
        source = true_page.get(f"{field}_source")
        if source is not None:
            out[f"{field}_source"] = source
        return

    _pick_highest_confidence(field, pages, out)


def _apply_document_level_derivations(
    out: dict,
    pages: list[dict],
    page_count: int | None,
) -> None:
    """Override model-supplied document fields with deterministic values."""
    authoritative_page_count = page_count if isinstance(page_count, int) else len(pages)
    out["document_page_count"] = authoritative_page_count

    ordered_pages = sorted(
        enumerate(pages, start=1),
        key=lambda item: item[1].get("page_number") or item[0],
    )
    out["seal_present_on_pages"] = [
        page.get("page_number") or fallback_index
        for fallback_index, page in ordered_pages
        if page.get("seal_type") in _POSITIVE_SEAL_TYPES
    ]
    out["print_technology_per_page"] = [
        page.get("print_technology") or "unclear"
        for _fallback_index, page in ordered_pages
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

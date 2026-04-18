"""AggregationLambda: flatten per-page extraction into document-level fields.

Runs between ExtractLambda and ValidateLambda in the Step Functions pipeline.

The ExtractLambda produces a per-page extraction JSON at
``processed/{applicationId}/extraction_transcript.json`` with the shape::

    {
      "schema_version": "1.0",
      "application_id": "...",
      "document_type": "TRANSCRIPT",
      "page_count": N,
      "pages": [
        {
          "page_number": 1,
          "<field>": <value>,
          "<field>_confidence": "high|medium|low",
          "<field>_source":     {"page_number": 1, "text_spans": [...]},
          ...
        },
        ...
      ]
    }

The ValidateLambda expects a flat document-level ``aggregation.json`` where
each field from the extraction vocabulary appears once at the top level, with
its sibling ``_source`` and ``_confidence`` keys. This handler produces that
flat document from the per-page list:

- **Enum / scalar fields**: value from the page with the highest confidence.
  Ties are broken by page_number (earlier page wins). The matching
  ``_source`` and ``_confidence`` come from the same page.
- **Array fields** (``security_features_present``, ``suspicious_course_names``,
  ``diploma_mill_phrases_found``, ``required_nursing_domains_present``):
  union across all pages, deduplicated while preserving first-seen order.
  ``_source`` is merged (all source pages concatenated).

See: design/extraction-vocabulary.md for field definitions.
See: design/architecture-plan.md Section 1.4 for pipeline context.
"""

import json
import logging
import os

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

_s3 = boto3.client("s3")

_BUCKET_NAME = os.environ.get("BUCKET_NAME", "")

# Rank confidence values so we can compare pages deterministically.
# High values win; unknown/missing confidence is treated as below "low".
_CONFIDENCE_RANK = {"high": 3, "medium": 2, "low": 1}

# Array-valued fields — merged (union) across pages, not winner-take-all.
# Matches the vocabulary's array fields in Sections 1-3.
_ARRAY_FIELDS = frozenset({
    "security_features_present",
    "suspicious_course_names",
    "diploma_mill_phrases_found",
    "required_nursing_domains_present",
})

# Keys that are per-page bookkeeping, not extraction fields.
_PAGE_META_KEYS = frozenset({"page_number", "image_dimensions"})


def handler(event, context):
    """Read extraction JSON, flatten per-page to document-level, write aggregation.json.

    Input event (from Step Functions):
        {
            "applicationId":     "<id>",
            "extraction_s3_key": "processed/<id>/extraction_transcript.json"
        }

    Returns:
        {"applicationId": "<id>", "aggregation_s3_key": "processed/<id>/aggregation.json"}
    """
    application_id = event["applicationId"]
    extraction_key = event["extraction_s3_key"]
    bucket = event.get("bucket") or _BUCKET_NAME

    logger.info(json.dumps({
        "event": "aggregate_start",
        "applicationId": application_id,
        "extraction_s3_key": extraction_key,
    }))

    # ── 1. Load extraction JSON ────────────────────────────────────────────────
    obj = _s3.get_object(Bucket=bucket, Key=extraction_key)
    extraction = json.loads(obj["Body"].read().decode("utf-8"))

    pages = extraction.get("pages", [])

    # ── 2. Flatten per-page → document-level ───────────────────────────────────
    aggregation = _flatten_pages(pages)
    aggregation["applicationId"] = application_id

    # ── 3. Write aggregation.json ──────────────────────────────────────────────
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
    """Collapse per-page records into a single flat document-level dict.

    For each field name ``F`` found across any page:
      - If ``F`` is in ``_ARRAY_FIELDS``, the top-level value is the union
        (preserving first-seen order) of the per-page lists.
      - Otherwise, the top-level value is the value from the page with the
        highest confidence; its matching ``F_source`` is copied too.
      - ``F_confidence`` is always the confidence from the winning page
        (or, for arrays, from the first page that contributed any value).
    """
    # Collect the set of all field names present on any page. Exclude
    # ``*_confidence`` and ``*_source`` sibling keys — they travel with the
    # base field. Exclude per-page meta (page_number, image_dimensions).
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
    """Write ``field``, ``field_confidence``, ``field_source`` to ``out`` using
    the value from the page with the highest confidence.

    Tie-breaker: earlier page (lower page_number) wins. Pages that do not
    contain the field are skipped entirely.
    """
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
    """Union of per-page lists for an array-valued field, deduplicated.

    The companion ``_source`` is merged by concatenating text_spans across
    every page that reported a non-empty value; page_number is taken from the
    first such page. ``_confidence`` is the highest confidence among
    contributing pages.
    """
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
            # Items are strings in every vocabulary array field; use the item
            # itself as the dedup key.
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

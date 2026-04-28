"""Extract transcript PDFs into the JSON contract consumed by the rules."""

import base64
import datetime
import hashlib
import json
import logging
import os
import re
import tempfile
import time

import boto3
from botocore.exceptions import ClientError
from pdf2image import convert_from_path

from prompt import (
    PROMPT_VERSION,
    VOCABULARY,
    build_extraction_prompt,
    build_textract_structuring_prompt,
)

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Keep clients warm between Lambda invocations.
_s3 = boto3.client("s3")
_bedrock = boto3.client("bedrock-runtime", region_name="us-east-1")
_textract = boto3.client("textract", region_name="us-east-1")
_dynamo = boto3.resource("dynamodb", region_name="us-east-1")

BUCKET_NAME = os.environ.get("BUCKET_NAME", "")
TABLE_NAME = os.environ.get("TABLE_NAME", "")
BEDROCK_MODEL_ID = os.environ.get("BEDROCK_MODEL_ID", "amazon.nova-pro-v1:0")
BEDROCK_MAX_NEW_TOKENS = int(os.environ.get("BEDROCK_MAX_NEW_TOKENS", "5000"))
NOVA_TEXTRACT_INTERPRETER_ENABLED = (
    os.environ.get("NOVA_TEXTRACT_INTERPRETER_ENABLED", "true").lower()
    not in {"0", "false", "no"}
)
TEXTRACT_FEATURE_TYPES = [
    item.strip()
    for item in os.environ.get(
        "TEXTRACT_FEATURE_TYPES",
        "TABLES,FORMS,QUERIES,SIGNATURES,LAYOUT",
    ).split(",")
    if item.strip()
]
TEXTRACT_JOB_TIMEOUT_SECONDS = int(
    os.environ.get("TEXTRACT_JOB_TIMEOUT_SECONDS", "150")
)
TEXTRACT_JOB_POLL_SECONDS = float(os.environ.get("TEXTRACT_JOB_POLL_SECONDS", "2"))
TEXTRACT_MAX_RESULTS = int(os.environ.get("TEXTRACT_MAX_RESULTS", "1000"))
NOVA_TEXTRACT_RAW_TEXT_CHARS = int(
    os.environ.get("NOVA_TEXTRACT_RAW_TEXT_CHARS", "12000")
)
NOVA_TEXTRACT_MAX_TABLES = int(os.environ.get("NOVA_TEXTRACT_MAX_TABLES", "8"))
NOVA_TEXTRACT_MAX_TABLE_ROWS = int(os.environ.get("NOVA_TEXTRACT_MAX_TABLE_ROWS", "80"))
NOVA_TEXTRACT_MAX_FORMS = int(os.environ.get("NOVA_TEXTRACT_MAX_FORMS", "80"))
NOVA_TEXTRACT_MAX_LAYOUTS = int(os.environ.get("NOVA_TEXTRACT_MAX_LAYOUTS", "120"))
NOVA_TEXTRACT_MAX_LINES = int(os.environ.get("NOVA_TEXTRACT_MAX_LINES", "250"))
_GENERIC_FIELD_RECORD_KEYS = {"value", "confidence", "source_location"}
_NOVA_VISUAL_FIELDS = frozenset({
    "applicant_name_visible",
    "seal_type",
    "seal_quality",
    "seal_visible_text",
    "security_features_present",
    "security_features_assessable",
    "registrar_block",
    "print_technology",
    "print_technology_per_page",
    "paper_size_format",
    "text_alignment",
    "compressed_numbers_detected",
    "mixed_fonts_detected",
    "correction_artifacts_present",
    "obliteration_marks_detected",
    "mixed_ink_colors_in_field",
    "printer_quality_consistency",
    "document_provenance_appearance",
    "suspected_alteration_fields",
    "identity_redaction_detected",
    "overlapping_text_detected",
})
_NOVA_ACADEMIC_FIELDS = frozenset({
    "courses",
    "semesters",
    "final_cum_gpa_stated",
    "total_credit_hours_stated",
    "total_credit_hours",
    "total_quality_points_stated",
    "program_type",
    "claimed_degree_type",
    "grading_scale_format",
    "grading_scale_maximum",
    "degree_conferral_statement_present",
})
_NOVA_ACADEMIC_ARRAY_FIELDS = frozenset({"courses", "semesters"})
_NOVA_ACADEMIC_NUMERIC_FIELDS = frozenset({
    "final_cum_gpa_stated",
    "total_credit_hours_stated",
    "total_credit_hours",
    "total_quality_points_stated",
    "grading_scale_maximum",
})

_COURSE_CODE_RE = re.compile(r"\b([A-Z]{2,5})\s*-?\s*(\d{3,4}[A-Z]?)\b")
_GRADE_RE = re.compile(r"\b(A[+-]?|B[+-]?|C[+-]?|D[+-]?|F|P|PASS|S|U|W|WF|I|TR)\b", re.I)
_TERM_RE = re.compile(
    r"\b((?:fall|spring|summer|winter)\s+\d{4}|"
    r"\d{4}\s+(?:fall|spring|summer|winter)|"
    r"(?:semester|term)\s*[#:]?\s*\d+)\b",
    re.I,
)
_PNV_CODE_RE = re.compile(r"\bPNV\s*-?\s*\d{3,4}[A-Z]?\b", re.I)

_LETTER_GRADE_POINTS = {
    "A+": 4.0,
    "A": 4.0,
    "A-": 3.7,
    "B+": 3.3,
    "B": 3.0,
    "B-": 2.7,
    "C+": 2.3,
    "C": 2.0,
    "C-": 1.7,
    "D+": 1.3,
    "D": 1.0,
    "D-": 0.7,
    "F": 0.0,
}

_TEXTRACT_QUERIES = [
    ("applicant_name", "What is the student or applicant name?"),
    ("institution", "What institution issued this transcript?"),
    ("country", "What country is printed for the institution or study location?"),
    ("license_number", "What student, license, registration, or candidate number is printed?"),
    ("program_year", "What graduation, completion, or program year is printed?"),
    ("date_of_birth", "What is the student's date of birth?"),
    ("document_issue_date", "What date was this transcript issued or certified?"),
    ("degree_conferred_date", "What date was the degree, diploma, or certificate conferred?"),
    ("claimed_degree_type", "What nursing degree, diploma, certificate, or credential is claimed?"),
    ("final_cum_gpa_stated", "What final cumulative GPA is stated?"),
    ("total_credit_hours", "What total credit hours are stated?"),
    ("registrar_name", "What registrar name is printed?"),
    ("registrar_title", "What registrar title is printed?"),
    ("registrar_contact", "What registrar or institution contact information is printed?"),
    ("seal_visible_text", "What readable text appears in the seal or watermark?"),
]

_ARRAY_FIELDS = {
    "security_features_present",
    "suspicious_course_names",
    "diploma_mill_phrases_found",
    "required_nursing_domains_present",
    "suspected_alteration_fields",
}


def _textract_queries_config() -> dict:
    """Return transcript-specific Textract Queries configuration."""
    return {
        "Queries": [
            {"Alias": alias, "Text": text}
            for alias, text in _TEXTRACT_QUERIES
        ]
    }


def _analyze_transcript_with_textract(
    bucket: str,
    s3_key: str,
    application_id: str,
) -> dict:
    """Run Textract analysis over the source transcript PDF and normalize blocks."""
    token_seed = f"{bucket}/{s3_key}".encode("utf-8")
    client_request_token = hashlib.sha256(token_seed).hexdigest()[:32]

    logger.info(json.dumps({
        "event": "textract_start",
        "applicationId": application_id,
        "s3_key": s3_key,
        "feature_types": TEXTRACT_FEATURE_TYPES,
    }))

    start_response = _textract.start_document_analysis(
        DocumentLocation={"S3Object": {"Bucket": bucket, "Name": s3_key}},
        FeatureTypes=TEXTRACT_FEATURE_TYPES,
        QueriesConfig=_textract_queries_config(),
        ClientRequestToken=client_request_token,
        JobTag="msbn-transcript",
    )
    job_id = start_response["JobId"]

    deadline = time.monotonic() + TEXTRACT_JOB_TIMEOUT_SECONDS
    first_terminal_response = None
    while True:
        response = _textract.get_document_analysis(
            JobId=job_id,
            MaxResults=TEXTRACT_MAX_RESULTS,
        )
        status = response.get("JobStatus")
        if status in ("SUCCEEDED", "PARTIAL_SUCCESS", "FAILED"):
            first_terminal_response = response
            break
        if time.monotonic() >= deadline:
            raise TimeoutError(
                f"Textract job {job_id} did not complete within "
                f"{TEXTRACT_JOB_TIMEOUT_SECONDS} seconds"
            )
        time.sleep(TEXTRACT_JOB_POLL_SECONDS)

    if first_terminal_response is None:
        raise RuntimeError(f"Textract job {job_id} did not return a terminal response")

    if first_terminal_response.get("JobStatus") == "FAILED":
        raise RuntimeError(
            "Textract analysis failed: "
            f"{first_terminal_response.get('StatusMessage', 'unknown error')}"
        )

    blocks = list(first_terminal_response.get("Blocks") or [])
    next_token = first_terminal_response.get("NextToken")
    while next_token:
        page_response = _textract.get_document_analysis(
            JobId=job_id,
            MaxResults=TEXTRACT_MAX_RESULTS,
            NextToken=next_token,
        )
        blocks.extend(page_response.get("Blocks") or [])
        next_token = page_response.get("NextToken")

    normalized = _normalize_textract_result(
        first_terminal_response,
        blocks,
        job_id=job_id,
        source_s3_key=s3_key,
    )

    logger.info(json.dumps({
        "event": "textract_complete",
        "applicationId": application_id,
        "job_id": job_id,
        "job_status": first_terminal_response.get("JobStatus"),
        "block_count": len(blocks),
        "page_count": normalized.get("document_metadata", {}).get("Pages"),
    }))
    return normalized


def _normalize_textract_result(
    response: dict,
    blocks: list[dict],
    *,
    job_id: str,
    source_s3_key: str,
) -> dict:
    """Convert Textract Blocks into compact evidence grouped by page."""
    block_map = {
        block["Id"]: block
        for block in blocks
        if block.get("Id")
    }
    page_count = _textract_page_count(response, blocks)
    pages = [_empty_textract_page(page_number) for page_number in range(1, page_count + 1)]

    for block in blocks:
        page_number = int(block.get("Page") or 1)
        if page_number < 1:
            page_number = 1
        while page_number > len(pages):
            pages.append(_empty_textract_page(len(pages) + 1))
        page = pages[page_number - 1]
        block_type = block.get("BlockType")

        if block_type == "LINE":
            line = _block_evidence(block)
            line["text"] = block.get("Text", "")
            page["lines"].append(line)
        elif block_type == "WORD":
            word = _block_evidence(block)
            word["text"] = block.get("Text", "")
            word["text_type"] = block.get("TextType")
            page["words"].append(word)
        elif block_type == "TABLE":
            page["tables"].append(_table_from_block(block, block_map))
        elif block_type == "KEY_VALUE_SET" and "KEY" in block.get("EntityTypes", []):
            page["forms"].append(_form_pair_from_key(block, block_map))
        elif block_type == "QUERY":
            page["queries"].append(_query_from_block(block, block_map))
        elif block_type == "SIGNATURE":
            signature = _block_evidence(block)
            signature["id"] = block.get("Id")
            page["signatures"].append(signature)
        elif isinstance(block_type, str) and block_type.startswith("LAYOUT_"):
            page["layouts"].append(_layout_from_block(block, block_map))

    for page in pages:
        page["raw_text"] = "\n".join(
            line["text"] for line in page["lines"] if line.get("text")
        )
        _verify_queries_against_page_evidence(page)

    return {
        "job_id": job_id,
        "source_s3_key": source_s3_key,
        "feature_types": TEXTRACT_FEATURE_TYPES,
        "analyze_document_model_version": response.get("AnalyzeDocumentModelVersion"),
        "document_metadata": response.get("DocumentMetadata") or {"Pages": page_count},
        "job_status": response.get("JobStatus"),
        "warnings": response.get("Warnings") or [],
        "pages": pages,
    }


def _textract_page_count(response: dict, blocks: list[dict]) -> int:
    metadata_pages = (response.get("DocumentMetadata") or {}).get("Pages")
    if isinstance(metadata_pages, int) and metadata_pages > 0:
        return metadata_pages
    block_pages = [
        int(block["Page"])
        for block in blocks
        if isinstance(block.get("Page"), int)
    ]
    return max(block_pages, default=1)


def _empty_textract_page(page_number: int) -> dict:
    return {
        "page_number": page_number,
        "raw_text": "",
        "lines": [],
        "words": [],
        "tables": [],
        "forms": [],
        "layouts": [],
        "queries": [],
        "signatures": [],
    }


def _relationships(block: dict, relationship_type: str) -> list[str]:
    ids: list[str] = []
    for rel in block.get("Relationships") or []:
        if rel.get("Type") == relationship_type:
            ids.extend(rel.get("Ids") or [])
    return ids


def _text_for_block(block: dict, block_map: dict[str, dict]) -> str:
    if block.get("Text"):
        return block["Text"]

    parts: list[str] = []
    for child_id in _relationships(block, "CHILD"):
        child = block_map.get(child_id)
        if not child:
            continue
        child_type = child.get("BlockType")
        if child_type in ("WORD", "LINE") and child.get("Text"):
            parts.append(child["Text"])
        elif child_type == "SELECTION_ELEMENT":
            parts.append("[X]" if child.get("SelectionStatus") == "SELECTED" else "[ ]")
    return " ".join(parts).strip()


def _block_evidence(block: dict) -> dict:
    return {
        "confidence": block.get("Confidence"),
        "geometry": block.get("Geometry"),
    }


def _table_from_block(block: dict, block_map: dict[str, dict]) -> dict:
    cells = []
    for child_id in _relationships(block, "CHILD"):
        child = block_map.get(child_id)
        if not child or child.get("BlockType") not in ("CELL", "MERGED_CELL"):
            continue
        cells.append({
            "row_index": child.get("RowIndex"),
            "column_index": child.get("ColumnIndex"),
            "row_span": child.get("RowSpan"),
            "column_span": child.get("ColumnSpan"),
            "entity_types": child.get("EntityTypes") or [],
            "text": _text_for_block(child, block_map),
            "confidence": child.get("Confidence"),
            "geometry": child.get("Geometry"),
        })

    max_row = max((cell.get("row_index") or 0 for cell in cells), default=0)
    max_col = max((cell.get("column_index") or 0 for cell in cells), default=0)
    rows = [["" for _ in range(max_col)] for _ in range(max_row)]
    for cell in cells:
        row_idx = (cell.get("row_index") or 0) - 1
        col_idx = (cell.get("column_index") or 0) - 1
        if row_idx >= 0 and col_idx >= 0:
            rows[row_idx][col_idx] = cell.get("text") or ""

    return {
        "id": block.get("Id"),
        "entity_types": block.get("EntityTypes") or [],
        "confidence": block.get("Confidence"),
        "geometry": block.get("Geometry"),
        "rows": rows,
        "cells": sorted(
            cells,
            key=lambda cell: (
                cell.get("row_index") or 0,
                cell.get("column_index") or 0,
            ),
        ),
        "titles": [
            _text_for_block(block_map[title_id], block_map)
            for title_id in _relationships(block, "TABLE_TITLE")
            if title_id in block_map
        ],
        "footers": [
            _text_for_block(block_map[footer_id], block_map)
            for footer_id in _relationships(block, "TABLE_FOOTER")
            if footer_id in block_map
        ],
    }


def _form_pair_from_key(key_block: dict, block_map: dict[str, dict]) -> dict:
    value_blocks = [
        block_map[value_id]
        for value_id in _relationships(key_block, "VALUE")
        if value_id in block_map
    ]
    values = [_text_for_block(value_block, block_map) for value_block in value_blocks]
    return {
        "key": _text_for_block(key_block, block_map),
        "value": " ".join(value for value in values if value).strip(),
        "key_confidence": key_block.get("Confidence"),
        "value_confidence": max(
            [
                value_block.get("Confidence") or 0
                for value_block in value_blocks
            ],
            default=None,
        ),
        "key_geometry": key_block.get("Geometry"),
        "value_geometry": [
            value_block.get("Geometry")
            for value_block in value_blocks
            if value_block.get("Geometry")
        ],
    }


def _query_from_block(block: dict, block_map: dict[str, dict]) -> dict:
    answer_blocks = [
        block_map[answer_id]
        for answer_id in _relationships(block, "ANSWER")
        if answer_id in block_map
    ]
    query = block.get("Query") or {}
    return {
        "alias": query.get("Alias"),
        "question": query.get("Text"),
        "pages": query.get("Pages") or [],
        "answers": [
            {
                "text": answer.get("Text", ""),
                "confidence": answer.get("Confidence"),
                "geometry": answer.get("Geometry"),
            }
            for answer in answer_blocks
        ],
    }


def _verify_queries_against_page_evidence(page: dict) -> None:
    """Mark query answers that are supported by raw text/tables/forms/layouts."""
    evidence_text = _query_verification_text(page)
    evidence_norm = _normalize_query_text(evidence_text)
    for query in page.get("queries") or []:
        if not isinstance(query, dict):
            continue
        for answer in query.get("answers") or []:
            if not isinstance(answer, dict):
                continue
            answer_text = str(answer.get("text") or "").strip()
            answer_norm = _normalize_query_text(answer_text)
            verified = bool(answer_norm and answer_norm in evidence_norm)
            answer["verified"] = verified
            answer["verification_sources"] = ["raw_text"] if verified else []


def _query_verification_text(page: dict) -> str:
    parts: list[str] = [page.get("raw_text") or ""]
    for line in page.get("lines") or []:
        if isinstance(line, dict):
            parts.append(line.get("text") or "")
    for table in page.get("tables") or []:
        if not isinstance(table, dict):
            continue
        for row in table.get("rows") or []:
            if isinstance(row, list):
                parts.append(" ".join(str(cell) for cell in row))
        parts.extend(str(title) for title in table.get("titles") or [])
        parts.extend(str(footer) for footer in table.get("footers") or [])
    for form in page.get("forms") or []:
        if isinstance(form, dict):
            parts.append(form.get("key") or "")
            parts.append(form.get("value") or "")
    for layout in page.get("layouts") or []:
        if isinstance(layout, dict):
            parts.append(layout.get("text") or "")
    return "\n".join(part for part in parts if part)


def _normalize_query_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _layout_from_block(block: dict, block_map: dict[str, dict]) -> dict:
    layout = _block_evidence(block)
    layout.update({
        "id": block.get("Id"),
        "type": block.get("BlockType"),
        "text": _text_for_block(block, block_map),
    })
    return layout


def _textract_context_for_page(textract_doc: dict, page_number: int) -> dict:
    pages = textract_doc.get("pages") or []
    page = pages[page_number - 1] if page_number - 1 < len(pages) else None
    compact_page = _compact_textract_page_for_nova(
        page or _empty_textract_page(page_number)
    )
    return {
        "feature_types": textract_doc.get("feature_types") or TEXTRACT_FEATURE_TYPES,
        "analyze_document_model_version": textract_doc.get(
            "analyze_document_model_version"
        ),
        "document_metadata": textract_doc.get("document_metadata") or {},
        "page": compact_page,
    }


def _compact_textract_page_for_nova(page: dict, *, minimal: bool = False) -> dict:
    """Keep Textract semantics, but drop token-heavy geometry and word detail."""
    raw_text_limit = 4000 if minimal else NOVA_TEXTRACT_RAW_TEXT_CHARS
    max_tables = 4 if minimal else NOVA_TEXTRACT_MAX_TABLES
    max_rows = 40 if minimal else NOVA_TEXTRACT_MAX_TABLE_ROWS
    max_forms = 30 if minimal else NOVA_TEXTRACT_MAX_FORMS
    max_layouts = 40 if minimal else NOVA_TEXTRACT_MAX_LAYOUTS
    max_lines = 100 if minimal else NOVA_TEXTRACT_MAX_LINES

    return {
        "page_number": page.get("page_number"),
        "raw_text": _truncate_text(page.get("raw_text") or "", raw_text_limit),
        "lines": [
            {
                "text": _truncate_text(line.get("text") or "", 300),
                "confidence": line.get("confidence"),
            }
            for line in (page.get("lines") or [])[:max_lines]
            if isinstance(line, dict) and line.get("text")
        ],
        "tables": [
            {
                "titles": table.get("titles") or [],
                "footers": table.get("footers") or [],
                "entity_types": table.get("entity_types") or [],
                "confidence": table.get("confidence"),
                "rows": [
                    [_truncate_text(str(cell), 200) for cell in row]
                    for row in (table.get("rows") or [])[:max_rows]
                ],
            }
            for table in (page.get("tables") or [])[:max_tables]
            if isinstance(table, dict)
        ],
        "forms": [
            {
                "key": _truncate_text(form.get("key") or "", 200),
                "value": _truncate_text(form.get("value") or "", 500),
                "key_confidence": form.get("key_confidence"),
                "value_confidence": form.get("value_confidence"),
            }
            for form in (page.get("forms") or [])[:max_forms]
            if isinstance(form, dict)
        ],
        "layouts": [
            {
                "type": layout.get("type"),
                "text": _truncate_text(layout.get("text") or "", 700),
                "confidence": layout.get("confidence"),
            }
            for layout in (page.get("layouts") or [])[:max_layouts]
            if isinstance(layout, dict) and layout.get("text")
        ],
        "queries": [
            {
                "alias": query.get("alias"),
                "question": query.get("question"),
                "answers": [
                    {
                        "text": _truncate_text(answer.get("text") or "", 500),
                        "confidence": answer.get("confidence"),
                        "verified": answer.get("verified"),
                    }
                    for answer in (query.get("answers") or [])
                    if isinstance(answer, dict) and answer.get("verified") is not False
                ],
            }
            for query in page.get("queries") or []
            if isinstance(query, dict)
        ],
        "signatures": [
            {
                "confidence": signature.get("confidence"),
            }
            for signature in page.get("signatures") or []
            if isinstance(signature, dict)
        ],
        "omitted_for_prompt_size": {
            "words": len(page.get("words") or []),
            "table_cell_details_preserved_in_s3": True,
            "block_details_preserved_in_s3": True,
        },
    }


def _minimal_textract_context(textract_context: dict | None) -> dict | None:
    if not textract_context:
        return None
    page = (textract_context.get("page") or {}) if isinstance(textract_context, dict) else {}
    return {
        "feature_types": textract_context.get("feature_types") or TEXTRACT_FEATURE_TYPES,
        "document_metadata": textract_context.get("document_metadata") or {},
        "page": _compact_textract_page_for_nova(page, minimal=True),
    }


def _truncate_text(value: str, max_chars: int) -> str:
    text = str(value or "")
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "\n[TRUNCATED]"


def _apply_document_level_extraction_fields(
    pages: list[dict],
    page_count: int,
) -> None:
    """Stamp deterministic document-level fields into page one for aggregation."""
    if not pages:
        return

    first_page = pages[0]
    first_page["document_page_count"] = page_count
    first_page["document_page_count_confidence"] = "high"
    first_page["document_page_count_source"] = {
        "page_number": 1,
        "text_spans": [f"PDF page count: {page_count}"],
    }

    seal_pages = [
        page.get("page_number")
        for page in pages
        if page.get("seal_type") not in (None, "absent", "unclear")
        or bool(page.get("seal_visible_text"))
    ]
    first_page["seal_present_on_pages"] = [
        page_num for page_num in seal_pages if isinstance(page_num, int)
    ]
    first_page["seal_present_on_pages_confidence"] = "medium"

    first_page["print_technology_per_page"] = [
        page.get("print_technology") or "unclear"
        for page in pages
    ]
    first_page["print_technology_per_page_confidence"] = "medium"


def _validate_and_build_page_record(
    nova_response: dict,
    page_number: int,
    width: int,
    height: int,
) -> dict:
    """Flatten Nova visual findings and warn on unsupported fields."""
    record: dict = {
        "page_number": page_number,
        "image_dimensions": {"width": width, "height": height},
    }

    for field, meta in nova_response.items():
        if field not in _NOVA_VISUAL_FIELDS:
            logger.warning(
                json.dumps({
                    "event": "nova_non_visual_field_ignored",
                    "field": field,
                    "page_number": page_number,
                })
            )
            continue

        if not isinstance(meta, dict):
            logger.warning(
                json.dumps({
                    "event": "unexpected_field_shape",
                    "field": field,
                    "value_preview": str(meta)[:200],
                    "page_number": page_number,
                })
            )
            record[field] = meta
            continue

        value = meta.get("value")
        confidence = meta.get("confidence")
        source_location = meta.get("source_location")

        if isinstance(source_location, dict):
            source_location["page_number"] = page_number

        # Treat vocabulary drift as a data-quality warning, not a pipeline failure.
        if field in VOCABULARY:
            allowed = VOCABULARY[field]
            if field in _ARRAY_FIELDS and isinstance(value, list):
                for item in value:
                    if item not in allowed:
                        logger.warning(
                            json.dumps({
                                "event": "unexpected_enum_value",
                                "field": field,
                                "value": item,
                                "allowed": sorted(allowed),
                                "page_number": page_number,
                            })
                        )
            elif not isinstance(value, (list, dict)) and value not in allowed:
                logger.warning(
                    json.dumps({
                        "event": "unexpected_enum_value",
                        "field": field,
                        "value": value,
                        "allowed": sorted(allowed),
                        "page_number": page_number,
                    })
                )

        if confidence is not None and confidence not in VOCABULARY["_confidence"]:
            logger.warning(
                json.dumps({
                    "event": "unexpected_confidence_value",
                    "field": field,
                    "confidence": confidence,
                    "page_number": page_number,
                })
            )

        # Store the field plus its optional confidence/source siblings.
        record[field] = value
        if confidence is not None:
            record[f"{field}_confidence"] = confidence
        if source_location is not None:
            record[f"{field}_source"] = source_location

    # Rule helpers expect the usual <field>_source shape.
    acc_loc = record.get("accreditation_claim_location")
    if isinstance(acc_loc, dict):
        record.setdefault("accreditation_claim_source", acc_loc)

    return record


def _normalize_nova_response_shape(nova_response: dict, page_number: int) -> dict:
    """Accept known wrappers, but keep only visual/physical evidence fields."""
    for wrapper_key in ("fields", "extracted_fields", "extraction", "data"):
        wrapped = nova_response.get(wrapper_key)
        if isinstance(wrapped, dict):
            nova_response = wrapped
            break

    if set(nova_response.keys()).issubset(_GENERIC_FIELD_RECORD_KEYS):
        logger.warning(json.dumps({
            "event": "nova_generic_field_record_ignored",
            "page_number": page_number,
            "keys": sorted(nova_response.keys()),
        }))
        return {}

    visual_response = {
        key: value
        for key, value in nova_response.items()
        if key in _NOVA_VISUAL_FIELDS
    }
    ignored_fields = sorted(set(nova_response.keys()) - set(visual_response.keys()))
    for field in ignored_fields:
        logger.warning(json.dumps({
            "event": "nova_non_visual_field_ignored",
            "field": field,
            "page_number": page_number,
        }))

    if not visual_response:
        logger.warning(json.dumps({
            "event": "nova_unexpected_schema_ignored",
            "page_number": page_number,
            "keys": sorted(nova_response.keys())[:40],
        }))
        return {}

    return visual_response


def _normalize_nova_academic_response_shape(
    nova_response: dict,
    page: dict,
    page_number: int,
) -> dict:
    """Keep only Textract-supported academic fields from Nova's text-only pass."""
    for wrapper_key in ("fields", "extracted_fields", "extraction", "data"):
        wrapped = nova_response.get(wrapper_key)
        if isinstance(wrapped, dict):
            nova_response = wrapped
            break

    evidence_text = "\n".join(_page_text_evidence(page))
    evidence_norm = _normalize_query_text(evidence_text)
    accepted: dict = {}

    for field, meta in nova_response.items():
        if field not in _NOVA_ACADEMIC_FIELDS:
            logger.warning(json.dumps({
                "event": "nova_textract_non_academic_field_ignored",
                "field": field,
                "page_number": page_number,
            }))
            continue
        if not isinstance(meta, dict):
            logger.warning(json.dumps({
                "event": "nova_textract_unexpected_field_shape",
                "field": field,
                "page_number": page_number,
            }))
            continue

        value = meta.get("value")
        if value in (None, "", [], "unclear"):
            continue
        confidence = meta.get("confidence")
        if confidence not in VOCABULARY["_confidence"]:
            confidence = "medium"
        source_location = _validated_source_location(
            meta.get("source_location"),
            evidence_norm,
            page_number,
        )

        if field in _NOVA_ACADEMIC_ARRAY_FIELDS:
            value = _validated_nova_academic_array(
                field,
                value,
                evidence_norm,
                page_number,
            )
            if not value:
                continue
            if source_location is None:
                source_location = _source_from_nested_academic_items(value, page_number)
        elif source_location is None and not _value_supported_by_textract(
            value,
            evidence_norm,
        ):
            logger.warning(json.dumps({
                "event": "nova_textract_unsupported_value_ignored",
                "field": field,
                "page_number": page_number,
                "value_preview": str(value)[:200],
            }))
            continue

        value = _coerce_nova_academic_value(field, value)
        if value in (None, "", [], "unclear"):
            continue

        accepted[field] = {
            "value": value,
            "confidence": confidence,
            "source_location": source_location or {
                "page_number": page_number,
                "text_spans": [str(value)],
            },
        }

    return accepted


def _validated_source_location(
    source_location,
    evidence_norm: str,
    page_number: int,
) -> dict | None:
    if not isinstance(source_location, dict):
        return None
    spans = [
        str(span).strip()
        for span in source_location.get("text_spans") or []
        if str(span or "").strip()
    ]
    supported = [
        span for span in spans
        if _text_span_supported(span, evidence_norm)
    ]
    if not supported:
        return None
    source_page = source_location.get("page_number")
    if not isinstance(source_page, int):
        source_page = page_number
    return {
        "page_number": source_page,
        "text_spans": supported,
    }


def _validated_nova_academic_array(
    field: str,
    value,
    evidence_norm: str,
    page_number: int,
) -> list:
    if not isinstance(value, list):
        return []
    if field == "courses":
        return [
            course for course in (
                _validated_nova_course(item, evidence_norm, page_number)
                for item in value
            )
            if course
        ]
    if field == "semesters":
        return [
            semester for semester in (
                _validated_nova_semester(item, evidence_norm, page_number)
                for item in value
            )
            if semester
        ]
    return []


def _validated_nova_course(item, evidence_norm: str, page_number: int) -> dict | None:
    if not isinstance(item, dict):
        return None
    source_location = _validated_source_location(
        item.get("source_location"),
        evidence_norm,
        page_number,
    )
    row_text = " ".join(source_location["text_spans"]) if source_location else ""
    code = _find_course_code(item.get("code") or item.get("course_code") or row_text)
    name = _clean_text(item.get("name") or item.get("course_title"))
    if not code and not name:
        return None
    if not source_location and not _value_supported_by_textract(code or name, evidence_norm):
        return None

    credit_hours = _coerce_numeric(item.get("credit_hours"), max_value=80.0)
    grade_points = _coerce_numeric(item.get("grade_points"), max_value=500.0)
    semester = _coerce_int(item.get("semester"), min_value=1, max_value=20)
    grade = _extract_grade(item.get("grade"))

    return {
        "name": name or code,
        "code": code,
        "course_code": code,
        "course_title": name,
        "credit_hours": credit_hours,
        "grade": grade,
        "grade_points": grade_points,
        "semester": semester,
        "start_date": _clean_text(item.get("start_date")),
        "end_date": _clean_text(item.get("end_date")),
        "retake_marker": bool(item.get("retake_marker")),
        "transfer_marker": bool(item.get("transfer_marker")),
        "source_location": source_location or {
            "page_number": page_number,
            "text_spans": [code or name],
        },
    }


def _validated_nova_semester(item, evidence_norm: str, page_number: int) -> dict | None:
    if not isinstance(item, dict):
        return None
    source_location = _validated_source_location(
        item.get("source_location"),
        evidence_norm,
        page_number,
    )
    term = _clean_text(item.get("term"))
    if not term:
        return None
    if not source_location and not _value_supported_by_textract(term, evidence_norm):
        return None
    term_type = _clean_text(item.get("term_type"))
    if term_type not in {"fall", "spring", "summer", "winter"}:
        term_type = _term_type(term)
    courses = [
        str(course).strip()
        for course in item.get("courses") or []
        if str(course or "").strip()
    ]
    return {
        "term": term,
        "term_type": term_type,
        "start_date": _clean_text(item.get("start_date")),
        "end_date": _clean_text(item.get("end_date")),
        "courses": courses,
        "term_gpa_stated": _coerce_numeric(item.get("term_gpa_stated"), max_value=5.0),
        "term_credit_hours_stated": _coerce_numeric(
            item.get("term_credit_hours_stated"),
            max_value=120.0,
        ),
        "cum_gpa_stated_after_term": _coerce_numeric(
            item.get("cum_gpa_stated_after_term"),
            max_value=5.0,
        ),
        "cum_credit_hours_stated": _coerce_numeric(
            item.get("cum_credit_hours_stated"),
            max_value=300.0,
        ),
        "cum_quality_points_stated": _coerce_numeric(
            item.get("cum_quality_points_stated"),
            max_value=1500.0,
        ),
        "source_location": source_location or {
            "page_number": page_number,
            "text_spans": [term],
        },
    }


def _source_from_nested_academic_items(items: list[dict], page_number: int) -> dict:
    spans: list[str] = []
    source_page = page_number
    for item in items:
        source = item.get("source_location") if isinstance(item, dict) else None
        if not isinstance(source, dict):
            continue
        if isinstance(source.get("page_number"), int):
            source_page = source["page_number"]
        for span in source.get("text_spans") or []:
            if span not in spans:
                spans.append(span)
    return {"page_number": source_page, "text_spans": spans}


def _coerce_nova_academic_value(field: str, value):
    if field in _NOVA_ACADEMIC_NUMERIC_FIELDS:
        max_value = 5.0 if "gpa" in field else 1500.0
        return _coerce_numeric(value, max_value=max_value)
    if field == "program_type":
        return value if value in VOCABULARY["program_type"] else None
    if field == "claimed_degree_type":
        return value if value in VOCABULARY["claimed_degree_type"] else None
    if field == "grading_scale_format":
        return value if value in VOCABULARY["grading_scale_format"] else None
    if field == "degree_conferral_statement_present":
        return True if value is True else None
    return value


def _text_span_supported(span: str, evidence_norm: str) -> bool:
    span_norm = _normalize_query_text(span)
    if not span_norm:
        return False
    if span_norm in evidence_norm:
        return True
    tokens = [token for token in span_norm.split() if len(token) > 1]
    if len(tokens) < 3:
        return all(token in evidence_norm.split() for token in tokens)
    present = sum(1 for token in tokens if token in evidence_norm.split())
    return present / len(tokens) >= 0.85


def _value_supported_by_textract(value, evidence_norm: str) -> bool:
    if isinstance(value, (int, float, bool)):
        return str(value).lower() in evidence_norm
    if isinstance(value, str):
        return _text_span_supported(value, evidence_norm)
    return False


def _clean_text(value) -> str | None:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text or None


def _coerce_numeric(value, *, max_value: float | None = None) -> float | int | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        number = float(value)
    else:
        parsed = _parse_number(str(value or ""), max_value=max_value)
        return parsed
    if max_value is not None and number > max_value:
        return None
    return int(number) if number.is_integer() else number


def _coerce_int(value, *, min_value: int, max_value: int) -> int | None:
    number = _coerce_numeric(value, max_value=max_value)
    if number is None:
        return None
    integer = int(number)
    if integer < min_value or integer > max_value:
        return None
    return integer


def _apply_nova_textract_academic_fields(
    record: dict,
    nova_academic: dict,
    page_number: int,
) -> None:
    """Fill deterministic gaps from supported Nova interpretation and log conflicts."""
    for field, meta in nova_academic.items():
        value = meta.get("value")
        confidence = meta.get("confidence") or "medium"
        source = meta.get("source_location") or {
            "page_number": page_number,
            "text_spans": [str(value)],
        }

        if field not in record:
            _set_from_textract(
                record,
                field,
                value,
                confidence="medium" if confidence == "high" else confidence,
                page_number=source.get("page_number") or page_number,
                spans=source.get("text_spans") or [str(value)],
            )
            record[f"{field}_source"]["method"] = "nova_textract_interpreter"
            continue

        if _academic_values_equivalent(record.get(field), value, field):
            record.setdefault(f"{field}_agreement", "deterministic_and_nova_textract")
            continue

        conflict = {
            "field": field,
            "deterministic_value": _json_safe_preview(record.get(field)),
            "nova_textract_value": _json_safe_preview(value),
            "source_location": source,
        }
        record.setdefault("academic_extraction_conflicts", []).append(conflict)
        logger.warning(json.dumps({
            "event": "academic_extraction_conflict",
            "page_number": page_number,
            "field": field,
            "deterministic_value": conflict["deterministic_value"],
            "nova_textract_value": conflict["nova_textract_value"],
        }))


def _academic_values_equivalent(left, right, field: str) -> bool:
    if field in _NOVA_ACADEMIC_NUMERIC_FIELDS:
        try:
            return abs(float(left) - float(right)) < 0.001
        except (TypeError, ValueError):
            return False
    if field == "courses":
        return _course_signature_set(left) == _course_signature_set(right)
    if field == "semesters":
        return _semester_signature_set(left) == _semester_signature_set(right)
    return left == right


def _course_signature_set(value) -> set[tuple]:
    if not isinstance(value, list):
        return set()
    signatures = set()
    for course in value:
        if not isinstance(course, dict):
            continue
        signatures.add((
            str(course.get("code") or course.get("course_code") or "").upper(),
            _number_signature(course.get("credit_hours")),
            str(course.get("grade") or "").upper(),
        ))
    return signatures


def _semester_signature_set(value) -> set[tuple]:
    if not isinstance(value, list):
        return set()
    signatures = set()
    for semester in value:
        if not isinstance(semester, dict):
            continue
        signatures.add((
            str(semester.get("term") or "").lower(),
            _number_signature(semester.get("term_gpa_stated")),
            _number_signature(semester.get("cum_gpa_stated_after_term")),
        ))
    return signatures


def _number_signature(value) -> float | None:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def _json_safe_preview(value):
    text = json.dumps(value, default=str, sort_keys=True)
    if len(text) <= 500:
        return json.loads(text)
    return text[:500] + "...[TRUNCATED]"


def _apply_textract_backed_page_fields(
    record: dict,
    textract_doc: dict,
    page_number: int,
    image,
) -> None:
    """Fill high-value fields from verified Textract evidence and image heuristics."""
    pages = textract_doc.get("pages") or []
    page = pages[page_number - 1] if page_number - 1 < len(pages) else {}

    applicant_answer = _verified_query_answer(page, "applicant_name")
    if applicant_answer:
        _set_from_textract(
            record,
            "applicant_name",
            applicant_answer,
            confidence="high",
            page_number=page_number,
        )
        _set_from_textract(
            record,
            "applicant_name_visible",
            "yes",
            confidence="high",
            page_number=page_number,
            spans=[applicant_answer],
        )
    elif page_number == 1 and _looks_like_transcript_identity_area(page):
        _set_from_textract(
            record,
            "applicant_name_visible",
            "no",
            confidence="high",
            page_number=page_number,
            spans=["No readable applicant name found in transcript identity area"],
        )

    institution = _extract_issuing_institution_from_textract(page)
    if institution:
        institution_name, institution_source = institution
        _set_from_textract(
            record,
            "institution",
            institution_name,
            confidence="high",
            page_number=page_number,
            spans=[institution_source],
        )

    for alias, field in (
        ("country", "country"),
        ("license_number", "license_number"),
        ("program_year", "program_year"),
        ("document_issue_date", "document_issue_date"),
        ("degree_conferred_date", "degree_conferred_date"),
        ("seal_visible_text", "seal_visible_text"),
    ):
        answer = _verified_query_answer(page, alias)
        if answer:
            _set_from_textract(
                record,
                field,
                _coerce_query_value(field, answer),
                confidence="high",
                page_number=page_number,
                spans=[answer],
            )

    if "institution" not in record:
        institution_answer = _verified_query_answer(page, "institution")
        if institution_answer and not _is_recipient_institution_answer(page, institution_answer):
            _set_from_textract(
                record,
                "institution",
                institution_answer,
                confidence="medium",
                page_number=page_number,
                spans=[institution_answer],
            )

    _apply_textract_academic_fields(record, page, page_number)
    _apply_registrar_from_textract(record, page, page_number)

    if _detect_identity_redaction_marks(image):
        _set_from_textract(
            record,
            "identity_redaction_detected",
            True,
            confidence="high",
            page_number=page_number,
            spans=["Black redaction mark in applicant/student identity area"],
        )
        _set_from_textract(
            record,
            "applicant_name_visible",
            "no",
            confidence="high",
            page_number=page_number,
            spans=["Applicant/student identity area is visibly redacted"],
        )
        alterations = record.get("suspected_alteration_fields")
        if not isinstance(alterations, list):
            alterations = []
        if "applicant/student identity redaction" not in alterations:
            alterations.append("applicant/student identity redaction")
        record["suspected_alteration_fields"] = alterations
        record.setdefault("suspected_alteration_fields_confidence", "high")
        record.setdefault(
            "suspected_alteration_fields_source",
            {
                "page_number": page_number,
                "text_spans": ["Black redaction mark in applicant/student identity area"],
            },
        )


def _apply_textract_academic_fields(record: dict, page: dict, page_number: int) -> None:
    """Authoritative academic extraction from Textract text/table structure."""
    table_result = _extract_academic_tables(page, page_number)
    courses = table_result["courses"]
    semesters = table_result["semesters"]

    if courses:
        _set_from_textract(
            record,
            "courses",
            courses,
            confidence="high",
            page_number=page_number,
            spans=[course["source_location"]["text_spans"][0] for course in courses[:5]],
        )

    if semesters:
        _set_from_textract(
            record,
            "semesters",
            semesters,
            confidence="high",
            page_number=page_number,
            spans=[
                sem.get("source_location", {}).get("text_spans", [""])[0]
                for sem in semesters[:5]
                if sem.get("source_location")
            ],
        )

    for field, labels, max_value in (
        (
            "final_cum_gpa_stated",
            [
                r"final\s+(?:cum(?:ulative)?\s+)?gpa",
                r"(?:cum(?:ulative)?|overall|career)\s+gpa",
                r"\bcgpa\b",
            ],
            5.0,
        ),
        (
            "total_credit_hours_stated",
            [
                r"total\s+(?:semester\s+)?(?:credit|credits|hours)",
                r"(?:credit|credits|hours)\s+total",
                r"total\s+earned\s+(?:credit|credits|hours)",
            ],
            250.0,
        ),
        (
            "total_quality_points_stated",
            [
                r"total\s+(?:quality|grade)\s+points",
                r"(?:quality|grade)\s+points\s+total",
            ],
            1000.0,
        ),
    ):
        query_alias = "total_credit_hours" if field == "total_credit_hours_stated" else field
        answer = _verified_query_answer(page, query_alias)
        parsed = _parse_number(answer, max_value=max_value) if answer else None
        source_text = answer
        confidence = "high"
        if parsed is None:
            candidate = _find_labeled_number(page, labels, max_value=max_value)
            if candidate:
                parsed, source_text = candidate
                confidence = "high"
        if parsed is not None:
            _set_from_textract(
                record,
                field,
                parsed,
                confidence=confidence,
                page_number=page_number,
                spans=[source_text],
            )

    if "total_credit_hours" not in record:
        if record.get("total_credit_hours_stated") is not None:
            _set_from_textract(
                record,
                "total_credit_hours",
                record["total_credit_hours_stated"],
                confidence=record.get("total_credit_hours_stated_confidence", "high"),
                page_number=page_number,
                spans=(record.get("total_credit_hours_stated_source") or {}).get("text_spans"),
            )
        elif courses:
            total = sum(
                float(course.get("credit_hours") or 0)
                for course in courses
                if not course.get("transfer_marker")
            )
            if total > 0:
                _set_from_textract(
                    record,
                    "total_credit_hours",
                    int(total) if total.is_integer() else total,
                    confidence="medium",
                    page_number=page_number,
                    spans=["Computed from Textract course table credit-hour column"],
                )

    raw_text = page.get("raw_text") or ""
    if _PNV_CODE_RE.search(raw_text) or any(
        str(course.get("code") or "").upper().startswith("PNV")
        for course in courses
    ):
        _set_from_textract(
            record,
            "program_type",
            "ms_practical_nursing",
            confidence="high",
            page_number=page_number,
            spans=["PNV course code detected in Textract text/table data"],
        )

    degree_type = _detect_claimed_degree_type(raw_text)
    if degree_type:
        _set_from_textract(
            record,
            "claimed_degree_type",
            degree_type,
            confidence="medium",
            page_number=page_number,
            spans=[_first_matching_line(raw_text, degree_type) or degree_type],
        )

    scale_format, scale_max = _detect_grading_scale(raw_text)
    if scale_format:
        _set_from_textract(
            record,
            "grading_scale_format",
            scale_format,
            confidence="medium",
            page_number=page_number,
            spans=[_first_matching_line(raw_text, "grade") or "grading scale"],
        )
    if scale_max is not None:
        _set_from_textract(
            record,
            "grading_scale_maximum",
            scale_max,
            confidence="medium",
            page_number=page_number,
            spans=[_first_matching_line(raw_text, str(scale_max)) or str(scale_max)],
        )

    if _degree_conferral_statement_found(raw_text):
        _set_from_textract(
            record,
            "degree_conferral_statement_present",
            True,
            confidence="high",
            page_number=page_number,
            spans=[_first_degree_conferral_line(raw_text) or "Degree conferral statement"],
        )


def _extract_academic_tables(page: dict, page_number: int) -> dict:
    courses: list[dict] = []
    semesters_by_term: dict[str, dict] = {}
    term_order: list[str] = []
    current_term: str | None = None
    header: dict[str, int] | None = None

    for table in page.get("tables") or []:
        if not isinstance(table, dict):
            continue
        rows = table.get("rows") or []
        if not isinstance(rows, list):
            continue

        for row in rows:
            if not isinstance(row, list):
                continue
            cells = [str(cell or "").strip() for cell in row]
            row_text = _row_text(cells)
            if not row_text:
                continue

            term = _extract_term_label(row_text)
            if term and not _find_course_code(row_text):
                current_term = term
                _ensure_semester(semesters_by_term, term_order, current_term, row_text, page_number)
                header = None
                continue

            maybe_header = _table_header_map(cells)
            if maybe_header:
                header = maybe_header
                continue

            if current_term:
                _update_semester_summary(
                    semesters_by_term[current_term],
                    cells,
                    row_text,
                    header,
                )

            course = _course_from_table_row(
                cells,
                row_text,
                header,
                current_term,
                term_order,
                page_number,
            )
            if course:
                courses.append(course)
                if current_term:
                    sem = _ensure_semester(
                        semesters_by_term,
                        term_order,
                        current_term,
                        row_text,
                        page_number,
                    )
                    sem["courses"].append(course["code"] or course["name"])

    return {
        "courses": courses,
        "semesters": [semesters_by_term[term] for term in term_order],
    }


def _row_text(cells: list[str]) -> str:
    return " ".join(cell for cell in cells if cell).strip()


def _table_header_map(cells: list[str]) -> dict[str, int] | None:
    mapped: dict[str, int] = {}
    normalized = [_normalize_header_cell(cell) for cell in cells]
    for idx, cell in enumerate(normalized):
        if not cell:
            continue
        if "quality" in cell or "grade point" in cell or cell in {"points", "pts", "qp"}:
            mapped.setdefault("grade_points", idx)
        elif "cum" in cell and "gpa" in cell:
            mapped.setdefault("cum_gpa", idx)
        elif ("term" in cell or "semester" in cell or "current" in cell) and "gpa" in cell:
            mapped.setdefault("term_gpa", idx)
        elif "gpa" in cell and "term_gpa" not in mapped:
            mapped.setdefault("term_gpa", idx)
        elif "cum" in cell and ("credit" in cell or "hour" in cell):
            mapped.setdefault("cum_credit_hours", idx)
        elif (
            "credit" in cell
            or "credits" in cell
            or "hour" in cell
            or cell in {"cr", "hrs", "ch"}
        ):
            mapped.setdefault("credit_hours", idx)
        elif "grade" in cell or cell in {"grd", "gr"}:
            mapped.setdefault("grade", idx)
        elif "title" in cell or "description" in cell or "name" in cell:
            mapped.setdefault("course_title", idx)
        elif "course" in cell or "subject" in cell or "catalog" in cell or "code" in cell:
            mapped.setdefault("code", idx)

    if any(key in mapped for key in ("code", "course_title")) and any(
        key in mapped for key in ("credit_hours", "grade", "grade_points")
    ):
        return mapped
    if any(key in mapped for key in ("term_gpa", "cum_gpa", "credit_hours")) and not _find_course_code(_row_text(cells)):
        return mapped
    return None


def _normalize_header_cell(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def _course_from_table_row(
    cells: list[str],
    row_text: str,
    header: dict[str, int] | None,
    current_term: str | None,
    term_order: list[str],
    page_number: int,
) -> dict | None:
    code = _find_course_code(
        _cell_by_header(cells, header, "code")
        or row_text
    )
    if not code:
        return None

    title = _cell_by_header(cells, header, "course_title")
    if not title:
        title = _strip_course_code(_cell_by_header(cells, header, "code") or row_text, code)

    credit_hours = _parse_number(
        _cell_by_header(cells, header, "credit_hours"),
        max_value=40.0,
    )
    grade = _extract_grade(_cell_by_header(cells, header, "grade")) or _extract_grade(row_text)
    grade_points = _parse_number(
        _cell_by_header(cells, header, "grade_points"),
        max_value=200.0,
    )
    if grade_points is None and grade:
        grade_points = _LETTER_GRADE_POINTS.get(grade.upper())

    transfer = bool(re.search(r"\b(TR|TRANSFER|CREDIT\s+AWARDED)\b", row_text, re.I))
    retake = bool(re.search(r"\b(REPEAT|RETAKE|REPLACED|ADJ|ADJUSTMENT)\b", row_text, re.I))
    semester = term_order.index(current_term) + 1 if current_term in term_order else None

    return {
        "name": title or code,
        "code": code,
        "course_code": code,
        "course_title": title or None,
        "credit_hours": credit_hours,
        "grade": grade,
        "grade_points": grade_points,
        "semester": semester,
        "start_date": None,
        "end_date": None,
        "retake_marker": retake,
        "transfer_marker": transfer,
        "source_location": {
            "page_number": page_number,
            "text_spans": [row_text],
        },
    }


def _cell_by_header(cells: list[str], header: dict[str, int] | None, key: str) -> str | None:
    if not header or key not in header:
        return None
    idx = header[key]
    if idx < 0 or idx >= len(cells):
        return None
    return cells[idx]


def _find_course_code(text: str | None) -> str | None:
    match = _COURSE_CODE_RE.search(str(text or "").upper())
    if not match:
        return None
    return f"{match.group(1)} {match.group(2)}"


def _strip_course_code(text: str | None, code: str) -> str | None:
    value = str(text or "")
    stripped = _COURSE_CODE_RE.sub("", value, count=1)
    stripped = re.sub(r"\s+", " ", stripped).strip(" -:\t")
    if not stripped or stripped == value:
        return None
    return stripped


def _extract_grade(text: str | None) -> str | None:
    match = _GRADE_RE.search(str(text or ""))
    if not match:
        return None
    grade = match.group(1).upper()
    return "Pass" if grade == "PASS" else grade


def _extract_term_label(text: str) -> str | None:
    match = _TERM_RE.search(text)
    if not match:
        return None
    return re.sub(r"\s+", " ", match.group(1)).strip().title()


def _ensure_semester(
    semesters_by_term: dict[str, dict],
    term_order: list[str],
    term: str,
    source_text: str,
    page_number: int,
) -> dict:
    if term not in semesters_by_term:
        term_order.append(term)
        semesters_by_term[term] = {
            "term": term,
            "term_type": _term_type(term),
            "start_date": None,
            "end_date": None,
            "courses": [],
            "term_gpa_stated": None,
            "term_credit_hours_stated": None,
            "cum_gpa_stated_after_term": None,
            "source_location": {
                "page_number": page_number,
                "text_spans": [source_text],
            },
        }
    return semesters_by_term[term]


def _term_type(term: str) -> str | None:
    lowered = term.lower()
    for item in ("fall", "spring", "summer", "winter"):
        if item in lowered:
            return item
    return None


def _update_semester_summary(
    semester: dict,
    cells: list[str],
    row_text: str,
    header: dict[str, int] | None,
) -> None:
    updates = {
        "term_gpa_stated": _parse_number(_cell_by_header(cells, header, "term_gpa"), max_value=5.0),
        "term_credit_hours_stated": _parse_number(_cell_by_header(cells, header, "credit_hours"), max_value=80.0),
        "cum_gpa_stated_after_term": _parse_number(_cell_by_header(cells, header, "cum_gpa"), max_value=5.0),
        "cum_credit_hours_stated": _parse_number(_cell_by_header(cells, header, "cum_credit_hours"), max_value=250.0),
    }
    labeled = {
        "term_gpa_stated": _extract_number_from_text(
            row_text,
            [r"(?:term|semester|current)\s+gpa"],
            max_value=5.0,
        ),
        "term_credit_hours_stated": _extract_number_from_text(
            row_text,
            [r"(?:term|semester|current).{0,20}(?:credits?|hours?)"],
            max_value=80.0,
        ),
        "cum_gpa_stated_after_term": _extract_number_from_text(
            row_text,
            [r"(?:cum(?:ulative)?|overall|career)\s+gpa", r"\bcgpa\b"],
            max_value=5.0,
        ),
        "cum_credit_hours_stated": _extract_number_from_text(
            row_text,
            [r"(?:cum(?:ulative)?|overall|career).{0,20}(?:credits?|hours?)"],
            max_value=250.0,
        ),
        "cum_quality_points_stated": _extract_number_from_text(
            row_text,
            [r"(?:cum(?:ulative)?|overall|career).{0,20}(?:quality|grade)\s+points"],
            max_value=1000.0,
        ),
    }
    for key, value in updates.items():
        if value is not None:
            semester[key] = value
            spans = semester.setdefault("source_location", {}).setdefault("text_spans", [])
            if row_text not in spans:
                spans.append(row_text)
    for key, value in labeled.items():
        if value is not None:
            semester[key] = value
            spans = semester.setdefault("source_location", {}).setdefault("text_spans", [])
            if row_text not in spans:
                spans.append(row_text)


def _find_labeled_number(
    page: dict,
    labels: list[str],
    *,
    max_value: float | None = None,
) -> tuple[float | int, str] | None:
    for text in _page_text_evidence(page):
        value = _extract_number_from_text(text, labels, max_value=max_value)
        if value is not None:
            return value, text
    return None


def _page_text_evidence(page: dict) -> list[str]:
    evidence: list[str] = []
    for line in page.get("lines") or []:
        if isinstance(line, dict) and line.get("text"):
            evidence.append(str(line["text"]))
    for table in page.get("tables") or []:
        if not isinstance(table, dict):
            continue
        evidence.extend(str(title) for title in table.get("titles") or [] if title)
        for row in table.get("rows") or []:
            if isinstance(row, list):
                evidence.append(_row_text([str(cell or "") for cell in row]))
        evidence.extend(str(footer) for footer in table.get("footers") or [] if footer)
    for form in page.get("forms") or []:
        if isinstance(form, dict):
            evidence.append(f"{form.get('key') or ''} {form.get('value') or ''}".strip())
    if page.get("raw_text"):
        evidence.extend(str(page["raw_text"]).splitlines())
    return [item for item in evidence if item]


def _extract_number_from_text(
    text: str | None,
    labels: list[str],
    *,
    max_value: float | None = None,
) -> float | int | None:
    source = str(text or "")
    for label in labels:
        match = re.search(label + r"[^0-9]{0,40}(\d+(?:\.\d+)?)", source, re.I)
        if match:
            return _parse_number(match.group(1), max_value=max_value)
    return None


def _parse_number(value: str | None, *, max_value: float | None = None) -> float | int | None:
    match = re.search(r"\d+(?:\.\d+)?", str(value or ""))
    if not match:
        return None
    number = float(match.group(0))
    if max_value is not None and number > max_value:
        return None
    return int(number) if number.is_integer() else number


def _detect_claimed_degree_type(raw_text: str) -> str | None:
    text = raw_text.lower()
    if "practical nursing" in text or "licensed practical nurse" in text or re.search(r"\blpn\b", text):
        return "LPN"
    if "associate" in text and "nursing" in text:
        return "ADN"
    if "bachelor" in text and "nursing" in text:
        return "BSN"
    if re.search(r"\bbsn\b", text):
        return "BSN"
    if re.search(r"\badn\b", text):
        return "ADN"
    return None


def _detect_grading_scale(raw_text: str) -> tuple[str | None, float | None]:
    text = raw_text.lower()
    if re.search(r"\ba\s*=\s*4(?:\.0)?", text) or "grade point" in text:
        return "letter_grade_us", 4.0
    if "pass/fail" in text or "pass fail" in text:
        return "pass_fail", None
    if "percent" in text or "percentage" in text:
        return "percentage", 100.0
    return None, None


def _degree_conferral_statement_found(raw_text: str) -> bool:
    return bool(re.search(
        r"(degree|certificate|diploma|credential).{0,40}"
        r"(conferred|awarded|earned|completed|granted)",
        raw_text,
        re.I | re.S,
    ))


def _first_degree_conferral_line(raw_text: str) -> str | None:
    for line in raw_text.splitlines():
        if _degree_conferral_statement_found(line):
            return line.strip()
    return None


def _first_matching_line(raw_text: str, needle: str) -> str | None:
    target = str(needle or "").lower()
    for line in raw_text.splitlines():
        if target in line.lower():
            return line.strip()
    return None


def _verified_query_answer(page: dict, alias: str) -> str | None:
    for query in page.get("queries") or []:
        if not isinstance(query, dict) or query.get("alias") != alias:
            continue
        for answer in query.get("answers") or []:
            if not isinstance(answer, dict) or answer.get("verified") is False:
                continue
            text = str(answer.get("text") or "").strip()
            if text:
                return text
    return None


def _extract_issuing_institution_from_textract(page: dict) -> tuple[str, str] | None:
    """Prefer issuer header lines over Textract query answers that may hit recipients."""
    lines = [
        str(line.get("text") or "").strip()
        for line in page.get("lines") or []
        if isinstance(line, dict) and str(line.get("text") or "").strip()
    ]
    if not lines and page.get("raw_text"):
        lines = [
            line.strip()
            for line in str(page.get("raw_text") or "").splitlines()
            if line.strip()
        ]

    candidates: list[tuple[int, str, str]] = []
    for idx, line in enumerate(lines[:40]):
        if _line_is_recipient_or_contact_context(line):
            continue
        candidate = _institution_name_from_line_window(lines, idx)
        if not candidate:
            continue
        name, source = candidate
        candidates.append((_institution_header_score(name, idx), name, source))

    if not candidates:
        return None
    _score, name, source = max(candidates, key=lambda item: item[0])
    return name, source


def _institution_name_from_line_window(
    lines: list[str],
    idx: int,
) -> tuple[str, str] | None:
    line = _clean_institution_line(lines[idx])
    if not _looks_like_institution_line(line):
        return None

    previous = _clean_institution_line(lines[idx - 1]) if idx > 0 else ""
    if (
        previous
        and len(previous.split()) <= 4
        and not _line_is_recipient_or_contact_context(previous)
        and not _looks_like_label_line(previous)
        and not _looks_like_address_line(previous)
        and previous.upper() == previous
    ):
        combined = f"{previous} {line}"
        if _looks_like_institution_line(combined):
            return _normalize_institution_name(combined), f"{previous} {line}"

    return _normalize_institution_name(line), line


def _clean_institution_line(line: str) -> str:
    value = re.sub(r"^(issued\s+by|institution|school|college)\s*[:\-]\s*", "", line, flags=re.I)
    return re.sub(r"\s+", " ", value).strip(" -:\t")


def _looks_like_institution_line(line: str) -> bool:
    text = str(line or "").strip()
    if not text or len(text) < 5:
        return False
    lowered = text.lower()
    if _line_is_recipient_or_contact_context(text):
        return False
    if any(term in lowered for term in (
        "college",
        "university",
        "school of",
        "institute",
        "academy",
        "community college",
    )):
        return True
    return False


def _line_is_recipient_or_contact_context(line: str) -> bool:
    lowered = str(line or "").lower().strip()
    return (
        lowered.startswith("issued to")
        or lowered.startswith("send to")
        or lowered.startswith("sent to")
        or lowered.startswith("mailed to")
        or lowered.startswith("recipient")
        or lowered.startswith("current name")
        or lowered.startswith("record of")
        or "board of nursing" in lowered
        or "pear orchard" in lowered
        or "ridgeland" in lowered
    )


def _looks_like_label_line(line: str) -> bool:
    lowered = str(line or "").lower().strip()
    return lowered.endswith(":") or lowered in {
        "ssn:",
        "student no:",
        "date of birth:",
        "current name:",
        "record of:",
        "page:",
    }


def _looks_like_address_line(line: str) -> bool:
    text = str(line or "")
    lowered = text.lower()
    return bool(
        re.search(r"\b\d{5}(?:-\d{4})?\b", text)
        or re.search(r"\b(p\.?o\.?\s*box|street|st\.|road|rd\.|avenue|ave\.|suite|ste)\b", lowered)
    )


def _institution_header_score(name: str, idx: int) -> int:
    lowered = name.lower()
    score = max(0, 100 - idx)
    if "community college" in lowered:
        score += 30
    elif "college" in lowered or "university" in lowered:
        score += 20
    if "admissions" in lowered or "records" in lowered:
        score -= 20
    return score


def _normalize_institution_name(name: str) -> str:
    text = re.sub(r"\s+", " ", str(name or "")).strip()
    if text.upper() == text:
        return text.title()
    return text


def _is_recipient_institution_answer(page: dict, answer: str) -> bool:
    answer_norm = _normalize_query_text(answer)
    if not answer_norm:
        return False
    for line in _page_text_evidence(page):
        line_norm = _normalize_query_text(line)
        if answer_norm and answer_norm in line_norm and _line_is_recipient_or_contact_context(line):
            return True
    return False


def _set_from_textract(
    record: dict,
    field: str,
    value,
    *,
    confidence: str,
    page_number: int,
    spans: list[str] | None = None,
) -> None:
    if value in (None, "", [], "unclear"):
        return
    record[field] = value
    record[f"{field}_confidence"] = confidence
    record[f"{field}_source"] = {
        "page_number": page_number,
        "text_spans": spans or ([str(value)] if value not in (None, "") else []),
    }


def _looks_like_transcript_identity_area(page: dict) -> bool:
    raw_text = (page.get("raw_text") or "").lower()
    return "stuid" in raw_text or "student id" in raw_text or "student no" in raw_text


def _coerce_query_value(field: str, value: str):
    if field in {"final_cum_gpa_stated", "total_credit_hours"}:
        match = re.search(r"\d+(?:\.\d+)?", value)
        if match:
            number = float(match.group(0))
            return int(number) if number.is_integer() else number
    return value


def _apply_registrar_from_textract(record: dict, page: dict, page_number: int) -> None:
    if isinstance(record.get("registrar_block"), dict):
        return
    name = _verified_query_answer(page, "registrar_name")
    title = _verified_query_answer(page, "registrar_title")
    contact = _verified_query_answer(page, "registrar_contact")
    signature_present = "yes" if page.get("signatures") else "no"
    if not any([name, title, contact, signature_present == "yes"]):
        return
    record["registrar_block"] = {
        "detected": "yes",
        "location": "footer" if page_number else "none",
        "page_number": page_number,
        "name_text": name,
        "title_text": title,
        "signature_present": signature_present,
        "signature_type": "handwritten" if signature_present == "yes" else "none",
        "contact_info_text": contact,
    }
    record["registrar_block_confidence"] = "medium"
    record["registrar_block_source"] = {
        "page_number": page_number,
        "text_spans": [text for text in (name, title, contact) if text],
    }


def _detect_identity_redaction_marks(image) -> bool:
    """Detect large black bars in the upper transcript identity/header area."""
    grayscale = image.convert("L")
    width, height = grayscale.size
    scan_box = grayscale.crop((0, 0, width, int(height * 0.30)))
    pixels = scan_box.load()
    min_width = max(60, int(width * 0.055))
    min_height = max(8, int(height * 0.004))

    for y in range(scan_box.height):
        run_start: int | None = None
        for x in range(scan_box.width):
            is_dark = pixels[x, y] < 45
            if is_dark and run_start is None:
                run_start = x
            if (not is_dark or x == scan_box.width - 1) and run_start is not None:
                run_end = x if not is_dark else x + 1
                if run_end - run_start >= min_width:
                    vertical = _dark_run_height(scan_box, run_start, run_end, y)
                    if vertical >= min_height:
                        return True
                run_start = None
    return False


def _dark_run_height(image, x0: int, x1: int, y0: int) -> int:
    pixels = image.load()
    height = 0
    for y in range(y0, image.height):
        dark_count = sum(1 for x in range(x0, x1) if pixels[x, y] < 45)
        if dark_count / max(1, x1 - x0) < 0.65:
            break
        height += 1
    return height


def _call_bedrock_for_page(
    image_bytes: bytes,
    page_number: int,
    textract_context: dict | None = None,
) -> dict:
    """Run one page through Nova and parse the JSON response."""
    try:
        response_body = _invoke_bedrock_for_page(image_bytes, textract_context)
    except ClientError as exc:
        error = exc.response.get("Error", {})
        if (
            error.get("Code") == "ValidationException"
            and "Input Tokens Exceeded" in (error.get("Message") or "")
            and textract_context
        ):
            logger.warning(json.dumps({
                "event": "nova_input_tokens_exceeded_retry",
                "page_number": page_number,
            }))
            response_body = _invoke_bedrock_for_page(
                image_bytes,
                _minimal_textract_context(textract_context),
            )
        else:
            raise

    raw_text = response_body["output"]["message"]["content"][0]["text"]
    stop_reason = response_body.get("stopReason", "unknown")
    usage = response_body.get("usage") or {}

    try:
        return _normalize_nova_response_shape(_parse_nova_json(raw_text), page_number)
    except json.JSONDecodeError as exc:
        logger.error(
            json.dumps({
                "event": "nova_json_parse_error",
                "page_number": page_number,
                "error": str(exc),
                "stop_reason": stop_reason,
                "input_tokens": usage.get("inputTokens"),
                "output_tokens": usage.get("outputTokens"),
                "raw_text_length": len(raw_text),
                "raw_text_preview": raw_text[:500],
            })
        )
        raise ValueError(
            f"Nova response for page {page_number} is not valid JSON"
        ) from exc


def _call_bedrock_for_textract_page(
    page_number: int,
    textract_context: dict,
) -> dict:
    """Run one page's Textract context through Nova for academic structuring."""
    try:
        try:
            response_body = _invoke_bedrock_for_textract_page(textract_context)
        except ClientError as exc:
            error = exc.response.get("Error", {})
            if (
                error.get("Code") == "ValidationException"
                and "Input Tokens Exceeded" in (error.get("Message") or "")
            ):
                logger.warning(json.dumps({
                    "event": "nova_textract_input_tokens_exceeded_retry",
                    "page_number": page_number,
                }))
                response_body = _invoke_bedrock_for_textract_page(
                    _minimal_textract_context(textract_context) or textract_context
                )
            else:
                raise

        raw_text = response_body["output"]["message"]["content"][0]["text"]
        page = (textract_context.get("page") or {}) if isinstance(textract_context, dict) else {}
        return _normalize_nova_academic_response_shape(
            _parse_nova_json(raw_text),
            page,
            page_number,
        )
    except Exception as exc:
        logger.warning(json.dumps({
            "event": "nova_textract_interpreter_failed",
            "page_number": page_number,
            "error": str(exc),
        }))
        return {}


def _invoke_bedrock_for_page(
    image_bytes: bytes,
    textract_context: dict | None = None,
) -> dict:
    system_prompt, user_prompt = build_extraction_prompt(textract_context)
    b64_image = base64.b64encode(image_bytes).decode("utf-8")

    body = json.dumps({
        "schemaVersion": "messages-v1",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "image": {
                            "format": "png",
                            "source": {"bytes": b64_image},
                        }
                    },
                    {"text": user_prompt},
                ],
            }
        ],
        "system": [{"text": system_prompt}],
        "inferenceConfig": {
            "max_new_tokens": BEDROCK_MAX_NEW_TOKENS,
            "temperature": 0.0,
            "topP": 1.0,
        },
    })

    response = _bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )

    return json.loads(response["body"].read())


def _invoke_bedrock_for_textract_page(textract_context: dict) -> dict:
    system_prompt, user_prompt = build_textract_structuring_prompt(textract_context)

    body = json.dumps({
        "schemaVersion": "messages-v1",
        "messages": [
            {
                "role": "user",
                "content": [{"text": user_prompt}],
            }
        ],
        "system": [{"text": system_prompt}],
        "inferenceConfig": {
            "max_new_tokens": BEDROCK_MAX_NEW_TOKENS,
            "temperature": 0.0,
            "topP": 1.0,
        },
    })

    response = _bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        contentType="application/json",
        accept="application/json",
        body=body,
    )

    return json.loads(response["body"].read())


def _parse_nova_json(raw_text: str) -> dict:
    """Parse a Nova JSON object even when it is wrapped in prose/fences."""
    text = str(raw_text or "").lstrip("\ufeff").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        parsed = _parse_json_from_wrapped_text(text)

    if not isinstance(parsed, dict):
        raise json.JSONDecodeError("Nova response JSON is not an object", text, 0)
    return parsed


def _parse_json_from_wrapped_text(text: str) -> dict:
    fenced = text
    if fenced.startswith("```"):
        fenced = fenced.removeprefix("```json").removeprefix("```").strip()
        if fenced.endswith("```"):
            fenced = fenced[:-3].strip()
        return json.loads(fenced)

    decoder = json.JSONDecoder()
    for idx, char in enumerate(text):
        if char != "{":
            continue
        try:
            parsed, _end_idx = decoder.raw_decode(text[idx:])
        except json.JSONDecodeError:
            continue
        logger.warning(
            json.dumps({
                "event": "nova_json_recovered",
                "recovery": "embedded_object",
            })
        )
        return parsed

    first = text.find("{")
    last = text.rfind("}")
    if first >= 0 and last > first:
        logger.warning(
            json.dumps({
                "event": "nova_json_recovered",
                "recovery": "brace_slice",
            })
        )
        return json.loads(text[first : last + 1])

    raise json.JSONDecodeError("No JSON object found in Nova response", text, 0)


def _parse_nova_json_object(raw_text: str) -> dict:
    """Backward-compatible alias for tests and callers using the old helper name."""
    return _parse_nova_json(raw_text)


def _parse_model_json_object(raw_text: str) -> dict:
    """Backward-compatible alias for the previous model JSON parser name."""
    return _parse_nova_json(raw_text)


def handler(event, context):
    """Download the PDF, extract each page, and persist the merged result."""
    logger.info("ExtractLambda invoked: %s", json.dumps(event))

    application_id = event["applicationId"]
    s3_key = event["s3_key"]
    bucket = event.get("bucket") or BUCKET_NAME

    textract_doc = _analyze_transcript_with_textract(bucket, s3_key, application_id)
    textract_key = f"processed/{application_id}/textract_TRANSCRIPT.json"
    _s3.put_object(
        Bucket=bucket,
        Key=textract_key,
        Body=json.dumps(textract_doc, indent=2).encode("utf-8"),
        ContentType="application/json",
    )

    # Download the source PDF to local Lambda storage.
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

    # Render once up front so each page can be stored and sent to Nova.
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
        if os.path.exists(local_pdf):
            os.unlink(local_pdf)

    page_extractions = []

    for page_idx, img in enumerate(images, start=1):
        width, height = img.size

        # Persist the rendered page for reviewer highlighting.
        img_key = f"processed/{application_id}/page_transcript_{page_idx}.png"
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            img.save(tmp.name, format="PNG")
            tmp_path = tmp.name
        try:
            with open(tmp_path, "rb") as fh:
                image_bytes = fh.read()
            _s3.upload_file(tmp_path, bucket, img_key)
        finally:
            os.unlink(tmp_path)

        # Extract the page into the prompt schema using Textract text structure
        # plus Nova visual reasoning for physical document flags.
        textract_context = _textract_context_for_page(textract_doc, page_idx)
        nova_raw = _call_bedrock_for_page(
            image_bytes,
            page_idx,
            textract_context,
        )

        # Convert Nova's nested field records into the downstream page shape.
        page_record = _validate_and_build_page_record(
            nova_raw, page_idx, width, height
        )
        _apply_textract_backed_page_fields(
            page_record,
            textract_doc,
            page_idx,
            img,
        )
        if NOVA_TEXTRACT_INTERPRETER_ENABLED:
            nova_academic = _call_bedrock_for_textract_page(page_idx, textract_context)
            _apply_nova_textract_academic_fields(
                page_record,
                nova_academic,
                page_idx,
            )
        page_extractions.append(page_record)

    _apply_document_level_extraction_fields(page_extractions, len(images))

    # Write the document-level extraction payload for AggregationLambda.
    extraction_key = f"processed/{application_id}/extraction_transcript.json"
    extraction_doc = {
        "schema_version": "1.0",
        "application_id": application_id,
        "document_type": "TRANSCRIPT",
        "page_count": len(images),
        "textract_s3_key": textract_key,
        "textract": textract_doc,
        "bedrock_model_id": BEDROCK_MODEL_ID,
        "prompt_version": PROMPT_VERSION,
        "nova_textract_interpreter_enabled": NOVA_TEXTRACT_INTERPRETER_ENABLED,
        "extraction_ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "pages": page_extractions,
    }

    _s3.put_object(
        Bucket=bucket,
        Key=extraction_key,
        Body=json.dumps(extraction_doc, indent=2).encode("utf-8"),
        ContentType="application/json",
    )
    _write_document_record(
        application_id,
        page_count=len(images),
        extraction_key=extraction_key,
        textract_key=textract_key,
    )

    logger.info(
        json.dumps({
            "event": "extraction_complete",
            "applicationId": application_id,
            "page_count": len(images),
            "textract_s3_key": textract_key,
            "extraction_s3_key": extraction_key,
        })
    )

    return {
        "applicationId": application_id,
        "page_count": len(images),
        "textract_s3_key": textract_key,
        "extraction_s3_key": extraction_key,
    }


def _write_document_record(
    application_id: str,
    *,
    page_count: int,
    extraction_key: str,
    textract_key: str,
) -> None:
    if not TABLE_NAME:
        return

    table = _dynamo.Table(TABLE_NAME)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    try:
        table.put_item(
            Item={
                "PK": f"APP#{application_id}",
                "SK": "DOCUMENT#TRANSCRIPT",
                "entity_type": "DOCUMENT",
                "doc_type": "TRANSCRIPT",
                "status": "EXTRACTED",
                "s3_extraction_key": extraction_key,
                "s3_textract_key": textract_key,
                "model_id": BEDROCK_MODEL_ID,
                "prompt_version": PROMPT_VERSION,
                "page_count": page_count,
                "updated_ts": now,
            }
        )
    except ClientError as exc:
        if exc.response.get("Error", {}).get("Code") == "ResourceNotFoundException":
            logger.warning("Skipping document record write because table %s was not found", TABLE_NAME)
            return
        raise

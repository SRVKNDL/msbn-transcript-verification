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

from prompt import PROMPT_VERSION, VOCABULARY, build_extraction_prompt

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
_EXPECTED_EXTRACTION_FIELDS = {
    "applicant_name",
    "applicant_name_visible",
    "institution",
    "country",
    "license_number",
    "program_year",
    "document_page_count",
    "seal_type",
    "seal_quality",
    "seal_visible_text",
    "security_features_present",
    "security_features_assessable",
    "registrar_block",
    "print_technology",
    "text_alignment",
    "suspected_alteration_fields",
    "identity_redaction_detected",
    "overlapping_text_detected",
    "degree_conferral_statement_present",
    "degree_conferred_date",
    "date_of_birth",
    "programs",
    "courses",
    "semesters",
    "grading_scale_format",
    "final_cum_gpa_stated",
    "program_type",
    "total_credit_hours",
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
    """Flatten Nova output and warn on enum drift without failing the run."""
    record: dict = {
        "page_number": page_number,
        "image_dimensions": {"width": width, "height": height},
    }

    for field, meta in nova_response.items():
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
    """Accept known wrappers, but reject generic single-field records."""
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

    if not (_EXPECTED_EXTRACTION_FIELDS & set(nova_response.keys())):
        logger.warning(json.dumps({
            "event": "nova_unexpected_schema_ignored",
            "page_number": page_number,
            "keys": sorted(nova_response.keys())[:40],
        }))
        return {}

    return nova_response


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
        _set_if_missing(
            record,
            "applicant_name",
            applicant_answer,
            confidence="high",
            page_number=page_number,
        )
        _set_if_missing(
            record,
            "applicant_name_visible",
            "yes",
            confidence="high",
            page_number=page_number,
            spans=[applicant_answer],
        )
    elif page_number == 1 and _looks_like_transcript_identity_area(page):
        _set_if_missing(
            record,
            "applicant_name_visible",
            "no",
            confidence="high",
            page_number=page_number,
            spans=["No readable applicant name found in transcript identity area"],
        )

    for alias, field in (
        ("institution", "institution"),
        ("program_year", "program_year"),
        ("document_issue_date", "document_issue_date"),
        ("degree_conferred_date", "degree_conferred_date"),
        ("final_cum_gpa_stated", "final_cum_gpa_stated"),
        ("total_credit_hours", "total_credit_hours"),
        ("seal_visible_text", "seal_visible_text"),
    ):
        answer = _verified_query_answer(page, alias)
        if answer:
            _set_if_missing(
                record,
                field,
                _coerce_query_value(field, answer),
                confidence="high",
                page_number=page_number,
                spans=[answer],
            )

    _apply_registrar_from_textract(record, page, page_number)

    if _detect_identity_redaction_marks(image):
        _set_if_missing(
            record,
            "identity_redaction_detected",
            True,
            confidence="high",
            page_number=page_number,
            spans=["Black redaction mark in applicant/student identity area"],
        )
        _set_if_missing(
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


def _set_if_missing(
    record: dict,
    field: str,
    value,
    *,
    confidence: str,
    page_number: int,
    spans: list[str] | None = None,
) -> None:
    existing = record.get(field)
    if existing not in (None, "", [], "unclear"):
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
        "contact_text": contact,
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
        nova_raw = _call_bedrock_for_page(
            image_bytes,
            page_idx,
            _textract_context_for_page(textract_doc, page_idx),
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

"""Prompt text and enum vocabulary for transcript extraction."""

PROMPT_VERSION = "2.1"

# Enum values the handler accepts from Nova.
# Only scalar enum fields appear here; boolean, free-text, array-of-objects,
# and numeric fields are validated structurally by the model, not via this dict.

VOCABULARY: dict[str, set] = {
    # Physical document fields.
    "seal_type": {
        "embossed", "stamped_ink", "printed_flat",
        "sticker_foil", "absent", "unclear",
    },
    "seal_quality": {"clear", "degraded", "pixelated", "absent", "unclear"},
    "print_technology": {
        "typewriter", "dot_matrix", "laser", "inkjet", "photocopy", "unclear",
    },
    "paper_size_format": {"us_letter", "a4", "legal", "custom_irregular", "unclear"},
    "text_alignment": {"normal", "misaligned", "uneven_spacing", "unclear"},
    "document_provenance_appearance": {
        "original", "color_copy", "scan_artifacts_present", "unclear",
    },
    "applicant_name_visible": {"yes", "no", "unclear"},
    "security_features_present": {
        "watermark", "micro_printing", "hologram", "serial_number",
    },
    "security_features_assessable": {"yes", "no"},
    "printer_quality_consistency": {"consistent", "inconsistent", "unclear"},
    # Academic content fields.
    "grading_scale_format": {
        "letter_grade_us", "percentage", "20_point_french",
        "5_point_russian", "pass_fail", "mixed", "unclear",
    },
    "language_of_issue": {"english", "french", "spanish", "other", "unclear"},
    "suspicious_course_names": set(),   # free-text strings; no controlled vocab
    "dates_chronology_ok": {"yes", "no", "unclear"},
    "dates_chronology_issue": {
        "none", "overlap", "gap",
        "enrollment_implausibly_early", "enrollment_implausibly_late", "other",
    },
    # New content control vocab for CONT_003.
    "claimed_degree_type": {
        "LPN", "ADN", "BSN", "ABSN", "RN-BSN", "LPN-RN",
        "MSN", "DNP", "CRNA", "unclear",
    },
    # Program and institution fields.
    "institution_address_present": {"yes", "no", "unclear"},
    "institution_phone_present": {"yes", "no", "unclear"},
    "institution_website_present": {"yes", "no", "unclear"},
    # MS-specific program classification.
    "program_type": {"ms_practical_nursing", "other", "unclear"},
    # Confidence appears beside every extracted field.
    "_confidence": {"high", "medium", "low"},
}

# System prompt: response shape and output constraints.

_SYSTEM_PROMPT = """\
You are a forensic document examiner assisting the Mississippi State Board of \
Nursing (MSBN) in verifying nursing school transcripts for licensure eligibility.
Your task is visual document examination only.

Do NOT extract academic transcript data. Do NOT return courses, grades, GPA,
credit hours, programs, dates, institution fields, or other text/table values.
Amazon Textract is the authoritative source for text, tables, forms, query
answers, signatures, courses, GPA, and credit-hour values. You may use
TEXTRACT_CONTEXT_JSON only to orient yourself to the page and to cross-check
whether visual artifacts align with Textract-detected layout and signatures.

Inspect the page image for physical authenticity and tampering evidence:
- Seal/watermark presence, type, quality, and visible security features.
- Registrar attestation appearance and whether Textract SIGNATURE blocks align
  with a visible signature area.
- Print technology, paper format, print density, font consistency, baseline and
  column alignment.
- Correction fluid, erasures, smudges, obliteration marks, mixed ink, blackouts,
  redactions, overlapping/layered text, clipped headers, scattered fragments, and
  other signs of Photoshop/PDF-editor modification.

When reporting tampering, be specific. Describe the visible artifact and the
affected area. If identity data is blacked out, treat that as physical tampering
evidence, not as a request to recover the redacted text.

Return valid JSON only. No markdown fences, preamble, or explanation.
Return only the requested visual/physical fields. The response must be a single
JSON object starting with "{" and ending with "}".

FIELD FORMAT:
  "<field_name>": {
    "value": <enum string, boolean, array, object, or null>,
    "confidence": "high" | "medium" | "low",
    "source_location": {
      "page_number": 1,
      "text_spans": ["short visual evidence description"]
    }
  }

For visual fields without a precise text span, use a short evidence description
such as "upper-right seal area", "student identity header", or "grade table rows".
"""

# User prompt: extraction fields and allowed values.

_USER_PROMPT = """\
Inspect the attached transcript page image for physical authenticity and
tampering only. Textract-backed code handles all academic extraction.
Return a single JSON object with exactly the keys listed below. Use only the
allowed enum values. If a value cannot be determined, use "unclear" for enum
fields, false for booleans unless the artifact is visible, [] for arrays, and
null for unreadable free-text visual fields.

applicant_name_visible
  Allowed: yes | no | unclear
  Description: Whether the student's name is visually present. Return "no" when
               the expected identity area is blank, blacked out, covered, or redacted.

seal_type
  Allowed: embossed | stamped_ink | printed_flat | sticker_foil | absent | unclear
  Description: The physical nature of the institution seal, if present.

seal_quality
  Allowed: clear | degraded | pixelated | absent | unclear
  Description: The visual fidelity of the seal or logo.

seal_visible_text
  Value: string (any readable text from the seal or watermark), or null if not readable
  Description: Verbatim text visible in the institution seal or watermark impression.
               Return null if the seal contains no readable text or text is illegible.

security_features_present
  Value: JSON array containing zero or more of: watermark, micro_printing, hologram, serial_number
  Description: Physical security items visible on the document. Watermarks and micro-printing
               can be faint. If page quality, contrast, or scan artifacts make them uncertain,
               do not guess; prefer security_features_assessable = "no". Use [] only when you
               can confidently conclude no listed feature is visible.

security_features_assessable
  Allowed: yes | no
  Description: Whether the page quality permits a reliable assessment of security features.
               If watermark or micro-printing visibility is uncertain, return "no".
               If "no", security_features_present should be treated as unreliable.

registrar_block
  Value: a JSON object with the following sub-fields:
         {
           "detected": "yes" | "no" | "unclear",
           "location": "header" | "footer" | "margin" | "separate_page" | "embedded_in_seal" | "none",
           "page_number": <integer or null — page where the registrar block appears>,
           "name_text": <string or null — the actual printed registrar name, verbatim>,
           "title_text": <string or null — the actual printed registrar title, verbatim>,
           "signature_present": "yes" | "no" | "unclear",
           "signature_type": "handwritten" | "stamped" | "digital" | "facsimile" | "none" | "unclear",
           "contact_info_text": <string or null — institution address or phone near the block>
         }
  Description: Structured detection of the official registrar attestation block.
               If detected="no", set location="none" and all text fields to null.
               If detected="unclear", fill in sub-fields for anything partially visible.

print_technology
  Allowed: typewriter | dot_matrix | laser | inkjet | photocopy | unclear
  Description: The apparent machinery used to print the document text.

paper_size_format
  Allowed: us_letter | a4 | legal | custom_irregular | unclear
  Description: The dimensions and standard of the paper.

text_alignment
  Allowed: normal | misaligned | uneven_spacing | unclear
  Description: The consistency of text baselines and column edges across the page.
               "misaligned" = baselines or column edges are offset.
               "uneven_spacing" = irregular spacing between characters or words.

compressed_numbers_detected
  Value: boolean (true if any numbers appear squeezed or compressed to fit a space)
  Description: Whether numerals look horizontally compressed, indicating possible digit insertion.

mixed_fonts_detected
  Value: boolean (true if noticeably different fonts, sizes, or weights appear inconsistently)
  Description: Whether the document uses inconsistent typefaces suggesting inserted content.

correction_artifacts_present
  Value: boolean (true if correction fluid, erasures, or smudge marks are visible)
  Description: Whether physical tampering marks are detectable on the page.

obliteration_marks_detected
  Value: boolean (true if text appears crossed out, obliterated, or interrupted unexpectedly)
  Description: Whether text has been deliberately obscured without explanation.

mixed_ink_colors_in_field
  Value: boolean (true if the same field — e.g., grade column — shows different ink colors
         across entries)
  Description: Whether handwritten entries in a single field use noticeably different inks,
               suggesting some entries were added later.

printer_quality_consistency
  Allowed: consistent | inconsistent | unclear
  Description: Whether print density, sharpness, and quality are uniform across the page.
               "inconsistent" = blurry letters mixed with clear letters or uneven density.

document_provenance_appearance
  Allowed: original | color_copy | scan_artifacts_present | unclear
  Description: Visual indicators of how the document was reproduced.

suspected_alteration_fields
  Value: JSON array of strings (free-text field names or descriptions where alteration is suspected)
  Description: Any fields where the examiner suspects content was altered. Include descriptions
               of overlapping text, scattered fragments, clipped headers, or any other visual
               evidence of digital editing. Include applicant/student identity redaction if
               the name or student ID area is blacked out. Use [] if none.

identity_redaction_detected
  Value: boolean (true if applicant/student identity data is visibly redacted, blacked out,
         covered, or removed from the transcript header)
  Description: Whether the transcript appears to have hidden applicant identity information.

overlapping_text_detected
  Value: boolean (true if text fragments overlap, are layered on top of each other, or appear
         duplicated at unexpected positions on the page)
  Description: Whether the page shows signs of digital manipulation such as copy-pasted text
               layers, scattered data fragments outside of table structures, or text rendered
               at positions inconsistent with the document layout. This is a primary indicator
               of Photoshop or PDF-editor tampering.
"""


def build_extraction_prompt(textract_context: dict | None = None) -> tuple[str, str]:
    """Return the prompt pair used for one page image."""
    if not textract_context:
        return _SYSTEM_PROMPT, _USER_PROMPT

    import json

    textract_payload = json.dumps(textract_context, ensure_ascii=True, default=str)
    return (
        _SYSTEM_PROMPT,
        _USER_PROMPT
        + "\n\n=== TEXTRACT_CONTEXT_JSON ===\n"
        + textract_payload
        + "\n=== END_TEXTRACT_CONTEXT_JSON ===\n",
    )


_TEXTRACT_STRUCTURING_SYSTEM_PROMPT = """\
You are a transcript data structuring assistant for the Mississippi State Board
of Nursing (MSBN). Your task is to interpret Amazon Textract output only.

Do NOT use page-image visual reasoning. Do NOT infer values from general
knowledge. Do NOT create or repair values that are not present in the supplied
TEXTRACT_CONTEXT_JSON. Textract text, tables, forms, queries, and layout lines
are the only authoritative evidence.

Return valid JSON only. No markdown fences, preamble, or explanation. Return a
single JSON object starting with "{" and ending with "}".

Each returned field must follow this format:
  "<field_name>": {
    "value": <scalar, boolean, array, object, or null>,
    "confidence": "high" | "medium" | "low",
    "source_location": {
      "page_number": 1,
      "text_spans": ["exact Textract line, table row, or form text used"]
    }
  }

Every source_location.text_spans item must be copied from the Textract context
or be an exact concatenation of cells from one Textract table row. If the
evidence is ambiguous, omit the field instead of guessing.
"""


_TEXTRACT_STRUCTURING_USER_PROMPT = """\
Use TEXTRACT_CONTEXT_JSON to structure academic transcript data. Return only
fields that are directly supported by the Textract evidence.

Allowed fields:

courses
  Value: array of course objects. Each course object may contain:
         {
           "code": <course code string or null>,
           "course_code": <same as code when available>,
           "name": <course title/name string>,
           "course_title": <course title/name string or null>,
           "credit_hours": <number or null>,
           "grade": <grade string or null>,
           "grade_points": <number or null>,
           "semester": <integer term order or null>,
           "start_date": <string or null>,
           "end_date": <string or null>,
           "retake_marker": <boolean>,
           "transfer_marker": <boolean>,
           "source_location": {
             "page_number": <integer>,
             "text_spans": ["exact Textract row text used for this course"]
           }
         }
  Rules: Extract only rows that clearly represent courses. Do not include GPA,
         totals, headers, or grading scale rows as courses.

semesters
  Value: array of semester/term objects. Each object may contain:
         {
           "term": <term label string>,
           "term_type": "fall" | "spring" | "summer" | "winter" | null,
           "start_date": <string or null>,
           "end_date": <string or null>,
           "courses": [<course code or title strings>],
           "term_gpa_stated": <number or null>,
           "term_credit_hours_stated": <number or null>,
           "cum_gpa_stated_after_term": <number or null>,
           "cum_credit_hours_stated": <number or null>,
           "cum_quality_points_stated": <number or null>,
           "source_location": {
             "page_number": <integer>,
             "text_spans": ["exact Textract line/table row used"]
           }
         }

final_cum_gpa_stated
  Value: number. The final cumulative/overall/career GPA stated on this page.

total_credit_hours_stated
  Value: number. The explicitly stated total earned/attempted/completed credit hours.

total_credit_hours
  Value: number. Same as total_credit_hours_stated when the transcript states a
         total; otherwise omit and let deterministic code compute it.

total_quality_points_stated
  Value: number. The explicitly stated cumulative/total quality points.

program_type
  Allowed: ms_practical_nursing | other | unclear
  Value: Use ms_practical_nursing only when Practical Nursing/LPN wording or PN/PNV
         course evidence is present.

claimed_degree_type
  Allowed: LPN | ADN | BSN | ABSN | RN-BSN | LPN-RN | MSN | DNP | CRNA | unclear
  Value: Nursing degree/certificate/credential type stated in Textract text.

grading_scale_format
  Allowed: letter_grade_us | percentage | 20_point_french | 5_point_russian |
           pass_fail | mixed | unclear

grading_scale_maximum
  Value: number, such as 4.0 or 100, only when stated or clearly implied by a
         printed grading scale.

degree_conferral_statement_present
  Value: boolean true only when Textract text states a degree/certificate/diploma
         was conferred, awarded, earned, completed, or granted. Omit when absent.

If deterministic parsing and this interpretation might disagree, still return
the Textract-supported value with exact evidence; downstream reconciliation will
decide whether to accept it.
"""


def build_textract_structuring_prompt(textract_context: dict) -> tuple[str, str]:
    """Return the prompt pair used for Textract-only academic structuring."""
    import json

    textract_payload = json.dumps(textract_context, ensure_ascii=True, default=str)
    return (
        _TEXTRACT_STRUCTURING_SYSTEM_PROMPT,
        _TEXTRACT_STRUCTURING_USER_PROMPT
        + "\n\n=== TEXTRACT_CONTEXT_JSON ===\n"
        + textract_payload
        + "\n=== END_TEXTRACT_CONTEXT_JSON ===\n",
    )

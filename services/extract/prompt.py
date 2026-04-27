"""Prompt text and enum vocabulary for transcript extraction.

The prompt is the single contract between the vision model and the rule
engine. Every field declared here is consumed by at least one rule in
services/rule_engine/rules/. Dead fields have been removed; redundant
aliases have been collapsed (the aggregator handles the remaining
course_code → code and total_credit_hours_stated → total_credit_hours
mappings).
"""

PROMPT_VERSION = "5.0"

# Enum values the handler accepts from the extraction model.
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
    "text_alignment": {"normal", "misaligned", "uneven_spacing", "unclear"},
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
    "dates_chronology_ok": {"yes", "no", "unclear"},
    "claimed_degree_type": {
        "LPN", "ADN", "BSN", "ABSN", "RN-BSN", "LPN-RN",
        "MSN", "DNP", "CRNA", "unclear",
    },
    # MS-specific program classification.
    "program_type": {"ms_practical_nursing", "other", "unclear"},
    # Confidence appears beside every extracted field.
    "_confidence": {"high", "medium", "low"},
}

# System prompt: response shape and output constraints.

_SYSTEM_PROMPT = """\
You are a forensic document examiner assisting the Mississippi State Board of \
Nursing (MSBN) in verifying nursing school transcripts for licensure eligibility. \
Your task is to extract structured fields from a single transcript page image.

TAMPERING AWARENESS:
Before extracting data, visually scan the entire page for signs of digital \
manipulation. Look for:
- Overlapping or layered text (text rendered on top of other text at different \
positions, a hallmark of Photoshop or PDF-editor tampering).
- Scattered data fragments — student names, ID numbers, dates, or numbers \
placed outside of the normal table or header structure.
- Clipped or truncated headers, institution names, or logos.
- Inconsistent text density, font rendering, or baseline alignment between \
different regions of the page.
If you observe ANY of these indicators, set overlapping_text_detected to true \
and list the affected areas in suspected_alteration_fields. Do NOT treat orphan \
text fragments (numbers, names, or dates floating outside a table row) as \
course data, credit hours, or grades.

OUTPUT FORMAT:
Return a single valid JSON object. No markdown fences, preamble, or explanation.
Your response must begin with "{".

FIELD FORMAT:
Return every requested field in this structure:

  "<field_name>": {
    "value": <extracted value — see typing rules below>,
    "confidence": "high" | "medium" | "low",
    "source_location": {
      "page_number": 1,
      "text_spans": ["verbatim text from the document that led to this extraction"]
    }
  }

Typing rules for "value":
- Enum fields: a single string from the allowed set, or "unclear" if undetermined.
- Free-text / date / number fields: the extracted value, or null if undetermined.
- Boolean fields: literal true or false (never a string, never null).
- String-array fields (security_features_present, suspected_alteration_fields): \
a JSON array of strings; [] if nothing is found.
- Object-array fields (programs, courses, semesters, leave_of_absence_markers): \
a JSON array of objects with the sub-fields specified per field; [] if none found.
- Object fields (registrar_block): a JSON object with the sub-fields specified per \
field; populate every sub-field, using null / "unclear" / "none" for unknown sub-values.

EXTRACTION FAILURE RULES (when a value cannot be determined from this page):
- Enum fields → "unclear".
- Free-text / date / number fields → null.
- Array fields → [].
- Boolean fields → false. Set true only when you are confident the indicator is \
present; never set true on suspicion alone.
- Object fields → return the object with each sub-field defaulted as above.
- confidence → "low" whenever the value is defaulted or inferred indirectly.
- source_location may be omitted for visual-judgement fields with no locatable \
text span (text_alignment, print_technology, printer_quality_consistency, \
overlapping_text_detected, suspected_alteration_fields, mixed_fonts_detected, \
compressed_numbers_detected, correction_artifacts_present, \
obliteration_marks_detected, mixed_ink_colors_in_field).

ENUM DISCIPLINE:
Use ONLY the allowed enum values listed in the extraction request. If you cannot \
determine a value from this page, use "unclear". Do not invent values outside \
the allowed set.

CONFIDENCE:
"high" when the text is unambiguous and directly readable. "medium" when inferred \
from context (e.g., grade computed from points). "low" when the page quality is \
poor, the value is defaulted, or you are guessing.
"""

# User prompt: extraction fields and allowed values.

_USER_PROMPT = """\
Extract all fields below from the attached transcript page image.
Return a single JSON object with exactly the keys listed.

Apply the FIELD FORMAT, ENUM DISCIPLINE, and EXTRACTION FAILURE RULES from the \
system prompt to every field. Use only the allowed enum values. If a value \
cannot be determined from this page, use the documented default for that field.
Return valid JSON only — no markdown fences, no preamble, no explanation.

=== SECTION 0: Transcript Identity ===

applicant_name
  Type: string | null (default null)
  Description: Student/applicant name printed on the transcript. Prefer the most
               complete legal name. Do not infer from filenames or surrounding
               context.

institution
  Type: string | null (default null)
  Description: School, college, university, or nursing program name that issued
               the transcript. Used by PHYS_001 to compare against seal text.

country
  Type: string | null (default null)
  Description: Country of issue or country of study, taken from the institution
               address or transcript body. Do not infer from institution name alone.

license_number
  Type: string | null (default null)
  Description: Applicant license, student, registration, or candidate number, if
               printed.

program_year
  Type: string | null (default null)
  Description: Graduation year, completion year, or program year printed on the
               transcript.

=== SECTION 1: Physical Document Fields ===

--- PHYS_001: Seal and Security ---

seal_type
  Allowed: embossed | stamped_ink | printed_flat | sticker_foil | absent | unclear
  Description: Physical nature of the institution seal, if present.

seal_quality
  Allowed: clear | degraded | pixelated | absent | unclear
  Description: Visual fidelity of the seal or logo.

seal_visible_text
  Type: string | null (default null)
  Description: Verbatim text visible inside the institution seal or watermark
               impression. null if the seal contains no readable text or text is
               illegible.

security_features_present
  Type: array of strings; allowed items: watermark | micro_printing | hologram | serial_number
  Default: []
  Description: Physical security items visible on the document. Watermarks and
               micro-printing can be faint. If page quality, contrast, or scan
               artifacts make them uncertain, do not guess — instead set
               security_features_assessable = "no" and leave this array empty.

security_features_assessable
  Allowed: yes | no  (default "no" if undetermined — do NOT use "unclear" here)
  Description: Whether the page quality permits a reliable assessment of security
               features. If watermark or micro-printing visibility is uncertain,
               return "no". When "no", the rule engine treats
               security_features_present as unreliable.

--- PHYS_002: Registrar Attestation ---

EXTRACTION GUIDANCE FOR REGISTRAR BLOCK:
The registrar block is most often in the FOOTER of the last page. It may also
appear in the header, near the institutional seal, or on a separate certification
page. Look for:
- Handwritten signatures (cursive scrawl, often in blue or black ink)
- Printed or typed names below or above a signature line
- Titles such as: "Registrar", "University Registrar", "Director of Admissions
  and Records", "Director of Records", "Registrar of Academic Records"
- Institution contact information (address, phone) near the signature block
A signature without a printed name is still a signature — extract what you see.
If you see ANY of: a name, a signature, a title, or institution contact info →
set detected="yes" and fill in the sub-fields you can determine.
Only set detected="no" if you have actively scanned the header, footer, and
margins and found nothing resembling an official registrar attestation.
When uncertain, prefer detected="unclear" over detected="no".

registrar_block
  Type: object (always returned, populate every sub-field)
  Sub-fields:
    detected:           "yes" | "no" | "unclear"          (default "unclear")
    location:           "header" | "footer" | "margin" | "separate_page"
                        | "embedded_in_seal" | "none"     (default "none")
    page_number:        integer | null                    (default null)
    name_text:          string | null                     (default null)
    title_text:         string | null                     (default null)
    signature_present:  "yes" | "no" | "unclear"          (default "unclear")
    signature_type:     "handwritten" | "stamped" | "digital" | "facsimile"
                        | "none" | "unclear"              (default "unclear")
    contact_info_text:  string | null                     (default null)
  Description: Structured detection of the official registrar attestation block.
               If detected="no", set location="none" and all text sub-fields to
               null. If detected="unclear", fill in any partially visible
               sub-fields and leave the rest at their defaults.

--- PHYS_003: Print Technology ---

print_technology
  Allowed: typewriter | dot_matrix | laser | inkjet | photocopy | unclear
  Description: Apparent machinery used to print the document text.

reissue_markers_detected
  Type: boolean (default false)
  Description: true only if explicit reissue language is present ("reissued",
               "certified copy", "duplicate", or similar). A reissued transcript
               may legitimately use newer print technology than its original
               issue date would suggest.

document_issue_date
  Type: date string in YYYY-MM-DD format | null (default null)
  Description: Date this transcript was issued or certified, as printed on the
               document. Look for "Date Issued", "Issue Date", "Certified", or
               similar labels.

--- PHYS_004: Text and Print Integrity ---

text_alignment
  Allowed: normal | misaligned | uneven_spacing | unclear
  Description: Consistency of text baselines and column edges across the page.
               "misaligned" = baselines or column edges are offset.
               "uneven_spacing" = irregular spacing between characters or words.

compressed_numbers_detected
  Type: boolean (default false)
  Description: true only if numerals visibly look horizontally compressed or
               squeezed, indicating possible digit insertion into a fixed-width
               field.

mixed_fonts_detected
  Type: boolean (default false)
  Description: true only if noticeably different fonts, sizes, or weights appear
               inconsistently across the page (suggesting inserted content).

correction_artifacts_present
  Type: boolean (default false)
  Description: true only if correction fluid, erasures, or smudge marks are
               visible.

obliteration_marks_detected
  Type: boolean (default false)
  Description: true only if text appears crossed out, obliterated, or
               interrupted unexpectedly.

mixed_ink_colors_in_field
  Type: boolean (default false)
  Description: true only if the same field (e.g., the grade column) shows
               noticeably different ink colors across entries, suggesting some
               entries were added later.

printer_quality_consistency
  Allowed: consistent | inconsistent | unclear
  Description: Whether print density, sharpness, and quality are uniform across
               the page. "inconsistent" = blurry letters mixed with clear letters
               or uneven density.

overlapping_text_detected
  Type: boolean (default false)
  Description: true only if text fragments overlap, are layered on top of each
               other, or appear duplicated at unexpected positions on the page.
               This is a primary indicator of Photoshop or PDF-editor tampering.

suspected_alteration_fields
  Type: array of strings (default [])
  Description: Free-text descriptions of any fields or regions where alteration
               is suspected — overlapping text, scattered fragments, clipped
               headers, or any other visual evidence of digital editing.

--- PHYS_005: Document Completeness ---

degree_conferral_statement_present
  Type: boolean (default false)
  Description: true if the page contains an explicit degree, certificate, or
               credential conferral statement. Examples: "Student has completed
               requirements for [degree]", "Degrees Earned: BSN", "Awarded:
               Associate Degree in Nursing", "Credential: CC - Career
               Certificate", "Certificate Awarded", "Program Completed",
               "Diploma Awarded", or any section labeled "Credential", "Degree",
               or "Certificate" that names a specific award. Includes community
               college career certificates and LPN/PN program completion
               statements.

degree_conferred_date
  Type: date string in YYYY-MM-DD format | null (default null)
  Description: Specific date on which the degree was conferred, if stated.

=== SECTION 2: Academic Content ===

--- Shared structured arrays (consumed by CONT_001 – CONT_004) ---

date_of_birth
  Type: date string in YYYY-MM-DD format | null (default null)
  Description: Applicant date of birth if printed on this transcript.

programs
  Type: array of objects (default [])
  Object sub-fields:
    name:                string | null
    start_date:          date string YYYY-MM-DD | null   (enrollment date)
    end_date:            date string YYYY-MM-DD | null   (graduation/completion date)
    claimed_degree_type: string | null
  Description: Each distinct degree program appearing on the transcript.

courses
  Type: array of objects (default [])
  Object sub-fields:
    course_code:      string | null  (course code exactly as printed,
                                      e.g. "PNV 1116", "BIO 2514")
    course_title:     string | null  (course name as printed)
    credit_hours:     number | null
    grade:            string | null  (letter or pass/fail grade as printed,
                                      e.g. "A", "B+", "Pass")
    grade_points:     number | null  (numeric GPA equivalent, e.g. A=4.0,
                                      B+=3.3; null for Pass/Fail or
                                      non-numeric grades)
    semester:         integer | null (sequential semester number — see rule
                                      below)
    start_date:       date string YYYY-MM-DD | null
    end_date:         date string YYYY-MM-DD | null
    retake_marker:    boolean (default false; true if marked as repeat,
                               retake, ADJ adjustment, or grade replacement)
    transfer_marker:  boolean (default false; true if marked TR, TRANSFER,
                               or CREDIT AWARDED)
  Semester numbering: if the transcript groups courses under "Semester 1",
    "Semester 2", etc., use those numbers. If it uses "Fall 2023", "Spring
    2024", assign ordinals by date order starting from 1. Use null only if
    semester cannot be determined.

  IMPORTANT: Only extract courses from structured table rows that have a
  clear course code, title, and grade/credit in the same row. Do NOT treat
  isolated numbers, scattered text fragments, or data floating outside the
  table structure as course entries or credit hour values. If the page shows
  signs of tampering (overlapping text, scattered fragments), extract only
  from the visually coherent table rows and ignore orphan data.

semesters
  Type: array of objects (default [])
  Object sub-fields:
    term:                       string | null  (e.g., "Fall 2020")
    term_type:                  "fall" | "spring" | "summer" | "winter" | null
    start_date:                 date string YYYY-MM-DD | null
    end_date:                   date string YYYY-MM-DD | null
    courses:                    array of strings — course codes or titles in
                                this term (must match course_code or
                                course_title in the courses array). Default [].
    term_gpa_stated:            number | null
    term_credit_hours_stated:   number | null
    cum_gpa_stated_after_term:  number | null
  Description: Each academic term/semester block found on this page.

leave_of_absence_markers
  Type: array of objects (default [])
  Object sub-fields:
    start_date:  date string YYYY-MM-DD | null
    end_date:    date string YYYY-MM-DD | null
    reason:      string | null
  Description: Any leave of absence, withdrawal, or academic stop-out periods
               noted on the transcript.

--- CONT_001: Date Chronology ---

dates_chronology_ok
  Allowed: yes | no | unclear
  Description: Whether the chronology of enrollment, coursework, and graduation
               is coherent on this page. The structured rule checks run first;
               this field is an advisory fallback when no specific structural
               anomaly is detected.

--- CONT_002: GPA Arithmetic ---

final_cum_gpa_stated
  Type: number | null (default null)
  Description: Final cumulative GPA printed at the bottom or end of the
               transcript. Typically labeled "Cumulative GPA", "Overall GPA",
               or "CGPA".

grading_scale_maximum
  Type: number | null (default null)
  Description: Ceiling of the grading scale in use (e.g., 4.0 or 4.3). Default
               assumption is 4.0 for US transcripts unless another maximum is
               explicitly stated; if stated, return that value.

grading_scale_format
  Allowed: letter_grade_us | percentage | 20_point_french | 5_point_russian | pass_fail | mixed | unclear
  Description: Grading standard used for course grades on this page.

--- CONT_003: Program Duration ---

claimed_degree_type
  Allowed: LPN | ADN | BSN | ABSN | RN-BSN | LPN-RN | MSN | DNP | CRNA | unclear
  Description: Nursing degree or credential this transcript is for.

total_credit_hours_stated
  Type: number | null (default null)
  Description: Total program credit hours printed on the transcript (e.g.,
               "Total: 68 hours", "Total Credits: 44"). The aggregator aliases
               this to total_credit_hours for PROG_003, so do not emit a
               separate total_credit_hours field.

=== SECTION 3: Mississippi Practical Nursing Program ===

program_type
  Allowed: ms_practical_nursing | other | unclear
  Description: Whether this transcript belongs to a Mississippi Practical
               Nursing (PN) program. Return "ms_practical_nursing" when the
               transcript shows PNV course codes (e.g. PNV 1116, PNV 1213),
               mentions the Mississippi Community College Board, or explicitly
               identifies a Practical Nursing or Licensed Practical Nurse (LPN)
               program at a Mississippi institution. Return "other" for all
               non-PN programs. Return "unclear" when insufficient evidence
               exists. PROG_001 – PROG_004 only run when this is
               "ms_practical_nursing".
"""


def build_extraction_prompt() -> tuple[str, str]:
    """Return the prompt pair used for one page image."""
    return _SYSTEM_PROMPT, _USER_PROMPT

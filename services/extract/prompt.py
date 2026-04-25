"""Prompt text and enum vocabulary for transcript extraction."""

PROMPT_VERSION = "2.0"

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
    "security_features_present": {
        "watermark", "micro_printing", "hologram", "serial_number",
    },
    "security_features_assessable": {"yes", "no"},
    "printer_quality_consistency": {"consistent", "inconsistent", "unclear"},
    # Academic content fields — kept for PROG_002 corroboration signal and
    # aggregate handler _ARRAY_FIELDS (suspicious_course_names) and
    # PROG_002 (program_duration_consistency, dates_chronology_ok).
    "grading_scale_format": {
        "letter_grade_us", "percentage", "20_point_french",
        "5_point_russian", "pass_fail", "mixed", "unclear",
    },
    "language_of_issue": {"english", "french", "spanish", "other", "unclear"},
    # suspicious_course_names is still merged by services/aggregate/handler.py
    # _ARRAY_FIELDS — do NOT remove until that handler is updated.
    "suspicious_course_names": set(),   # free-text strings; no controlled vocab
    "dates_chronology_ok": {"yes", "no", "unclear"},
    "dates_chronology_issue": {
        "none", "overlap", "gap",
        "enrollment_implausibly_early", "enrollment_implausibly_late", "other",
    },
    # program_duration_consistency is still consumed by check_prog_002 in program.py
    # — do NOT remove until that rule is updated.
    "program_duration_consistency": {
        "consistent_with_degree", "unusually_short", "unusually_long", "unclear",
    },
    # New content control vocab for CONT_003.
    "claimed_degree_type": {
        "LPN", "ADN", "BSN", "ABSN", "RN-BSN", "LPN-RN",
        "MSN", "DNP", "CRNA", "unclear",
    },
    # Program and institution fields.
    "diploma_mill_language_detected": {"yes", "no", "possible"},
    "institution_address_present": {"yes", "no", "unclear"},
    "institution_phone_present": {"yes", "no", "unclear"},
    "institution_website_present": {"yes", "no", "unclear"},
    "graduation_confirmation_present": {"yes", "no", "unclear"},
    "required_nursing_domains_present": {
        "adult_med_surg", "obstetrics", "pediatrics",
        "psychiatric", "gerontology", "community_health",
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

CRITICAL OUTPUT RULES:
- Return valid JSON only.
- No markdown fences.
- No preamble.
- No explanation.
- The entire response must be a single JSON object starting with "{" and ending \
with "}".

FIELD FORMAT:
Return every requested field in this structure:

  "<field_name>": {
    "value": <extracted value — enum string, free string, boolean, number, or array>,
    "confidence": "high" | "medium" | "low",
    "source_location": {
      "page_number": 1,
      "text_spans": ["verbatim text from the document that led to this extraction"]
    }
  }

Rules:
- For array-valued fields (security_features_present, suspicious_course_names, \
diploma_mill_phrases_found, required_nursing_domains_present, seal_present_on_pages, \
print_technology_per_page, suspected_alteration_fields), "value" MUST be a JSON array. \
Use an empty array [] if nothing is found. Do not use null.
- For object-array fields (courses, semesters, programs, registrar_signature_instances, \
leave_of_absence_markers), "value" MUST be a JSON array of objects. Use [] if none found.
- For boolean fields, "value" must be true or false (JSON boolean, not a string).
- For fields derived from the overall page with no single locatable text span \
(e.g., text_alignment, document_provenance_appearance, print_technology), \
"source_location" may be omitted.
- For "accreditation_claim_location", the value is an object, not a string. \
Return it as:
    "accreditation_claim_location": {
      "value": {"page_number": 1, "text_spans": ["..."]},
      "confidence": "high"
    }
  If accreditation_claim is null/absent, set accreditation_claim_location value to null.
- Use ONLY the allowed enum values listed in the extraction request. If you cannot \
determine a value from this page, use "unclear". Do not invent values outside the \
allowed set.
- confidence reflects your certainty: "high" when the text is unambiguous, \
"medium" when inferred, "low" when the page quality or content is poor.
"""

# User prompt: extraction fields and allowed values.

_USER_PROMPT = """\
Extract all fields below from the attached transcript page image.
Return a single JSON object with exactly the keys listed. Use only the allowed \
enum values. If a value cannot be determined from this page, use "unclear" for \
enum fields, null for free-text/date/number fields, and [] for array fields.
Return valid JSON only — no markdown fences, no preamble, no explanation.

=== SECTION 0: Transcript Identity Fields ===

applicant_name
  Value: free text string extracted from the transcript, or null if absent
  Description: The student/applicant name printed on the transcript. Prefer the most complete
               legal name. Do not infer from filenames or surrounding context.

institution
  Value: free text string extracted from the transcript, or null if absent
  Description: The school, college, university, or nursing program name that issued the transcript.

country
  Value: free text country name extracted from the transcript, or null if absent
  Description: Country of issue or country of study. Use the country explicitly printed in the
               institution address or transcript body. Do not infer from institution name alone.

license_number
  Value: free text license, student, registration, or candidate number, or null if absent
  Description: Identifier printed for the applicant if present.

program_year
  Value: free text graduation/completion/program year, or null if absent
  Description: The graduation year, completion year, or program year printed on the transcript.

document_page_count
  Value: integer (total number of pages in this document), or null if not determinable
  Description: The total page count of the entire document (e.g., from "Page 1 of 3" notation
               or physical count). Used to verify that institution seals appear on all pages.

=== SECTION 1: Physical Document Fields (PHYS_001 – PHYS_005) ===

--- PHYS_001: Seal Authenticity ---

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

seal_present_on_pages
  Value: JSON array of integers (page numbers where the institution seal is visible)
  Description: List every page number on which a seal or watermark is clearly visible.
               Use [] if the seal is not visible on any page of this document.

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

--- PHYS_002: Registrar Information ---

registrar_name_present
  Value: boolean (true if a printed registrar name appears, false if absent)
  Description: Whether a registrar name is printed on this page.

registrar_signature_present
  Value: boolean (true if a registrar signature is present — handwritten, stamped, or digital)
  Description: Whether a registrar signature of any type appears on this page.

registrar_title_present
  Value: boolean (true if a registrar title appears — e.g., "Registrar", "University Registrar",
         "Director of Admissions and Records")
  Description: Whether an official registrar title is printed on this page.

institution_contact_info_present
  Value: boolean (true if institution address OR phone number appears)
  Description: Whether any institution contact information (street address or phone) is present.

registrar_signature_instances
  Value: JSON array of objects, each with:
         { "page": <integer>, "type": "handwritten" | "stamped" | "digital",
           "appears_consistent": <boolean — true if this instance looks the same as others> }
  Description: One entry per distinct registrar signature instance found on this page.
               "appears_consistent" should be false only when the signature looks meaningfully
               different from other instances (suggesting different hands). Use [] if no
               signature is present.

--- PHYS_003: Print Technology ---

print_technology
  Allowed: typewriter | dot_matrix | laser | inkjet | photocopy | unclear
  Description: The apparent machinery used to print the document text.

print_technology_per_page
  Value: JSON array of strings (one print_technology enum value per page of the document,
         in page order). Use the same allowed values as print_technology.
  Description: Per-page print technology assessment. A single-page document returns a
               one-element array. Use "unclear" for pages that cannot be assessed.

reissue_markers_detected
  Value: boolean (true if the document contains "reissued", "certified copy", "duplicate",
         or similar language indicating this is an officially reissued transcript)
  Description: Whether explicit reissue language is present. A reissued transcript may
               legitimately use different print technology than the original.

document_issue_date
  Value: date string in YYYY-MM-DD format, or null if not found
  Description: The date this transcript was issued or certified, as printed on the document.
               Look for "Date Issued", "Issue Date", "Certified", or similar labels.

--- PHYS_004: Text and Print Integrity ---

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
  Description: Any fields where the examiner suspects content was altered. Use [] if none.

--- PHYS_005: Document Completeness ---

degree_conferral_statement_present
  Value: boolean (true if a degree conferral statement appears — e.g., "Student has completed
         requirements for [degree]", "Degrees Earned: BSN", "Awarded: Associate Degree in Nursing")
  Description: Whether this page contains an explicit statement that the degree was conferred.

degree_conferred_date
  Value: date string in YYYY-MM-DD format, or null if not found
  Description: The specific date on which the degree was conferred, if stated.

=== SECTION 2: Content Fields (CONT_001 – CONT_004) ===

--- CONT_001 – CONT_004: Shared Structured Data ---

date_of_birth
  Value: date string in YYYY-MM-DD format, or null if not found
  Description: The applicant date of birth if printed on this transcript.

programs
  Value: JSON array of objects, each with:
         { "name": <string>, "start_date": <YYYY-MM-DD or null>,
           "end_date": <YYYY-MM-DD or null>, "claimed_degree_type": <string or null> }
  Description: Each distinct degree program appearing in the transcript. start_date is the
               enrollment date, end_date is the graduation/completion date. Use [] if none found.

courses
  Value: JSON array of objects, each with:
         { "name": <string>, "code": <string or null>, "course_code": <string or null>,
           "course_title": <string or null>,
           "credit_hours": <number or null>, "grade": <string or null>,
           "grade_points": <number or null>,
           "semester": <integer or null>,
           "start_date": <YYYY-MM-DD or null>, "end_date": <YYYY-MM-DD or null>,
           "retake_marker": <boolean — true if course is marked as a repeat/retake>,
           "transfer_marker": <boolean — true if marked TR, TRANSFER, or CREDIT AWARDED> }
  Description: Every course entry on this page.
               "code" is the course code exactly as printed (e.g. "PNV 1116", "BIO 2514").
               "course_code" is an alias — populate both with the same value.
               "grade" is the letter or pass/fail grade as printed (e.g. "A", "B+", "Pass").
               "grade_points" is the numeric GPA equivalent (e.g., A=4.0, B+=3.3).
               Use null for Pass/Fail or non-numeric grades.
               "semester" is the sequential semester number (1, 2, 3, etc.) this course
               appears in, derived from the transcript's semester/term grouping. If the
               transcript groups courses under "Semester 1", "Semester 2", etc., use those
               numbers. If it uses "Fall 2023", "Spring 2024", assign ordinals by date order
               starting from 1. Use null if semester cannot be determined.
               Use [] if no courses are found on this page.

semesters
  Value: JSON array of objects, each with:
         { "term": <string, e.g., "Fall 2020">, "term_type": "fall" | "spring" | "summer" | "winter",
           "start_date": <YYYY-MM-DD or null>, "end_date": <YYYY-MM-DD or null>,
           "courses": <array of course names or codes in this term>,
           "term_gpa_stated": <number or null>, "term_credit_hours_stated": <number or null>,
           "cum_gpa_stated_after_term": <number or null> }
  Description: Each academic term/semester block found on this page. start_date and end_date
               are the term start and end dates. Use [] if no semester structure is found.

leave_of_absence_markers
  Value: JSON array of objects, each with:
         { "start_date": <YYYY-MM-DD or null>, "end_date": <YYYY-MM-DD or null>,
           "reason": <string or null> }
  Description: Any leave of absence, withdrawal, or academic stop-out periods noted on the
               transcript. Use [] if none found.

--- CONT_001: Date and Chronology ---

dates_chronology_ok
  Allowed: yes | no | unclear
  Description: Whether the chronology of enrollment, coursework, and graduation is coherent.

dates_chronology_issue
  Allowed: none | overlap | gap | enrollment_implausibly_early | enrollment_implausibly_late | other
  Description: If dates_chronology_ok is "no", the specific issue. Use "none" otherwise.

--- CONT_002: GPA Arithmetic ---

final_cum_gpa_stated
  Value: number (the final cumulative GPA printed at the bottom or end of the transcript),
         or null if not found
  Description: The overall cumulative GPA as stated — typically labeled "Cumulative GPA",
               "Overall GPA", or "CGPA".

grading_scale_maximum
  Value: number (the maximum GPA value on the stated scale, e.g., 4.0 or 4.3)
  Description: The ceiling of the grading scale in use. Default assumption is 4.0 for US
               transcripts unless another maximum is explicitly stated.

--- CONT_003: Program Duration ---

claimed_degree_type
  Allowed: LPN | ADN | BSN | ABSN | RN-BSN | LPN-RN | MSN | DNP | CRNA | unclear
  Description: The nursing degree or credential this transcript is for.

total_credit_hours_stated
  Value: number (total credit hours as stated on the transcript), or null if not found
  Description: The total program credit hours printed on the transcript (e.g., "Total: 68 hours").

=== SECTION 3: Program and Institution Fields ===

grading_scale_format
  Allowed: letter_grade_us | percentage | 20_point_french | 5_point_russian | pass_fail | mixed | unclear
  Description: The standard used for course grades on this page.

language_of_issue
  Allowed: english | french | spanish | other | unclear
  Description: The primary language the document is written in.

accreditation_claim
  Value: free text string extracted verbatim, or null if absent
  Description: The claimed accrediting body as printed (e.g., "ACEN", "CCNE", "BOUA").
               The downstream rule engine compares this against an approved accreditor list.

accreditation_claim_location
  Value: object {"page_number": 1, "text_spans": ["..."]} or null if absent
  Description: Where on the page the accreditation claim appears. Null if accreditation_claim is null.
               Return as: {"value": {"page_number": 1, "text_spans": ["..."]}, "confidence": "high"}

diploma_mill_language_detected
  Allowed: yes | no | possible
  Description: Whether marketing language indicative of degree mills is present
               (e.g., "life experience credit", "no need to take exams", "all credits accepted").

diploma_mill_phrases_found
  Value: JSON array of strings (verbatim phrases)
  Description: Specific phrases found if diploma_mill_language_detected is "yes" or "possible".
               Use [] otherwise.

institution_address_present
  Allowed: yes | no | unclear
  Description: Whether a physical street address is listed for the institution.

institution_phone_present
  Allowed: yes | no | unclear
  Description: Whether a phone number is listed for the institution.

institution_website_present
  Allowed: yes | no | unclear
  Description: Whether a website URL is listed for the institution.

graduation_confirmation_present
  Allowed: yes | no | unclear
  Description: Whether this page contains a completion indicator such as a graduation date,
               "Grad Date", "Graduation Date", "Degrees Earned", degree/certificate awarded,
               diploma/certificate title, graduation term, or an explicit degree conferral
               statement. If any such indicator appears, return "yes".

required_nursing_domains_present
  Value: JSON array containing zero or more of:
         adult_med_surg, obstetrics, pediatrics, psychiatric, gerontology, community_health
  Description: The fundamental nursing domains visible in courses on this page.
               Include a domain only if courses on this page clearly belong to it.
               Use [] if no domains can be identified on this page.

suspicious_course_names
  Value: JSON array of strings (verbatim course names)
  Description: Specific course names that appear non-nursing or suspicious. Use [] if none.

program_duration_consistency
  Allowed: consistent_with_degree | unusually_short | unusually_long | unclear
  Description: The total elapsed time of the academic program relative to its degree type.

=== SECTION 3b: MS Practical Nursing Fields (PROG_004 – PROG_007) ===

program_type
  Allowed: ms_practical_nursing | other | unclear
  Description: Whether this transcript belongs to a Mississippi Practical Nursing (PN)
               program. Return "ms_practical_nursing" when the transcript shows PNV course
               codes (e.g. PNV 1116, PNV 1213), mentions the Mississippi Community College
               Board, or explicitly identifies a Practical Nursing or Licensed Practical Nurse
               (LPN) program at a Mississippi institution. Return "other" for all non-PN
               programs. Return "unclear" when insufficient evidence exists.

total_credit_hours
  Value: integer (sum of all credit hours across all courses on the transcript), or null
  Description: The total semester credit hours for the full program, either as printed on
               the transcript (e.g., "Total Credits: 44") or computed by summing all
               individual course credit hours. For MS Practical Nursing, the expected
               total is 44 semester hours.
"""


def build_extraction_prompt() -> tuple[str, str]:
    """Return the prompt pair used for one page image."""
    return _SYSTEM_PROMPT, _USER_PROMPT

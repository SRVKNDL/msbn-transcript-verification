"""Bedrock Nova extraction prompt for MSBN transcript pages.

build_extraction_prompt() returns (system_prompt, user_prompt) for a single
page extraction call.  The caller base64-encodes the page PNG and builds the
full messages array; this module owns only the text content of both prompts.

VOCABULARY maps field names to their allowed enum value sets.  The handler
uses this dict for post-response validation: unexpected values trigger a
WARNING log but do not crash the Lambda (advisory-only behaviour).

Array-valued fields (security_features_present, suspicious_course_names,
diploma_mill_phrases_found, required_nursing_domains_present) are validated
element-by-element.  Free-text and object fields (accreditation_claim,
accreditation_claim_location) are not in VOCABULARY; no enum check is run.

The special key "_confidence" holds the allowed values for the confidence
metadata field that wraps every extracted field.
"""

PROMPT_VERSION = "1.0"

# ---------------------------------------------------------------------------
# Controlled vocabulary — allowed enum values per field.
# ---------------------------------------------------------------------------

VOCABULARY: dict[str, set] = {
    # Section 1 — Physical document fields
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
    # Section 2 — Content fields
    "grading_scale_format": {
        "letter_grade_us", "percentage", "20_point_french",
        "5_point_russian", "pass_fail", "mixed", "unclear",
    },
    "language_of_issue": {"english", "french", "spanish", "other", "unclear"},
    "course_relevance": {
        "nursing_standard", "mixed_with_non_nursing",
        "predominantly_non_nursing", "unclear",
    },
    "duplicate_courses_detected": {"yes", "no", "unclear"},
    "gpa_arithmetic_consistency": {"consistent", "inconsistent", "unclear"},
    "dates_chronology_ok": {"yes", "no", "unclear"},
    "dates_chronology_issue": {
        "none", "overlap", "gap",
        "enrollment_implausibly_early", "enrollment_implausibly_late", "other",
    },
    "program_duration_consistency": {
        "consistent_with_degree", "unusually_short", "unusually_long", "unclear",
    },
    # Section 3 — Program/institution fields
    "diploma_mill_language_detected": {"yes", "no", "possible"},
    "institution_address_present": {"yes", "no", "unclear"},
    "institution_phone_present": {"yes", "no", "unclear"},
    "institution_website_present": {"yes", "no", "unclear"},
    "graduation_confirmation_present": {"yes", "no", "unclear"},
    "required_nursing_domains_present": {
        "adult_med_surg", "obstetrics", "pediatrics",
        "psychiatric", "gerontology", "community_health",
    },
    # Confidence level — validated on every field
    "_confidence": {"high", "medium", "low"},
}

# ---------------------------------------------------------------------------
# System prompt — output rules and field format
# ---------------------------------------------------------------------------

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
    "value": <extracted value — enum string, free string, or array>,
    "confidence": "high" | "medium" | "low",
    "source_location": {
      "page_number": 1,
      "text_spans": ["verbatim text from the document that led to this extraction"]
    }
  }

Rules:
- For array-valued fields (security_features_present, suspicious_course_names, \
diploma_mill_phrases_found, required_nursing_domains_present), "value" MUST be a \
JSON array. Use an empty array [] if nothing is found. Do not use null.
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

# ---------------------------------------------------------------------------
# User prompt — full field list with allowed values
# ---------------------------------------------------------------------------

_USER_PROMPT = """\
Extract all fields below from the attached transcript page image.
Return a single JSON object with exactly the keys listed. Use only the allowed \
enum values. If a value cannot be determined from this page, use "unclear".
Return valid JSON only — no markdown fences, no preamble, no explanation.

=== SECTION 1: Physical Document Fields ===

seal_type
  Allowed: embossed | stamped_ink | printed_flat | sticker_foil | absent | unclear
  Description: The physical nature of the institution seal, if present.

seal_quality
  Allowed: clear | degraded | pixelated | absent | unclear
  Description: The visual fidelity of the seal or logo.

print_technology
  Allowed: typewriter | dot_matrix | laser | inkjet | photocopy | unclear
  Description: The apparent machinery used to print the document text.

paper_size_format
  Allowed: us_letter | a4 | legal | custom_irregular | unclear
  Description: The dimensions and standard of the paper.

text_alignment
  Allowed: normal | misaligned | uneven_spacing | unclear
  Description: The consistency of text baselines and column edges across the page.

document_provenance_appearance
  Allowed: original | color_copy | scan_artifacts_present | unclear
  Description: Visual indicators of how the document was reproduced.

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

=== SECTION 2: Content Fields ===

grading_scale_format
  Allowed: letter_grade_us | percentage | 20_point_french | 5_point_russian | pass_fail | mixed | unclear
  Description: The standard used for course grades on this page.

language_of_issue
  Allowed: english | french | spanish | other | unclear
  Description: The primary language the document is written in.

course_relevance
  Allowed: nursing_standard | mixed_with_non_nursing | predominantly_non_nursing | unclear
  Description: The relevancy of listed courses to the nursing curriculum.

duplicate_courses_detected
  Allowed: yes | no | unclear
  Description: Whether duplicate or near-duplicate course entries appear on this page.

suspicious_course_names
  Value: JSON array of strings (verbatim course names)
  Description: Specific course names that appear non-nursing or suspicious. Use [] if none.

gpa_arithmetic_consistency
  Allowed: consistent | inconsistent | unclear
  Description: Whether the reported cumulative GPA matches individual grades.
               Use "unclear" when cumulative GPA and individual grades are on different pages.

dates_chronology_ok
  Allowed: yes | no | unclear
  Description: Whether the chronology of enrollment, coursework, and graduation is coherent.

dates_chronology_issue
  Allowed: none | overlap | gap | enrollment_implausibly_early | enrollment_implausibly_late | other
  Description: If dates_chronology_ok is "no", the specific issue. Use "none" otherwise.

program_duration_consistency
  Allowed: consistent_with_degree | unusually_short | unusually_long | unclear
  Description: The total elapsed time of the academic program relative to its degree type.

=== SECTION 3: Program and Institution Fields ===

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
"""


def build_extraction_prompt() -> tuple[str, str]:
    """Return ``(system_prompt, user_prompt)`` for a single page extraction call.

    Caller contract:
      1. Base64-encode the page PNG.
      2. Build the Nova messages body::

           {
             "schemaVersion": "messages-v1",
             "messages": [{
               "role": "user",
               "content": [
                 {"image": {"format": "png", "source": {"bytes": b64_image}}},
                 {"text": user_prompt},
               ],
             }],
             "system": [{"text": system_prompt}],
             "inferenceConfig": {"max_new_tokens": 4096, "temperature": 0.0},
           }

      3. Call ``bedrock-runtime invoke_model`` with that body.
    """
    return _SYSTEM_PROMPT, _USER_PROMPT

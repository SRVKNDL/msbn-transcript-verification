# Extraction Enum Vocabulary for the Bedrock Nova Prompt

This document defines the controlled vocabulary (enum values) that the Bedrock Nova Lite model must use when extracting data from transcript PDFs. These structured values ensure that the downstream Python rule engine evaluates fields predictably against the established fraud detection rules.

## Section 1 — Physical document fields (feeds `PHYS_` rules)

These fields capture the physical appearance and artifacts of the submitted document.

```yaml
# The physical nature of the institution seal, if present.
seal_type: embossed | stamped_ink | printed_flat | sticker_foil | absent | unclear

# The visual fidelity of the seal or logo.
seal_quality: clear | degraded | pixelated | absent | unclear

# The apparent machinery used to print the document text.
print_technology: typewriter | dot_matrix | laser | inkjet | photocopy | unclear

# The dimensions and standard of the paper.
paper_size_format: us_letter | a4 | legal | custom_irregular | unclear

# The consistency of text baselines and column edges.
text_alignment: normal | misaligned | uneven_spacing | unclear

# Visual indicators of how the document was reproduced.
document_provenance_appearance: original | color_copy | scan_artifacts_present | unclear

# Physical security items visible on the document. Empty array if none detected.
security_features_present: [watermark, micro_printing, hologram, serial_number]

# Whether the page quality permits a reliable assessment of security features.
# If "no", security_features_present should be treated as unreliable by the rule engine.
security_features_assessable: yes | no
```

## Section 2 — Content fields (feeds `CONT_` rules)

These fields evaluate the textual and semantic information contained in the document.

```yaml
# The standard used for course grades.
grading_scale_format: letter_grade_us | percentage | 20_point_french | 5_point_russian | pass_fail | mixed | unclear

# The primary language the document is written in (Examples: english, french, spanish, etc.)
language_of_issue: english | french | spanish | other | unclear

# The relevancy of listed courses to the nursing curriculum.
course_relevance: nursing_standard | mixed_with_non_nursing | predominantly_non_nursing | unclear

# Whether duplicate or near-duplicate course entries appear on the transcript.
duplicate_courses_detected: yes | no | unclear

# Array of specific course names that appear non-nursing or suspicious. Empty array if none.
# The dashboard uses this list to highlight offending entries for reviewers.
suspicious_course_names: [<string>, <string>, ...]

# Whether the reported cumulative GPA mathematically matches the sum/mean of individual grades.
# Note: for multi-page transcripts, Nova extracts raw grades per page and the Python
# aggregation step computes consistency. Nova should return "unclear" when individual
# grades and cumulative GPA are on different pages.
gpa_arithmetic_consistency: consistent | inconsistent | unclear

# Whether the chronology of enrollment, coursework, and graduation is coherent.
dates_chronology_ok: yes | no | unclear

# If dates_chronology_ok is "no", the specific issue. "none" otherwise.
dates_chronology_issue: none | overlap | gap | enrollment_implausibly_early | enrollment_implausibly_late | other

# The total elapsed time of the academic program.
program_duration_consistency: consistent_with_degree | unusually_short | unusually_long | unclear
```

## Section 3 — Program/institution fields (feeds `PROG_` rules)

These fields assess the institution's authenticity and educational requirements.

```yaml
# Free text extraction of the claimed accrediting body (e.g., "ACEN", "CCNE", "BOUA").
# The Python rule engine compares this string against a reference list of approved accreditors.
accreditation_claim: <string>

# Where on the page the accreditation claim appears, for source citation in the dashboard.
accreditation_claim_location: { page_number: int, text_spans: [str] }

# Detects marketing language indicative of degree mills (e.g., "life experience credit", "no need to take exams").
diploma_mill_language_detected: yes | no | possible

# If diploma_mill_language_detected is "yes" or "possible", the specific phrases Nova found.
# Empty array otherwise. The dashboard highlights these phrases for reviewers.
diploma_mill_phrases_found: [<string>, <string>, ...]

# Whether a physical street address is listed for the institution.
institution_address_present: yes | no | unclear

# Whether a phone number is listed for the institution.
institution_phone_present: yes | no | unclear

# Whether a website URL is listed for the institution.
institution_website_present: yes | no | unclear

# Explicit statements of degree conferral or graduation.
graduation_confirmation_present: yes | no | unclear

# The fundamental nursing domains present in the transcript.
# The rule engine computes missing domains as (required_domains - required_nursing_domains_present).
required_nursing_domains_present: [adult_med_surg, obstetrics, pediatrics, psychiatric, gerontology, community_health]
```

## Section 3b — Course-level fields (feeds `PROG_004`–`PROG_007` rules)

These fields are extracted per-course from the transcript. Nova should return an array of course objects for each page that contains coursework.

```yaml
# Array of course records extracted from the transcript.
# Each entry represents one row in a semester table.
courses:
  - code: <string>        # e.g. "PNV 1213", "PNV 1914", "BIO 2514"
    name: <string>        # e.g. "Body Structure and Function"
    credit_hours: <int>   # Semester credit hours listed on transcript
    semester: <int>       # Which semester (1, 2, 3, etc.) this course appears in
    grade: <string>       # Grade received (e.g. "A", "B", "Pass")
    source_location: { page_number: int, text_spans: [str] }

# The total credit hours reported on the transcript (usually on the summary page).
total_credit_hours: <int>

# Whether the transcript is for a Mississippi Practical Nursing program.
# Set to "ms_practical_nursing" when the institution is a MS community college
# and the program title matches "Practical Nursing" or "Licensed Practical/Vocational Nurse".
# The rule engine uses this to activate MS-curriculum-specific rules (PROG_004–007).
program_type: ms_practical_nursing | other | unclear
```

### Valid MS Practical Nursing course codes (2024 framework, CIP 51.3901)

Nova should recognize these PNV codes when extracting course data from Mississippi nursing transcripts:

| Code | Name | Credit Hours |
|------|------|-------------|
| PNV 1116 | Practical Nursing Foundations | 16 |
| PNV 1213 | Body Structure and Function | 3 |
| PNV 1216 | Intermediate Practical Nursing (FS) | 16 |
| PNV 1312 | Intermediate Practical Nursing (SS) | 12 |
| PNV 1412 | Advanced Practical Nursing | 12 |
| PNV 1426 | Fundamentals of Nursing Theory | 6 |
| PNV 1437 | Fundamentals of Nursing Lab/Clinical | 7 |
| PNV 1443 | Nursing Fundamentals and Clinical | 13 |
| PNV 1516 | Advanced Practical Nursing (SS) | 16 |
| PNV 1524 | IV Therapy & Pharmacology | 4 |
| PNV 1614 | Medical/Surgical Nursing Theory | 4 |
| PNV 1622 | Medical/Surgical Nursing Clinical | 2 |
| PNV 1634 | Alterations in Adult Health Theory | 4 |
| PNV 1642 | Alterations in Adult Health Clinical | 2 |
| PNV 1666 | Medical/Surgical Nursing Concepts & Clinical | 6 |
| PNV 1676 | Alterations in Adult Health Concepts & Clinical | 6 |
| PNV 1682 | Adult Health Nursing Concepts & Clinical | 12 |
| PNV 1714 | Maternal-Child Nursing | 4 |
| PNV 1728 | Specialty Areas in Nursing | 8 |
| PNV 1814 | Mental Health Nursing | 4 |
| PNV 1914 | Nursing Transition | 4 |

**BIO substitutions:** BIO 2514 (A&P I) and BIO 2524 (A&P II) may substitute for PNV 1213.

**Total program:** 44 semester hours, 980 clock hours (455 lecture, 180 lab, 345 clinical).

**Scheduling options:** Programs may be 1-semester (accelerated), 2-semester, 3-semester (most common), 4-semester, or 5-semester (part-time/weekend). Not all 22 courses appear on every transcript — different scheduling options use different course groupings.

## Section 4 — Cross-document fields (feeds `CROSS_` rules)

**Architectural note:** These fields are NOT extracted by the per-page Extract Lambda. The Extract Lambda only handles single-page extraction against one document at a time. Cross-document comparison runs in a separate aggregation step after all documents in an application have been extracted. This section is included here for completeness — the values Nova or the aggregation Lambda must return follow the same enum style as above.

```yaml
# Whether administrator signatures look identical across forms.
signature_match_across_documents: match | mismatch | insufficient_data

# Whether the institution title is consistent across forms.
institution_name_match: match | mismatch | insufficient_data

# Whether the student's name aligns across all records.
applicant_name_match: match | mismatch | insufficient_data

# Concordance of start/end dates across documents in the same application.
dates_match_across_documents: match | mismatch_greater_than_90_days | insufficient_data
```

## Section 5 — Confidence and metadata

For every field extracted in Sections 1–3, Nova must return these additional metadata points:

```yaml
# The model's certainty regarding the extracted value.
confidence: high | medium | low

# Tracing information mapping back to the PDF. text_spans is always an array, even for
# single-location citations (length 1), to keep the Python rule engine consistent.
# For page-level boolean fields (e.g., diploma_mill_language_detected), text_spans may
# contain multiple supporting phrases. If the field is derived from the whole page with
# no single citation (e.g., text_alignment), source_location may be omitted.
source_location: { page_number: int, text_spans: [str] }
```

## Section 6 — Resolved design decisions

The following decisions were made during vocabulary review and are reflected in the sections above:

1. **Cross-document evaluation.** `CROSS_*` rules do not run inside the Extract Lambda. A separate aggregation step between Extract and Validate will compare fields across documents in an application. The architecture plan will be updated to reflect this.

2. **Suspicious course string literals.** Nova returns the offending course names as a string array (`suspicious_course_names`) so the dashboard can highlight them directly for reviewers.

3. **Multi-page GPA arithmetic.** Nova extracts raw grades per page without computing arithmetic. The Python aggregation step calculates GPA consistency after all pages are extracted. Nova returns `unclear` for `gpa_arithmetic_consistency` when the cumulative GPA and individual grades appear on different pages.

4. **Security features as a clean array.** `security_features_present` is always a list of detected features (empty if none). A separate `security_features_assessable` boolean indicates whether page quality permits reliable assessment.

5. **Diploma mill phrase capture.** When `diploma_mill_language_detected` is `yes` or `possible`, Nova returns the specific phrases in `diploma_mill_phrases_found` for dashboard highlighting.

6. **Consistent array shape for source citations.** `text_spans` is always an array, even when citing a single location. This avoids union types in the Python rule engine.

## Section 7 — Open questions

1. **Minimum domain hour thresholds.** The NCSBN sample evaluation report lists specific clinical hour minimums (e.g., 700 hours adult medical). Should Nova extract hour counts per domain, or is `required_nursing_domains_present` as a boolean array enough for Phase 3? Hour extraction adds prompt complexity but enables more specific flags.

2. **Accreditation reference list source.** `accreditation_claim` is compared against a reference list in Python. Who owns the reference list (likely Bishal as Data Engineer), and what's the initial source? ACEN and CCNE directories are public; other accreditors (country-specific) need MSBN input.

3. **Confidence calibration.** Nova's self-reported `confidence` values may not align with actual reliability. Phase 3 testing against Bishal's synthetic corpus will reveal whether confidence thresholds need tuning before the rule engine weights them.

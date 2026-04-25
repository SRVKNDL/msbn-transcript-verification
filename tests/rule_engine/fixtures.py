"""Aggregation.json fixtures for rule engine tests.

CLEAN_BASELINE   — a well-formed application with no anomalies; fires ZERO flags.
FRAUD_CASE_B     — a transcript inspired by MSBN Case B (fabricated non-nursing courses)
                   combined with Case D diploma-mill signals and cross-document mismatches.
                   Expected to fire multiple flags.

Both fixtures follow the aggregation.json schema defined by the extraction
vocabulary (design/extraction-vocabulary.md) plus the additional context
fields the rule engine consumes.
"""

# ── Clean baseline (zero flags expected) ──────────────────────────────────────
CLEAN_BASELINE: dict = {
    "applicationId": "APP-CLEAN-001",
    # Physical section
    "seal_type": "embossed",
    "seal_type_source": {"page_number": 1, "text_spans": ["embossed seal top-right"]},
    "institution_expected_seal_type": "embossed",
    "seal_quality": "clear",
    "seal_quality_source": {"page_number": 1, "text_spans": ["institution logo and seal"]},
    "print_technology": "laser",
    "print_technology_source": {"page_number": 1, "text_spans": []},
    "issue_year": 2018,
    "text_alignment": "normal",
    "text_alignment_source": None,
    "document_provenance_appearance": "original",
    "document_provenance_appearance_source": None,
    "document_presented_as_original": True,
    "security_features_present": ["watermark", "serial_number"],
    "security_features_present_source": {"page_number": 1, "text_spans": []},
    "security_features_assessable": "yes",
    # Content section
    "grading_scale_format": "letter_grade_us",
    "grading_scale_format_source": {"page_number": 2, "text_spans": ["A, B+, B, A-"]},
    "language_of_issue": "english",
    "language_of_issue_source": {"page_number": 1, "text_spans": []},
    "country_of_study": "philippines",
    "declared_language_of_instruction": "english",
    "course_relevance": "nursing_standard",
    "course_relevance_source": {"page_number": 2, "text_spans": []},
    "duplicate_courses_detected": "no",
    "duplicate_courses_detected_source": None,
    "suspicious_course_names": [],
    "suspicious_course_names_source": None,
    "gpa_arithmetic_consistency": "consistent",
    "gpa_arithmetic_consistency_source": {
        "page_number": 2,
        "text_spans": ["Overall GPA: 3.50"],
    },
    "dates_chronology_ok": "yes",
    "dates_chronology_ok_source": None,
    "dates_chronology_issue": "none",
    "program_duration_consistency": "consistent_with_degree",
    "program_duration_consistency_source": None,
    # Program section
    "accreditation_claim": "ACEN",
    "accreditation_claim_source": {
        "page_number": 1,
        "text_spans": ["Accredited by ACEN"],
    },
    "diploma_mill_language_detected": "no",
    "diploma_mill_language_detected_source": None,
    "diploma_mill_phrases_found": [],
    "institution_address_present": "yes",
    "institution_address_present_source": {
        "page_number": 1,
        "text_spans": ["123 University Ave, Manila, Philippines"],
    },
    "institution_phone_present": "yes",
    "institution_phone_present_source": {
        "page_number": 1,
        "text_spans": ["+63 2 1234 5678"],
    },
    "institution_website_present": "yes",
    "graduation_confirmation_present": "yes",
    "graduation_confirmation_present_source": {
        "page_number": 3,
        "text_spans": [
            "Conferred degree: Bachelor of Science in Nursing, April 2018"
        ],
    },
    "required_nursing_domains_present": [
        "adult_med_surg",
        "obstetrics",
        "pediatrics",
        "psychiatric",
        "gerontology",
        "community_health",
    ],
    "required_nursing_domains_present_source": {"page_number": 2, "text_spans": []},
    # Cross-document section
    "applicant_name_match": "match",
    "applicant_name_match_source": None,
    "institution_name_match": "match",
    "institution_name_match_source": None,
    "dates_match_across_documents": "match",
    "dates_match_across_documents_source": None,
    "signature_match_across_documents": "match",
    "signature_match_across_documents_source": None,
}

# ── Fraud-laden fixture (Case B + diploma mill signals) ───────────────────────
# Inspired by MSBN Case B (fabricated non-nursing courses, duplicate entry)
# combined with Case D/E diploma mill signals and cross-document mismatches.
# Expected to fire (new rules):
#   PHYS_001 (x2): pixelated seal, no security features
#   PHYS_002 (x4): registrar name/signature/title/contact absent
#   PHYS_004 (x1): misaligned text
#   CONT_003 (x1): ADN program duration too short (5 months vs 18-month minimum)
#   PROG_001 (x2): diploma mill language + unknown accreditor
#   PROG_002 (x1): no graduation confirmation
#   PROG_003 (x4): missing all required nursing domains
#   CROSS_001–003 deferred to Phase 4
FRAUD_CASE_B: dict = {
    "applicationId": "APP-FRAUD-002",
    # Physical section — multiple problems
    "seal_type": "stamped_ink",
    "seal_type_source": {"page_number": 1, "text_spans": ["stamped seal bottom-right"]},
    "seal_quality": "pixelated",                    # PHYS_001 Check 2 fires
    "seal_quality_source": {"page_number": 1, "text_spans": ["institution logo region"]},
    "print_technology": "laser",
    "print_technology_source": {"page_number": 1, "text_spans": []},
    "issue_year": 2019,
    "text_alignment": "misaligned",                 # PHYS_004 Check 1 fires
    "text_alignment_source": {
        "page_number": 2,
        "text_spans": ["grade column — cell at row 5 appears offset"],
    },
    "document_provenance_appearance": "scan_artifacts_present",
    "document_provenance_appearance_source": {
        "page_number": 1,
        "text_spans": ["JPEG compression artifacts visible in background"],
    },
    "document_presented_as_original": True,
    "security_features_present": [],                # PHYS_001 Check 4 fires
    "security_features_present_source": {"page_number": 1, "text_spans": []},
    "security_features_assessable": "yes",
    # PHYS_002: missing registrar information — all four checks fire
    "registrar_name_present": False,
    "registrar_signature_present": False,
    "registrar_title_present": False,
    "institution_contact_info_present": False,
    # Content section — suspicious courses kept for future rule coverage
    "grading_scale_format": "letter_grade_us",
    "grading_scale_format_source": {"page_number": 2, "text_spans": ["A, B, C"]},
    "language_of_issue": "english",
    "language_of_issue_source": {"page_number": 1, "text_spans": []},
    "country_of_study": "nigeria",
    "declared_language_of_instruction": "english",
    "suspicious_course_names": [
        "Bandaging",
        "Theater techniques & surgery",
        "Personal Health",
        "Ear/nose/throat",
    ],
    "suspicious_course_names_source": {
        "page_number": 2,
        "text_spans": [
            "Bandaging",
            "Theater techniques & surgery",
            "Personal Health",
            "Ear/nose/throat",
        ],
    },
    "dates_chronology_ok": "yes",
    "dates_chronology_ok_source": None,
    "dates_chronology_issue": "none",
    "program_duration_consistency": "consistent_with_degree",
    "program_duration_consistency_source": None,
    # CONT_003: claimed ADN with implausibly short 5-month duration
    "claimed_degree_type": "ADN",
    "programs": [
        {
            "name": "Global Nursing College ADN",
            "start_date": "2019-01-01",
            "end_date": "2019-06-01",
            "claimed_degree_type": "ADN",
        }
    ],
    # Program section — diploma mill + missing graduation + unknown accreditor
    "accreditation_claim": "Global Online Nursing Board",  # PROG_001 fires
    "accreditation_claim_source": {
        "page_number": 1,
        "text_spans": ["Accredited by Global Online Nursing Board"],
    },
    "diploma_mill_language_detected": "yes",               # PROG_001 fires
    "diploma_mill_language_detected_source": {
        "page_number": 1,
        "text_spans": [
            "No Need To Study",
            "life experience degree",
        ],
    },
    "diploma_mill_phrases_found": [
        "No Need To Study",
        "life experience degree",
        "no need to take exams",
    ],
    "institution_address_present": "no",
    "institution_address_present_source": {"page_number": 1, "text_spans": []},
    "institution_phone_present": "no",
    "institution_phone_present_source": {"page_number": 1, "text_spans": []},
    "institution_website_present": "no",
    "graduation_confirmation_present": "no",               # PROG_002 fires
    "graduation_confirmation_present_source": {
        "page_number": 3,
        "text_spans": [],
    },
    "required_nursing_domains_present": [],                # PROG_003 fires x4
    "required_nursing_domains_present_source": {"page_number": 2, "text_spans": []},
    # Cross-document section — all mismatched
    "applicant_name_match": "mismatch",                    # CROSS_001 fires
    "applicant_name_match_source": {
        "page_number": 1,
        "text_spans": [
            "Transcript: Patricia Johnson",
            "Diploma: Patricia A. Johnstone",
        ],
    },
    "institution_name_match": "mismatch",                  # CROSS_002 fires
    "institution_name_match_source": {
        "page_number": 1,
        "text_spans": [
            "Transcript: Global Nursing College",
            "Diploma: Global Nursing & Health Institute",
        ],
    },
    "dates_match_across_documents": "mismatch_greater_than_90_days",  # CROSS_003 fires
    "dates_match_across_documents_source": {
        "page_number": 1,
        "text_spans": [
            "Transcript graduation: June 2019",
            "CEA report completion: October 2018",
        ],
    },
    "signature_match_across_documents": "mismatch",
    "signature_match_across_documents_source": None,
}

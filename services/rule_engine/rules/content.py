"""Educational content and chronology rules (CONT_001 – CONT_006).

SP-5: Analysis of Educational Chronology.

Each function accepts an aggregation dict and returns list[Flag].

Aggregation fields consumed (see design/extraction-vocabulary.md Section 2):
  grading_scale_format      : letter_grade_us | percentage | 20_point_french |
                              5_point_russian | pass_fail | mixed | unclear
  language_of_issue         : english | french | spanish | other | unclear
  country_of_study          : lower-case country name string (may be absent)
  declared_language_of_instruction : lower-case language string (may be absent)
  course_relevance          : nursing_standard | mixed_with_non_nursing |
                              predominantly_non_nursing | unclear
  duplicate_courses_detected: yes | no | unclear
  suspicious_course_names   : list of strings
  gpa_arithmetic_consistency: consistent | inconsistent | unclear
  dates_chronology_ok       : yes | no | unclear
  dates_chronology_issue    : none | overlap | gap | enrollment_implausibly_early |
                              enrollment_implausibly_late | other
  program_duration_consistency: consistent_with_degree | unusually_short |
                                unusually_long | unclear
"""

from rules.base import Flag, _src

# For CONT_001: which grading scales are expected per document language.
# "other" and "unclear" are intentionally excluded — not enough signal.
_LANGUAGE_TO_EXPECTED_SCALES: dict[str, set[str]] = {
    "english": {"letter_grade_us", "percentage", "pass_fail"},
    "french": {"20_point_french", "percentage"},
    "spanish": {"percentage", "pass_fail"},
    "russian": {"5_point_russian", "percentage"},
}

# For CONT_004: official languages per country of study.
# Keys are lower-case country names as extracted.  Values are sets of
# lower-case language strings.
# NOTE: This list is provisional; MSBN must supply a complete reference table.
_COUNTRY_OFFICIAL_LANGUAGES: dict[str, set[str]] = {
    "philippines": {"english", "filipino"},
    "nigeria": {"english"},
    "india": {"english", "hindi"},
    "kenya": {"english", "swahili"},
    "ghana": {"english"},
    "south africa": {"english", "afrikaans", "zulu", "xhosa"},
    "zimbabwe": {"english"},
    "zambia": {"english"},
    "uganda": {"english"},
    "cameroon": {"english", "french"},
    "france": {"french"},
    "canada": {"english", "french"},
    "belgium": {"french", "dutch", "german"},
    "russia": {"russian"},
    "ukraine": {"ukrainian"},
    "mexico": {"spanish"},
    "colombia": {"spanish"},
    "brazil": {"portuguese"},
    "china": {"chinese"},
    "japan": {"japanese"},
    "south korea": {"korean"},
    "egypt": {"arabic"},
    "jordan": {"arabic"},
    "saudi arabia": {"arabic"},
    "united kingdom": {"english"},
    "ireland": {"english", "irish"},
    "australia": {"english"},
    "new zealand": {"english"},
}


def check_cont_001(agg: dict) -> list:
    """CONT_001 — Grading scale does not match the country-of-study convention.

    E.g., U.S.-style A/B/C letter grades on a French-language transcript
    (France uses the 20-point scale).
    """
    language = agg.get("language_of_issue")
    scale = agg.get("grading_scale_format")

    if not language or not scale:
        return []
    if language in ("unclear", "other") or scale in ("unclear", "mixed"):
        return []

    expected = _LANGUAGE_TO_EXPECTED_SCALES.get(language)
    if expected and scale not in expected:
        return [
            Flag(
                rule_code="CONT_001",
                rule_description="Grading scale does not match country-of-study convention",
                severity="high",
                category="SP-5",
                rationale=(
                    f"Grading scale is '{scale}' but the document language is '{language}', "
                    f"which typically uses: {', '.join(sorted(expected))}. "
                    "A U.S.-style letter grade on a non-English transcript, for example, "
                    "may indicate the document was altered or fabricated."
                ),
                source_location=_src(agg, "grading_scale_format"),
            )
        ]
    return []


def check_cont_002(agg: dict) -> list:
    """CONT_002 — Enrollment or graduation dates are chronologically impossible.

    Fires when dates_chronology_ok is 'no', covering: applicant enrolled
    implausibly early (age < ~16), graduation before enrollment, overlapping
    programs, or unexplained date gaps.
    """
    chron_ok = agg.get("dates_chronology_ok")
    chron_issue = agg.get("dates_chronology_issue", "other")

    if chron_ok != "no":
        return []

    issue_label = {
        "overlap": "enrollment and graduation dates overlap — graduation precedes or coincides with enrollment start",
        "gap": "an unexplained gap exists between enrollment end and graduation date",
        "enrollment_implausibly_early": "enrollment date implies the applicant was younger than 16 at time of enrollment",
        "enrollment_implausibly_late": "enrollment date is implausibly late relative to the applicant's reported age",
        "other": "an unspecified chronological anomaly was detected in the program dates",
    }.get(chron_issue, f"chronological issue: {chron_issue}")

    return [
        Flag(
            rule_code="CONT_002",
            rule_description="Age or date chronology is impossible or incongruous",
            severity="high",
            category="SP-5",
            rationale=(
                f"Dates chronology check failed: {issue_label}. "
                "Impossible dates are a strong indicator of document fabrication."
            ),
            source_location=_src(agg, "dates_chronology_ok"),
        )
    ]


def check_cont_003(agg: dict) -> list:
    """CONT_003 — Non-nursing or duplicate course names detected.

    Fires in up to two situations:
    1. course_relevance indicates predominantly non-nursing content, OR
       suspicious_course_names is non-empty.
    2. duplicate_courses_detected is 'yes'.
    """
    flags = []

    relevance = agg.get("course_relevance")
    suspicious = agg.get("suspicious_course_names") or []

    if relevance in ("mixed_with_non_nursing", "predominantly_non_nursing") or suspicious:
        names_detail = (
            f" Suspicious course names identified: {', '.join(repr(n) for n in suspicious)}."
            if suspicious
            else ""
        )
        flags.append(
            Flag(
                rule_code="CONT_003",
                rule_description="Non-nursing course names detected",
                severity="high",
                category="SP-5",
                rationale=(
                    f"Course relevance classification is '{relevance}'."
                    f"{names_detail} "
                    "Courses that do not belong to a recognized nursing curriculum "
                    "(e.g., 'Bandaging', 'Theater techniques & surgery' — see MSBN Case B) "
                    "suggest a fabricated transcript."
                ),
                source_location=_src(agg, "course_relevance"),
            )
        )

    duplicate = agg.get("duplicate_courses_detected")
    if duplicate == "yes":
        flags.append(
            Flag(
                rule_code="CONT_003",
                rule_description="Duplicate course entries detected",
                severity="high",
                category="SP-5",
                rationale=(
                    "One or more course names appear more than once in the transcript. "
                    "Duplicate entries are a fabrication indicator "
                    "(see MSBN Case B: 'Family planning' listed twice)."
                ),
                source_location=_src(agg, "duplicate_courses_detected"),
            )
        )

    return flags


def check_cont_004(agg: dict) -> list:
    """CONT_004 — Document language does not match the country of study.

    Fires when the language the document is written in is neither the official
    language of the declared country of study nor the declared instruction language.
    """
    language = agg.get("language_of_issue")
    country = agg.get("country_of_study")
    declared_instruction_lang = agg.get("declared_language_of_instruction")

    if not language or not country:
        return []
    if language in ("unclear", "other"):
        return []

    official = _COUNTRY_OFFICIAL_LANGUAGES.get(country.lower())
    if official is None:
        # Unknown country — not enough reference data to flag
        return []

    # If the declared instruction language is in official languages, accept it
    accepted = set(official)
    if declared_instruction_lang:
        accepted.add(declared_instruction_lang.lower())

    if language.lower() not in accepted:
        return [
            Flag(
                rule_code="CONT_004",
                rule_description="Document language does not match country of study",
                severity="medium",
                category="SP-5",
                rationale=(
                    f"Document is written in '{language}' but the declared country of "
                    f"study is '{country}', whose official language(s) are: "
                    f"{', '.join(sorted(official))}. "
                    "A language mismatch may indicate the document was issued by a "
                    "different institution than claimed."
                ),
                source_location=_src(agg, "language_of_issue"),
            )
        ]
    return []


def check_cont_005(agg: dict) -> list:
    """CONT_005 — Reported GPA does not match arithmetic mean of individual grades.

    Fires when the aggregation step has determined GPA arithmetic is inconsistent.
    A mismatch is a strong signal that a grade value was inserted or altered
    (see MSBN Case A: '+2.0' addend inflating the final GPA).
    """
    consistency = agg.get("gpa_arithmetic_consistency")
    if consistency == "inconsistent":
        return [
            Flag(
                rule_code="CONT_005",
                rule_description="Reported GPA inconsistent with individual grade arithmetic",
                severity="high",
                category="SP-5",
                rationale=(
                    "The reported cumulative GPA does not match the arithmetic mean of "
                    "the individual subject grades extracted from the transcript. "
                    "This is consistent with a grade value having been inserted or altered "
                    "(see MSBN Case A: '+2.0' addend followed by an inflated final GPA)."
                ),
                source_location=_src(agg, "gpa_arithmetic_consistency"),
            )
        ]
    return []


def check_cont_006(agg: dict) -> list:
    """CONT_006 — Program duration is implausibly short or long.

    Fires when total enrollment-to-graduation span deviates materially from
    the expected length for the declared degree type.
    """
    duration = agg.get("program_duration_consistency")
    if duration in ("unusually_short", "unusually_long"):
        direction = "shorter" if duration == "unusually_short" else "longer"
        return [
            Flag(
                rule_code="CONT_006",
                rule_description="Program duration anomaly",
                severity="medium",
                category="SP-5",
                rationale=(
                    f"Program duration is classified as '{duration}' — significantly "
                    f"{direction} than expected for the declared degree type. "
                    "Duration outside the 80%–150% range of expected program length "
                    "warrants verification with the issuing institution."
                ),
                source_location=_src(agg, "program_duration_consistency"),
            )
        ]
    return []

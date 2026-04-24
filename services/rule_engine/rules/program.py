"""Program and institution checks for SP-4/SP-5."""

from rules.base import Flag, _src
from rules.ms_curriculum import (
    MS_PN_COURSES,
    VALID_PNV_CODES,
    VALID_BIO_SUBSTITUTIONS,
    TOTAL_SEMESTER_HOURS,
)

# Placeholder list until MSBN provides the production accreditor reference.
_APPROVED_ACCREDITORS = {
    "acen",
    "ccne",
    "cgfns",
    # Country-specific bodies; replace with MSBN-confirmed entries.
    "nmc",   # UK Nursing & Midwifery Council
    "anmac", # Australian Nursing & Midwifery Accreditation Council
    "cno",   # College of Nurses of Ontario
    "cnc",   # Canadian Nurses Association / provincial colleges
    "ncbn",  # Nigeria Council for Nursing
    "prc",   # Philippine Professional Regulation Commission
    "inc",   # Indian Nursing Council
}

# Required domains are provisional until MSBN confirms the official thresholds.
_REQUIRED_DOMAINS = frozenset([
    "adult_med_surg",
    "obstetrics",
    "pediatrics",
    "psychiatric",
])


def check_prog_001(agg: dict) -> list:
    """Flag diploma-mill language and unrecognized accreditation claims."""
    flags = []

    # Diploma-mill wording is enough to force human verification.
    mill_detected = agg.get("diploma_mill_language_detected")
    phrases = agg.get("diploma_mill_phrases_found") or []

    if mill_detected in ("yes", "possible"):
        phrase_detail = (
            f" Phrases detected: {', '.join(repr(p) for p in phrases)}."
            if phrases
            else ""
        )
        flags.append(
            Flag(
                rule_code="PROG_001",
                rule_description="Diploma mill language detected",
                severity="high",
                category="SP-5",
                rationale=(
                    f"Diploma mill language was detected (confidence: '{mill_detected}')."
                    f"{phrase_detail} "
                    "Examples include 'no need to study', 'life experience degree', "
                    "'no need to take exams' (see MSBN Cases D and E). "
                    "Requires human verification before denial."
                ),
                source_location=_src(agg, "diploma_mill_language_detected"),
            )
        )

    # Missing or unknown accreditation also needs review.
    claim = (agg.get("accreditation_claim") or "").strip()
    if not claim or claim.lower() not in _APPROVED_ACCREDITORS:
        detail = (
            f"Accreditation claim '{claim}' is not in the approved accreditor list."
            if claim
            else "No accreditation claim was found in the document."
        )
        flags.append(
            Flag(
                rule_code="PROG_001",
                rule_description="Unrecognized or absent accreditation claim",
                severity="high",
                category="SP-5",
                rationale=(
                    f"{detail} "
                    "The approved accreditor list is provisional (CGFNS, ACEN, CCNE, and "
                    "recognized country-specific bodies). MSBN must confirm official list "
                    "before this flag is used as a denial basis. Requires human review."
                ),
                source_location=_src(agg, "accreditation_claim"),
            )
        )

    return flags


def check_prog_002(agg: dict) -> list:
    """Flag missing completion evidence when the rest of the record is weak."""
    present = agg.get("graduation_confirmation_present")
    if present != "no":
        return []

    present_domains = frozenset(agg.get("required_nursing_domains_present") or [])
    has_all_required_domains = _REQUIRED_DOMAINS.issubset(present_domains)
    chronology_ok = agg.get("dates_chronology_ok") == "yes"
    duration_consistent = (
        agg.get("program_duration_consistency") == "consistent_with_degree"
    )

    # Many legitimate transcripts do not print an explicit conferral statement
    # on the coursework pages. If the transcript otherwise looks like a complete,
    # coherent nursing program, do not escalate this as a standalone fraud flag.
    if has_all_required_domains and chronology_ok and duration_consistent:
        return []

    return [
        Flag(
            rule_code="PROG_002",
            rule_description="No graduation or degree conferral confirmation",
            severity="high",
            category="SP-4",
            rationale=(
                "The transcript does not include a graduation date, degree conferral "
                "statement, or other explicit completion indicator, and the remaining "
                "program evidence is not strong enough to infer completion from the "
                "coursework record alone. Absence may indicate a fabricated affidavit "
                "of graduation (see MSBN Case C: student submitted an affidavit the "
                "school never issued). Staff must independently verify completion "
                "status with the institution."
            ),
            source_location=_src(agg, "graduation_confirmation_present"),
        )
    ]


def check_prog_003(agg: dict) -> list:
    """Flag missing required nursing domains."""
    present_raw = agg.get("required_nursing_domains_present")
    # None means extraction missed the field; [] means it found no domains.
    if present_raw is None:
        return []

    present = frozenset(present_raw)
    missing = sorted(_REQUIRED_DOMAINS - present)

    if not missing:
        return []

    return [
        Flag(
            rule_code="PROG_003",
            rule_description=f"Required nursing domain absent: {domain}",
            severity="high",
            category="SP-5",
            rationale=(
                f"Required nursing domain '{domain}' has no recorded theory or clinical "
                "hours in the transcript. "
                "All four core domains (Adult Med/Surg, Obstetrics, Pediatrics, "
                "Psychiatric/Mental Health) must be present in a qualifying nursing program "
                "(see requirements-draft.md Section 2 and MSBN Case E). "
                "MSBN must confirm official minimum hour thresholds before this flag "
                "is used as a denial basis."
            ),
            source_location=_src(agg, "required_nursing_domains_present"),
        )
        for domain in missing
    ]


def check_prog_004(agg: dict) -> list:
    """Flag PNV course codes outside the MS PN curriculum."""
    if agg.get("program_type") != "ms_practical_nursing":
        return []

    courses = agg.get("courses") or []
    if not courses:
        return []

    flags = []
    valid_codes = VALID_PNV_CODES | frozenset(VALID_BIO_SUBSTITUTIONS.keys())

    for course in courses:
        code = (course.get("code") or "").strip().upper()
        if not code.startswith("PNV"):
            continue
        if code not in valid_codes:
            flags.append(
                Flag(
                    rule_code="PROG_004",
                    rule_description=f"Unrecognized course code: {code}",
                    severity="high",
                    category="SP-5",
                    rationale=(
                        f"Course code '{code}' does not appear in the Mississippi "
                        "Practical Nursing Curriculum Framework (CIP 51.3901, 2024 "
                        "revision). All valid PNV course codes are defined by the "
                        "MS Community College Board. A course code not in this list "
                        "is a strong fraud indicator. Verify against the official "
                        "curriculum document."
                    ),
                    source_location=course.get("source_location"),
                )
            )
    return flags


def check_prog_005(agg: dict) -> list:
    """Flag PNV credit hours that do not match the curriculum."""
    if agg.get("program_type") != "ms_practical_nursing":
        return []

    courses = agg.get("courses") or []
    if not courses:
        return []

    flags = []
    for course in courses:
        code = (course.get("code") or "").strip().upper()
        reported_hours = course.get("credit_hours")
        if reported_hours is None or code not in MS_PN_COURSES:
            continue

        expected = MS_PN_COURSES[code].credit_hours
        try:
            reported = int(float(reported_hours))
        except (ValueError, TypeError):
            continue

        if reported != expected:
            flags.append(
                Flag(
                    rule_code="PROG_005",
                    rule_description=f"Credit hours mismatch for {code}",
                    severity="high",
                    category="SP-5",
                    rationale=(
                        f"Course {code} ({MS_PN_COURSES[code].name}) shows "
                        f"{reported} credit hours on the transcript, but the "
                        f"official MS PN curriculum specifies {expected} credit "
                        "hours. Credit hour discrepancies may indicate transcript "
                        "alteration."
                    ),
                    source_location=course.get("source_location"),
                )
            )
    return flags


def check_prog_006(agg: dict) -> list:
    """Flag total hours that do not match the MS PN program total."""
    if agg.get("program_type") != "ms_practical_nursing":
        return []

    total = agg.get("total_credit_hours")
    if total is None:
        return []

    try:
        total_val = int(float(total))
    except (ValueError, TypeError):
        return []

    if total_val == TOTAL_SEMESTER_HOURS:
        return []

    return [
        Flag(
            rule_code="PROG_006",
            rule_description="Total program hours mismatch",
            severity="high",
            category="SP-5",
            rationale=(
                f"Transcript reports {total_val} total semester credit hours, "
                f"but the official MS Practical Nursing program requires exactly "
                f"{TOTAL_SEMESTER_HOURS} semester hours (980 clock hours). "
                "A completed program transcript with a different total is "
                "suspicious and requires verification."
            ),
            source_location=_src(agg, "total_credit_hours"),
        )
    ]


def check_prog_007(agg: dict) -> list:
    """Flag MS PN courses listed earlier than their allowed semester."""
    if agg.get("program_type") != "ms_practical_nursing":
        return []

    courses = agg.get("courses") or []
    if not courses:
        return []

    flags = []
    for course in courses:
        code = (course.get("code") or "").strip().upper()
        semester = course.get("semester")
        if semester is None or code not in MS_PN_COURSES:
            continue

        try:
            sem_val = int(semester)
        except (ValueError, TypeError):
            continue

        expected_earliest = MS_PN_COURSES[code].earliest_semester
        if sem_val < expected_earliest:
            flags.append(
                Flag(
                    rule_code="PROG_007",
                    rule_description=f"Course {code} in wrong semester",
                    severity="medium",
                    category="SP-5",
                    rationale=(
                        f"Course {code} ({MS_PN_COURSES[code].name}) appears in "
                        f"semester {sem_val}, but the MS PN curriculum framework "
                        f"places it no earlier than semester {expected_earliest}. "
                        "Courses have prerequisites and expected ordering; an "
                        "out-of-sequence capstone or advanced course is a red flag "
                        "for a fabricated transcript."
                    ),
                    source_location=course.get("source_location"),
                )
            )
    return flags

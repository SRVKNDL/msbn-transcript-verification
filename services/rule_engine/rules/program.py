"""Program and institution checks for SP-4/SP-5."""

from rules.base import Flag, _src
from rules.ms_curriculum import (
    MS_PN_COURSES,
    VALID_PNV_CODES,
    VALID_BIO_SUBSTITUTIONS,
    TOTAL_SEMESTER_HOURS,
)


def check_prog_001(agg: dict) -> list:
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
                    rule_code="PROG_001",
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


def check_prog_002(agg: dict) -> list:
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
                    rule_code="PROG_002",
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


def check_prog_003(agg: dict) -> list:
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
            rule_code="PROG_003",
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


def check_prog_004(agg: dict) -> list:
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
                    rule_code="PROG_004",
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

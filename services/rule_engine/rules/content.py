"""Academic content and chronology checks for CONT_001–CONT_004."""

from collections import defaultdict
from datetime import date, datetime

from rules.base import Flag, _src

# Program duration reference table (months) for Mississippi nursing programs.
# Hard-coded here per spec; do NOT copy to ms_curriculum.py.
_DEGREE_DURATION: dict[str, dict] = {
    "LPN":    {"min": 9,  "max": 24},
    "ADN":    {"min": 18, "max": 48},
    "BSN":    {"min": 30, "max": 96},
    "ABSN":   {"min": 12, "max": 24},
    "RN-BSN": {"min": 9,  "max": 36},
    "LPN-RN": {"min": 9,  "max": 36},
    "MSN":    {"min": 18, "max": 60},
    "DNP":    {"min": 24, "max": 72},
    "CRNA":   {"min": 30, "max": 48},
}

_GPA_COVERAGE_TOLERANCE = 0.90
_TERM_HOURS_TOLERANCE = 0.25


def _parse_date(date_str) -> date | None:
    """Parse common date formats; return None on failure."""
    if not date_str:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d/%Y", "%Y"):
        try:
            return datetime.strptime(str(date_str), fmt).date()
        except (ValueError, TypeError):
            pass
    return None


def _months_between(start_str, end_str) -> float | None:
    """Return approximate whole months between two date strings, or None."""
    start = _parse_date(start_str)
    end = _parse_date(end_str)
    if start is None or end is None:
        return None
    return (end.year - start.year) * 12 + (end.month - start.month)


def check_cont_001(agg: dict) -> list:
    """Chronology impossibility — six structured checks plus an extractor-advisory fallback."""
    flags = []
    programs = agg.get("programs") or []
    courses = agg.get("courses") or []
    leave_markers = agg.get("leave_of_absence_markers") or []
    semesters = agg.get("semesters") or []
    dob_str = agg.get("date_of_birth")
    doc_issue_str = agg.get("document_issue_date")
    checks_fired = False

    # Check 1 — graduation before enrollment (HIGH)
    for prog in programs:
        start = _parse_date(prog.get("start_date"))
        end = _parse_date(prog.get("end_date"))
        if start and end and end < start:
            flags.append(Flag(
                rule_code="CONT_001",
                rule_description="Graduation date precedes enrollment date",
                severity="high",
                category="SP-5",
                rationale=(
                    f"Program '{prog.get('name', 'unknown')}' has graduation date "
                    f"{prog.get('end_date')} before enrollment date {prog.get('start_date')}. "
                    "Impossible program dates are a strong fabrication indicator."
                ),
                source_location=_src(agg, "programs"),
            ))
            checks_fired = True

    # Check 2 — course end before course start (HIGH)
    for course in courses:
        c_start = _parse_date(course.get("start_date"))
        c_end = _parse_date(course.get("end_date"))
        if c_start and c_end and c_end < c_start:
            label = course.get("course_title") or course.get("name") or "unknown"
            flags.append(Flag(
                rule_code="CONT_001",
                rule_description="Course end date precedes course start date",
                severity="high",
                category="SP-5",
                rationale=(
                    f"Course '{label}' has end date {course.get('end_date')} before "
                    f"start date {course.get('start_date')}. "
                    "Impossible course dates indicate document fabrication."
                ),
                source_location=_src(agg, "courses"),
            ))
            checks_fired = True

    # Check 3 — implausible age at enrollment (HIGH if <16, LOW if >80)
    if dob_str and programs:
        dob = _parse_date(dob_str)
        enrollment = _parse_date(programs[0].get("start_date"))
        if dob and enrollment:
            age_years = (enrollment - dob).days / 365.25
            if age_years < 16:
                flags.append(Flag(
                    rule_code="CONT_001",
                    rule_description="Implausibly young age at enrollment",
                    severity="high",
                    category="SP-5",
                    rationale=(
                        f"Computed age at enrollment is approximately {age_years:.1f} years, "
                        "below the minimum plausible age of 16 for a nursing program. "
                        "This strongly suggests a falsified date of birth or enrollment date."
                    ),
                    source_location=_src(agg, "date_of_birth"),
                ))
                checks_fired = True
            elif age_years > 80:
                flags.append(Flag(
                    rule_code="CONT_001",
                    rule_description="Implausibly advanced age at enrollment",
                    severity="low",
                    category="SP-5",
                    rationale=(
                        f"Computed age at enrollment is approximately {age_years:.1f} years, "
                        "above 80. This may indicate a data entry error in the date of birth "
                        "or enrollment date and warrants verification."
                    ),
                    source_location=_src(agg, "date_of_birth"),
                ))
                checks_fired = True

    # Check 4 — overlapping programs (HIGH)
    for i, prog_a in enumerate(programs):
        for prog_b in programs[i + 1:]:
            a_start = _parse_date(prog_a.get("start_date"))
            a_end = _parse_date(prog_a.get("end_date"))
            b_start = _parse_date(prog_b.get("start_date"))
            b_end = _parse_date(prog_b.get("end_date"))
            if a_start and a_end and b_start and b_end:
                if a_start <= b_end and b_start <= a_end:
                    flags.append(Flag(
                        rule_code="CONT_001",
                        rule_description="Overlapping program enrollments",
                        severity="high",
                        category="SP-5",
                        rationale=(
                            f"Programs '{prog_a.get('name')}' and '{prog_b.get('name')}' "
                            "have overlapping date ranges. Simultaneous full-time enrollment "
                            "in two nursing programs is implausible."
                        ),
                        source_location=_src(agg, "programs"),
                    ))
                    checks_fired = True

    # Check 5 — unexplained date gaps between consecutive terms (MEDIUM if >12mo, LOW if >6mo)
    if len(semesters) > 1:
        dated = []
        for sem in semesters:
            s_date = _parse_date(sem.get("start_date"))
            if s_date:
                dated.append((s_date, sem))
        dated.sort(key=lambda x: x[0])

        for idx in range(len(dated) - 1):
            _, sem_a = dated[idx]
            _, sem_b = dated[idx + 1]
            gap_months = _months_between(sem_a.get("end_date"), sem_b.get("start_date"))
            if gap_months is not None and gap_months > 6:
                gap_covered = False
                gap_end = _parse_date(sem_b.get("start_date"))
                gap_start = _parse_date(sem_a.get("end_date"))
                for loa in leave_markers:
                    loa_s = _parse_date(loa.get("start_date"))
                    loa_e = _parse_date(loa.get("end_date"))
                    if loa_s and loa_e and gap_start and gap_end:
                        if loa_s <= gap_end and loa_e >= gap_start:
                            gap_covered = True
                            break
                if not gap_covered:
                    severity = "medium" if gap_months > 12 else "low"
                    flags.append(Flag(
                        rule_code="CONT_001",
                        rule_description="Unexplained gap between academic terms",
                        severity=severity,
                        category="SP-5",
                        rationale=(
                            f"A gap of approximately {gap_months:.0f} months between "
                            f"'{sem_a.get('term', 'term')}' and '{sem_b.get('term', 'term')}' "
                            "has no leave of absence or withdrawal marker. "
                            f"Gaps {'> 12 months' if gap_months > 12 else '> 6 months'} "
                            "warrant verification."
                        ),
                        source_location=_src(agg, "semesters"),
                    ))
                    checks_fired = True

    # Check 6 — future-dated events (HIGH)
    if doc_issue_str:
        doc_issue = _parse_date(doc_issue_str)
        if doc_issue:
            date_candidates = []
            for prog in programs:
                for fld in ("start_date", "end_date"):
                    date_candidates.append((prog.get(fld), f"program '{prog.get('name')}'"))
            for course in courses:
                lbl = course.get("course_title") or course.get("name") or "course"
                for fld in ("start_date", "end_date"):
                    date_candidates.append((course.get(fld), lbl))
            for dt_str, label in date_candidates:
                dt = _parse_date(dt_str)
                if dt and dt > doc_issue:
                    flags.append(Flag(
                        rule_code="CONT_001",
                        rule_description="Transcript date is after document issue date",
                        severity="high",
                        category="SP-5",
                        rationale=(
                            f"'{label}' has date {dt_str} which is after the document issue "
                            f"date {doc_issue_str}. Events cannot appear on a transcript "
                            "before the document was issued."
                        ),
                        source_location=_src(agg, "document_issue_date"),
                    ))
                    checks_fired = True
                    break

    # Advisory fallback — extractor flagged chronology but structured checks found nothing
    if not checks_fired and agg.get("dates_chronology_ok") == "no":
        flags.append(Flag(
            rule_code="CONT_001",
            rule_description="Chronology advisory: extractor flagged date anomaly",
            severity="low",
            category="SP-5",
            rationale=(
                "The structured date checks did not produce specific findings, but the "
                "document extractor independently flagged a chronological anomaly "
                "(dates_chronology_ok='no'). Manual review of document dates is recommended."
            ),
            source_location=_src(agg, "dates_chronology_ok"),
        ))

    return flags


def check_cont_002(agg: dict) -> list:
    """GPA arithmetic verification — per-semester, rolling cumulative, final, and scale-ceiling checks."""
    flags = []

    semesters = agg.get("semesters") or []
    courses = agg.get("courses") or []
    grading_scale = agg.get("grading_scale_format")
    final_cum_gpa = agg.get("final_cum_gpa_stated")
    scale_max = agg.get("grading_scale_maximum")

    # Skip entire rule for Pass/Fail-only grading
    if grading_scale == "pass_fail":
        return []

    scale_max = float(scale_max or 4.0)

    # Numeric grades: courses with grade_points/quality points, excluding transfer credits
    numeric_grades = [
        c for c in courses
        if c.get("grade_points") is not None and not c.get("transfer_marker")
    ]
    has_semesters = bool(semesters)

    # ── Checks 1 and 2 require semester structure and ≥5 numeric grades ────────

    if has_semesters and len(numeric_grades) >= 5:
        for sem in semesters:
            term_gpa = sem.get("term_gpa_stated")
            term_hours = sem.get("term_credit_hours_stated") or 0
            cum_gpa_stated = sem.get("cum_gpa_stated_after_term")

            # Check 1 — per-semester Term GPA mismatch (HIGH if >5%, MEDIUM if 2–5%)
            sem_course_ids = set(sem.get("courses") or [])
            sem_courses = [
                c for c in courses
                if (c.get("name") in sem_course_ids or c.get("course_code") in sem_course_ids)
                and c.get("grade_points") is not None
                and not c.get("transfer_marker")
            ]
            if sem_courses and term_gpa is not None and term_gpa > 0:
                total_sem_ch = _course_hours(sem_courses)
                hours_are_complete = (
                    not term_hours
                    or abs(total_sem_ch - float(term_hours)) <= _TERM_HOURS_TOLERANCE
                )
                if total_sem_ch > 0 and hours_are_complete:
                    computed_term = _computed_gpa_from_courses(sem_courses, scale_max)
                    diff_pct = abs(computed_term - term_gpa) / term_gpa
                    if diff_pct > 0.05:
                        flags.append(Flag(
                            rule_code="CONT_002",
                            rule_description=f"Term GPA mismatch for {sem.get('term')}",
                            severity="high",
                            category="SP-5",
                            rationale=(
                                f"Stated Term GPA {term_gpa:.2f} differs from computed "
                                f"{computed_term:.2f} by {diff_pct:.1%} for "
                                f"'{sem.get('term')}' (threshold: >5%)."
                            ),
                            source_location=_src(agg, "semesters"),
                        ))
                    elif diff_pct > 0.02:
                        flags.append(Flag(
                            rule_code="CONT_002",
                            rule_description=f"Term GPA mismatch for {sem.get('term')}",
                            severity="medium",
                            category="SP-5",
                            rationale=(
                                f"Stated Term GPA {term_gpa:.2f} differs from computed "
                                f"{computed_term:.2f} by {diff_pct:.1%} for "
                                f"'{sem.get('term')}' (threshold: 2–5%)."
                            ),
                            source_location=_src(agg, "semesters"),
                        ))

            # Check 2 — rolling Cum GPA mismatch (HIGH if >5%, MEDIUM if 2–5%)
            # Only evaluate when explicit cumulative quality points are available.
            # Weighting term GPAs alone causes false positives on transfer-heavy
            # transcripts and documents whose cumulative GPA includes prior work.
            cum_quality_points = _first_number(
                sem,
                "cum_quality_points_stated",
                "cumulative_quality_points_stated",
                "cum_quality_points",
                "quality_points_stated_after_term",
            )
            cum_hours_stated = _first_number(
                sem,
                "cum_credit_hours_stated",
                "cumulative_credit_hours_stated",
                "cum_hours_stated",
                "hours_stated_after_term",
            )
            if (
                cum_quality_points is not None
                and cum_hours_stated is not None
                and cum_hours_stated > 0
            ):
                computed_cum = cum_quality_points / cum_hours_stated
            else:
                computed_cum = None

            if computed_cum is not None:
                if cum_gpa_stated is not None and cum_gpa_stated > 0:
                    diff_pct = abs(computed_cum - cum_gpa_stated) / cum_gpa_stated
                    if diff_pct > 0.05:
                        flags.append(Flag(
                            rule_code="CONT_002",
                            rule_description=f"Cumulative GPA mismatch after {sem.get('term')}",
                            severity="high",
                            category="SP-5",
                            rationale=(
                                f"Stated Cum GPA {cum_gpa_stated:.2f} after "
                                f"'{sem.get('term')}' differs from computed "
                                f"{computed_cum:.2f} by {diff_pct:.1%} (threshold: >5%)."
                            ),
                            source_location=_src(agg, "semesters"),
                        ))
                    elif diff_pct > 0.02:
                        flags.append(Flag(
                            rule_code="CONT_002",
                            rule_description=f"Cumulative GPA mismatch after {sem.get('term')}",
                            severity="medium",
                            category="SP-5",
                            rationale=(
                                f"Stated Cum GPA {cum_gpa_stated:.2f} after "
                                f"'{sem.get('term')}' differs from computed "
                                f"{computed_cum:.2f} by {diff_pct:.1%} (threshold: 2–5%)."
                            ),
                            source_location=_src(agg, "semesters"),
                        ))

    # ── Check 3 — final Cum GPA mismatch (HIGH if >10%, MEDIUM if 5–10%) ──────

    if final_cum_gpa is not None and final_cum_gpa > 0:
        computed_final = None
        total_credit_hours = _first_number(
            agg,
            "total_credit_hours_stated",
            "total_credit_hours",
        )
        total_quality_points = _first_number(
            agg,
            "total_quality_points_stated",
            "quality_points_stated",
            "total_grade_points_stated",
        )
        if total_quality_points is not None and total_credit_hours and total_credit_hours > 0:
            computed_final = total_quality_points / total_credit_hours
        elif numeric_grades:
            total_ch = _course_hours(numeric_grades)
            course_coverage_ok = (
                not total_credit_hours
                or total_ch >= float(total_credit_hours) * _GPA_COVERAGE_TOLERANCE
            )
            if total_ch > 0 and course_coverage_ok:
                computed_final = _computed_gpa_from_courses(numeric_grades, scale_max)
        elif semesters:
            total_ch = sum(s.get("term_credit_hours_stated") or 0 for s in semesters)
            semester_coverage_ok = (
                not total_credit_hours
                or total_ch >= float(total_credit_hours) * _GPA_COVERAGE_TOLERANCE
            )
            if total_ch > 0 and semester_coverage_ok:
                computed_final = sum(
                    (s.get("term_gpa_stated") or 0) * (s.get("term_credit_hours_stated") or 0)
                    for s in semesters
                    if s.get("term_gpa_stated") is not None
                ) / total_ch

        if computed_final is not None:
            diff_pct = abs(computed_final - final_cum_gpa) / final_cum_gpa
            if diff_pct > 0.10:
                flags.append(Flag(
                    rule_code="CONT_002",
                    rule_description="Final cumulative GPA mismatch",
                    severity="high",
                    category="SP-5",
                    rationale=(
                        f"Final stated Cum GPA {final_cum_gpa:.2f} differs from computed "
                        f"{computed_final:.2f} by {diff_pct:.1%} (threshold: >10%)."
                    ),
                    source_location=_src(agg, "final_cum_gpa_stated"),
                ))
            elif diff_pct > 0.05:
                flags.append(Flag(
                    rule_code="CONT_002",
                    rule_description="Final cumulative GPA mismatch",
                    severity="medium",
                    category="SP-5",
                    rationale=(
                        f"Final stated Cum GPA {final_cum_gpa:.2f} differs from computed "
                        f"{computed_final:.2f} by {diff_pct:.1%} (threshold: 5–10%)."
                    ),
                    source_location=_src(agg, "final_cum_gpa_stated"),
                ))

    # ── Check 4 — term-to-cum reconciliation failure (HIGH) ───────────────────

    if semesters and final_cum_gpa is not None and final_cum_gpa > 0:
        total_ch = sum(s.get("term_credit_hours_stated") or 0 for s in semesters)
        total_credit_hours = _first_number(
            agg,
            "total_credit_hours_stated",
            "total_credit_hours",
        )
        semester_coverage_ok = (
            not total_credit_hours
            or total_ch >= float(total_credit_hours) * _GPA_COVERAGE_TOLERANCE
        )
        if total_ch > 0 and semester_coverage_ok:
            computed_from_terms = sum(
                (s.get("term_gpa_stated") or 0) * (s.get("term_credit_hours_stated") or 0)
                for s in semesters
                if s.get("term_gpa_stated") is not None and s.get("term_credit_hours_stated")
            ) / total_ch
            diff_pct = abs(computed_from_terms - final_cum_gpa) / final_cum_gpa
            if diff_pct > 0.005:  # 0.5% tolerance for floating-point noise
                flags.append(Flag(
                    rule_code="CONT_002",
                    rule_description="Semester weighted average does not reconcile with final Cum GPA",
                    severity="high",
                    category="SP-5",
                    rationale=(
                        f"Credit-hour-weighted average of all Term GPAs ({computed_from_terms:.2f}) "
                        f"differs from final stated Cum GPA ({final_cum_gpa:.2f}) by {diff_pct:.1%}. "
                        "This reconciliation failure indicates GPA values were altered."
                    ),
                    source_location=_src(agg, "final_cum_gpa_stated"),
                ))

    # ── Check 5 — GPA exceeds scale maximum (HIGH) ────────────────────────────

    if scale_max is not None and scale_max > 0:
        gpa_candidates = []
        for sem in semesters:
            if sem.get("term_gpa_stated") is not None:
                gpa_candidates.append((sem.get("term_gpa_stated"), f"term '{sem.get('term')}'"))
            if sem.get("cum_gpa_stated_after_term") is not None:
                gpa_candidates.append((sem.get("cum_gpa_stated_after_term"), f"cum after '{sem.get('term')}'"))
        if final_cum_gpa is not None:
            gpa_candidates.append((final_cum_gpa, "final Cum GPA"))
        for gpa_val, label in gpa_candidates:
            if gpa_val > scale_max:
                flags.append(Flag(
                    rule_code="CONT_002",
                    rule_description="GPA value exceeds grading scale maximum",
                    severity="high",
                    category="SP-5",
                    rationale=(
                        f"GPA {gpa_val} for {label} exceeds the stated grading scale "
                        f"maximum of {scale_max}. A GPA above the scale ceiling is "
                        "mathematically impossible."
                    ),
                    source_location=_src(agg, "grading_scale_maximum"),
                ))
                break  # one flag suffices; all further values are suspect

    # ── Check 6 — suspicious perfection (LOW) ─────────────────────────────────

    if semesters:
        term_gpas = [s.get("term_gpa_stated") for s in semesters if s.get("term_gpa_stated") is not None]
        total_term_hours = sum(s.get("term_credit_hours_stated") or 0 for s in semesters)
        if (
            len(term_gpas) >= 2
            and total_term_hours >= 40
            and all(g == 4.0 for g in term_gpas)
        ):
            flags.append(Flag(
                rule_code="CONT_002",
                rule_description="Suspiciously perfect GPA across all terms",
                severity="low",
                category="SP-5",
                rationale=(
                    f"Every Term GPA is exactly 4.0 across {total_term_hours} credit hours "
                    f"and {len(term_gpas)} terms. Statistical perfection at this scale is "
                    "highly anomalous and may indicate fabricated grades."
                ),
                source_location=_src(agg, "semesters"),
            ))

    # ── Check 7 — monotonic trend anomaly (LOW) ───────────────────────────────

    if semesters:
        term_gpas = [s.get("term_gpa_stated") for s in semesters if s.get("term_gpa_stated") is not None]
        if len(term_gpas) >= 3:
            rounded = [round(g, 2) for g in term_gpas]
            if len(set(rounded)) == 1:
                flags.append(Flag(
                    rule_code="CONT_002",
                    rule_description="All term GPAs identical across semesters",
                    severity="low",
                    category="SP-5",
                    rationale=(
                        f"Every Term GPA is exactly {rounded[0]:.2f} across {len(term_gpas)} "
                        "semesters. Identical GPAs to two decimal places are statistically "
                        "implausible and suggest fabricated or copy-pasted values."
                    ),
                    source_location=_src(agg, "semesters"),
                ))

    return flags


def _first_number(data: dict, *keys: str) -> float | None:
    for key in keys:
        value = data.get(key)
        if value is None:
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _course_hours(courses: list[dict]) -> float:
    return sum(float(c.get("credit_hours") or 0) for c in courses)


def _course_quality_points(course: dict, scale_max: float) -> float:
    """Return quality points, accepting either GPA points or transcript points."""
    hours = float(course.get("credit_hours") or 0)
    grade_points = float(course.get("grade_points") or 0)
    if grade_points > scale_max and hours > 0:
        # Many transcripts print quality points in the course row:
        # credit hours * grade value, e.g. 9 credits with C => 18.
        return grade_points
    return grade_points * hours


def _computed_gpa_from_courses(courses: list[dict], scale_max: float) -> float:
    total_hours = _course_hours(courses)
    if total_hours <= 0:
        return 0.0
    return sum(_course_quality_points(course, scale_max) for course in courses) / total_hours


def check_cont_003(agg: dict) -> list:
    """Program duration plausibility against Mississippi nursing degree reference table."""
    flags = []

    degree_type = agg.get("claimed_degree_type")
    if not degree_type or degree_type == "unclear":
        return []

    duration_ref = _DEGREE_DURATION.get(degree_type)
    if duration_ref is None:
        return []

    programs = agg.get("programs") or []
    semesters = agg.get("semesters") or []
    total_credit_hours = agg.get("total_credit_hours_stated")
    leave_markers = agg.get("leave_of_absence_markers") or []

    duration_months = None
    if programs:
        duration_months = _months_between(
            programs[0].get("start_date"), programs[0].get("end_date")
        )

    min_m = duration_ref["min"]
    max_m = duration_ref["max"]

    # Check 1 — duration below minimum (HIGH)
    if duration_months is not None and duration_months < min_m:
        flags.append(Flag(
            rule_code="CONT_003",
            rule_description="Program duration below minimum for degree type",
            severity="high",
            category="SP-5",
            rationale=(
                f"{degree_type} program duration is approximately {duration_months:.0f} months, "
                f"below the minimum {min_m} months. A program shorter than its regulatory "
                "minimum is a diploma mill indicator."
            ),
            source_location=_src(agg, "programs"),
        ))

    # Check 2 — duration above maximum (MEDIUM)
    if duration_months is not None and duration_months > max_m:
        flags.append(Flag(
            rule_code="CONT_003",
            rule_description="Program duration above maximum for degree type",
            severity="medium",
            category="SP-5",
            rationale=(
                f"{degree_type} program duration is approximately {duration_months:.0f} months, "
                f"above the expected maximum of {max_m} months. "
                "Extended duration warrants verification with the issuing institution."
            ),
            source_location=_src(agg, "programs"),
        ))

    # Check 3 — credit-hour-to-duration pace implausible (HIGH)
    # Skip if total_credit_hours_stated missing
    if total_credit_hours is not None and duration_months is not None and duration_months > 0:
        pace = total_credit_hours / duration_months
        if pace > 15:
            flags.append(Flag(
                rule_code="CONT_003",
                rule_description="Credit-hour pace implausibly fast",
                severity="high",
                category="SP-5",
                rationale=(
                    f"Sustained pace of {pace:.1f} credit hours/month "
                    f"({total_credit_hours} hours over {duration_months:.0f} months) "
                    "exceeds 15 credit hours/month. This pace is not achievable in a "
                    "legitimate clinical nursing program."
                ),
                source_location=_src(agg, "total_credit_hours_stated"),
            ))

    # Check 4 — summer-only completion (LOW)
    # Skip if semester term types not extracted
    if semesters:
        term_types = [s.get("term_type") for s in semesters if s.get("term_type")]
        if term_types and all(t == "summer" for t in term_types):
            flags.append(Flag(
                rule_code="CONT_003",
                rule_description="Entire program completed only in summer terms",
                severity="low",
                category="SP-5",
                rationale=(
                    "All course terms are classified as summer sessions. A complete nursing "
                    "program compressed entirely into summer terms is unusual and warrants "
                    "verification with the institution."
                ),
                source_location=_src(agg, "semesters"),
            ))

    # Check 5 — unexplained extension (MEDIUM)
    # Fallback: if leave_of_absence_markers missing, treat as no LOA
    if duration_months is not None and duration_months > max_m and not leave_markers:
        flags.append(Flag(
            rule_code="CONT_003",
            rule_description="Unexplained program duration exceeds maximum with no leave of absence marker",
            severity="medium",
            category="SP-5",
            rationale=(
                f"{degree_type} program duration of {duration_months:.0f} months exceeds "
                f"the maximum {max_m} months with no leave of absence or withdrawal markers "
                "to explain the extension."
            ),
            source_location=_src(agg, "programs"),
        ))

    return flags


def check_cont_004(agg: dict) -> list:
    """Duplicate course detection — exact code duplicates and volume threshold."""
    flags = []

    courses = agg.get("courses") or []
    if not courses:
        return []

    # Exclude transfer courses from duplicate analysis
    non_transfer = [c for c in courses if not c.get("transfer_marker")]

    # Check 1 — exact code duplication without retake marker (HIGH)
    # Skip if course codes not extracted
    codes_extracted = any(c.get("course_code") for c in non_transfer)
    if codes_extracted:
        groups: dict = defaultdict(list)
        for c in non_transfer:
            code = c.get("course_code")
            if code:
                title = c.get("course_title") or c.get("name") or ""
                hours = c.get("credit_hours")
                groups[(code, title, hours)].append(c)

        for (code_str, title_str, _), group in groups.items():
            if len(group) >= 2:
                without_retake = [c for c in group if not c.get("retake_marker")]
                if len(without_retake) >= 2:
                    flags.append(Flag(
                        rule_code="CONT_004",
                        rule_description=f"Exact duplicate course without retake marker: {code_str}",
                        severity="high",
                        category="SP-5",
                        rationale=(
                            f"Course '{code_str} — {title_str}' appears {len(without_retake)} "
                            "times with no retake or repeat marker. Duplicate course entries "
                            "without a legitimate repeat indicator are a fabrication indicator."
                        ),
                        source_location=_src(agg, "courses"),
                    ))

    # Check 2 — duplicate volume threshold >20% (HIGH)
    if non_transfer:
        seen: dict = {}
        duplicated: set = set()
        for c in non_transfer:
            key = c.get("course_code") or c.get("course_title") or c.get("name")
            if key:
                if key in seen:
                    duplicated.add(key)
                else:
                    seen[key] = True

        dup_ratio = len(duplicated) / len(non_transfer)
        if dup_ratio > 0.20:
            flags.append(Flag(
                rule_code="CONT_004",
                rule_description="High proportion of duplicate courses",
                severity="high",
                category="SP-5",
                rationale=(
                    f"{len(duplicated)} of {len(non_transfer)} courses "
                    f"({dup_ratio:.0%}) appear more than once, exceeding the 20% threshold. "
                    "A high volume of duplicate entries strongly suggests transcript padding "
                    "or fabrication."
                ),
                source_location=_src(agg, "courses"),
            ))

    return flags

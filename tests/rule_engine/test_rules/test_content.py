"""Unit tests for educational content rules (CONT_001 – CONT_004)."""

import os
import sys

import pytest

_RULE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "../../../services/rule_engine")
)
if _RULE_DIR not in sys.path:
    sys.path.insert(0, _RULE_DIR)

from rules.content import (  # noqa: E402
    check_cont_001,
    check_cont_002,
    check_cont_003,
    check_cont_004,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _flags_with_code(flags, code):
    return [f for f in flags if f.rule_code == code]


def _single_semester(term="Fall 2020", term_gpa=3.5, hours=12, cum_gpa=3.5,
                     term_type="fall"):
    return {
        "term": term,
        "term_type": term_type,
        "start_date": "2020-08-24",
        "end_date": "2020-12-15",
        "courses": ["NUR101", "NUR102"],
        "term_gpa_stated": term_gpa,
        "term_credit_hours_stated": hours,
        "cum_gpa_stated_after_term": cum_gpa,
    }


def _course(code, title, hours, grade_points=3.5, retake=False, transfer=False,
            start="2020-08-24", end="2020-12-15"):
    return {
        "name": f"{code} {title}",
        "course_code": code,
        "course_title": title,
        "credit_hours": hours,
        "grade_points": grade_points,
        "start_date": start,
        "end_date": end,
        "retake_marker": retake,
        "transfer_marker": transfer,
    }


# ── CONT_001 — Chronology Impossibility ──────────────────────────────────────

# Check 1: graduation before enrollment

def test_cont_001_check1_fires_grad_before_enrollment():
    agg = {"programs": [
        {"name": "ADN", "start_date": "2020-01-01", "end_date": "2019-06-01",
         "claimed_degree_type": "ADN"},
    ]}
    flags = check_cont_001(agg)
    assert any(f.rule_code == "CONT_001" and f.severity == "high"
               and "graduation" in f.rule_description.lower() for f in flags)


def test_cont_001_check1_no_fire_normal_program():
    agg = {"programs": [
        {"name": "ADN", "start_date": "2019-01-01", "end_date": "2021-06-01",
         "claimed_degree_type": "ADN"},
    ]}
    flags = check_cont_001(agg)
    assert not any("graduation" in f.rule_description.lower() for f in flags)


# Check 2: course end before course start

def test_cont_001_check2_fires_course_end_before_start():
    agg = {"courses": [
        _course("NUR101", "Fundamentals", 3, start="2020-08-24", end="2020-07-01"),
    ]}
    flags = check_cont_001(agg)
    assert any(f.rule_code == "CONT_001" and f.severity == "high"
               and "course" in f.rule_description.lower() for f in flags)


def test_cont_001_check2_no_fire_normal_course():
    agg = {"courses": [
        _course("NUR101", "Fundamentals", 3, start="2020-08-24", end="2020-12-15"),
    ]}
    flags = check_cont_001(agg)
    assert not any("course end" in f.rule_description.lower() for f in flags)


# Check 3: implausible age at enrollment

def test_cont_001_check3_fires_age_below_16_high_severity():
    agg = {
        "date_of_birth": "2010-01-01",
        "programs": [{"name": "ADN", "start_date": "2020-01-01",
                      "end_date": "2022-01-01", "claimed_degree_type": "ADN"}],
    }
    flags = check_cont_001(agg)
    assert any(f.rule_code == "CONT_001" and f.severity == "high"
               and "young" in f.rule_description.lower() for f in flags)


def test_cont_001_check3_fires_age_above_80_low_severity():
    agg = {
        "date_of_birth": "1930-01-01",
        "programs": [{"name": "ADN", "start_date": "2020-01-01",
                      "end_date": "2022-01-01", "claimed_degree_type": "ADN"}],
    }
    flags = check_cont_001(agg)
    assert any(f.rule_code == "CONT_001" and f.severity == "low"
               and "advanced" in f.rule_description.lower() for f in flags)


def test_cont_001_check3_no_fire_normal_age():
    agg = {
        "date_of_birth": "1990-01-01",
        "programs": [{"name": "ADN", "start_date": "2020-01-01",
                      "end_date": "2022-01-01", "claimed_degree_type": "ADN"}],
    }
    flags = check_cont_001(agg)
    assert not any("age" in f.rule_description.lower() for f in flags)


def test_cont_001_check3_fallback_no_dob():
    """Fallback: no date_of_birth → age check skipped."""
    agg = {"programs": [{"name": "ADN", "start_date": "2020-01-01",
                         "end_date": "2022-01-01", "claimed_degree_type": "ADN"}]}
    flags = check_cont_001(agg)
    assert not any("age" in f.rule_description.lower() for f in flags)


# Check 4: overlapping programs

def test_cont_001_check4_fires_overlapping_programs():
    agg = {"programs": [
        {"name": "ADN", "start_date": "2019-01-01", "end_date": "2021-06-01",
         "claimed_degree_type": "ADN"},
        {"name": "BSN", "start_date": "2020-01-01", "end_date": "2023-06-01",
         "claimed_degree_type": "BSN"},
    ]}
    flags = check_cont_001(agg)
    assert any(f.rule_code == "CONT_001" and f.severity == "high"
               and "overlap" in f.rule_description.lower() for f in flags)


def test_cont_001_check4_no_fire_sequential_programs():
    agg = {"programs": [
        {"name": "ADN", "start_date": "2019-01-01", "end_date": "2021-06-01",
         "claimed_degree_type": "ADN"},
        {"name": "RN-BSN", "start_date": "2021-09-01", "end_date": "2023-06-01",
         "claimed_degree_type": "RN-BSN"},
    ]}
    flags = check_cont_001(agg)
    assert not any("overlap" in f.rule_description.lower() for f in flags)


# Check 5: unexplained term gaps — tier-boundary tests

def test_cont_001_check5_tier_13_months_medium():
    """Gap > 12 months → MEDIUM."""
    semesters = [
        {
            "term": "Fall 2019", "term_type": "fall",
            "start_date": "2019-08-01", "end_date": "2019-12-15",
            "courses": [], "term_gpa_stated": 3.5,
            "term_credit_hours_stated": 12, "cum_gpa_stated_after_term": 3.5,
        },
        {
            "term": "Spring 2021", "term_type": "spring",
            "start_date": "2021-01-01", "end_date": "2021-05-15",
            "courses": [], "term_gpa_stated": 3.5,
            "term_credit_hours_stated": 12, "cum_gpa_stated_after_term": 3.5,
        },
    ]
    flags = check_cont_001({"semesters": semesters})
    gap_flags = [f for f in flags if "gap" in f.rule_description.lower()]
    assert any(f.severity == "medium" for f in gap_flags)


def test_cont_001_check5_tier_7_months_low():
    """Gap > 6 months but ≤ 12 months → LOW."""
    semesters = [
        {
            "term": "Fall 2019", "term_type": "fall",
            "start_date": "2019-08-01", "end_date": "2019-12-15",
            "courses": [], "term_gpa_stated": 3.5,
            "term_credit_hours_stated": 12, "cum_gpa_stated_after_term": 3.5,
        },
        {
            "term": "Summer 2020", "term_type": "summer",
            "start_date": "2020-07-01", "end_date": "2020-08-15",
            "courses": [], "term_gpa_stated": 3.5,
            "term_credit_hours_stated": 12, "cum_gpa_stated_after_term": 3.5,
        },
    ]
    flags = check_cont_001({"semesters": semesters})
    gap_flags = [f for f in flags if "gap" in f.rule_description.lower()]
    assert any(f.severity == "low" for f in gap_flags)


def test_cont_001_check5_no_fire_small_gap():
    """Gap ≤ 6 months → no flag."""
    semesters = [
        {
            "term": "Fall 2019", "term_type": "fall",
            "start_date": "2019-08-01", "end_date": "2019-12-15",
            "courses": [], "term_gpa_stated": 3.5,
            "term_credit_hours_stated": 12, "cum_gpa_stated_after_term": 3.5,
        },
        {
            "term": "Spring 2020", "term_type": "spring",
            "start_date": "2020-01-15", "end_date": "2020-05-15",
            "courses": [], "term_gpa_stated": 3.5,
            "term_credit_hours_stated": 12, "cum_gpa_stated_after_term": 3.5,
        },
    ]
    flags = check_cont_001({"semesters": semesters})
    assert not any("gap" in f.rule_description.lower() for f in flags)


def test_cont_001_check5_no_fire_gap_covered_by_loa():
    """LOA marker covering the gap → no gap flag."""
    semesters = [
        {
            "term": "Fall 2019", "term_type": "fall",
            "start_date": "2019-08-01", "end_date": "2019-12-15",
            "courses": [], "term_gpa_stated": 3.5,
            "term_credit_hours_stated": 12, "cum_gpa_stated_after_term": 3.5,
        },
        {
            "term": "Spring 2021", "term_type": "spring",
            "start_date": "2021-01-01", "end_date": "2021-05-15",
            "courses": [], "term_gpa_stated": 3.5,
            "term_credit_hours_stated": 12, "cum_gpa_stated_after_term": 3.5,
        },
    ]
    loa = [{"start_date": "2020-01-01", "end_date": "2021-01-01", "reason": "medical"}]
    flags = check_cont_001({"semesters": semesters, "leave_of_absence_markers": loa})
    assert not any("gap" in f.rule_description.lower() for f in flags)


# Check 6: future-dated events

def test_cont_001_check6_fires_future_date():
    agg = {
        "document_issue_date": "2021-01-01",
        "programs": [{"name": "ADN", "start_date": "2019-01-01",
                      "end_date": "2022-06-01", "claimed_degree_type": "ADN"}],
    }
    flags = check_cont_001(agg)
    assert any(f.rule_code == "CONT_001" and f.severity == "high"
               and "after" in f.rule_description.lower() for f in flags)


def test_cont_001_check6_no_fire_past_date():
    agg = {
        "document_issue_date": "2022-12-01",
        "programs": [{"name": "ADN", "start_date": "2019-01-01",
                      "end_date": "2021-06-01", "claimed_degree_type": "ADN"}],
    }
    flags = check_cont_001(agg)
    assert not any("after" in f.rule_description.lower() for f in flags)


# Advisory fallback

def test_cont_001_fallback_advisory_fires_when_no_structured_data():
    """If no structural checks fire but dates_chronology_ok == 'no', fire LOW advisory."""
    flags = check_cont_001({"dates_chronology_ok": "no"})
    assert any(f.rule_code == "CONT_001" and f.severity == "low"
               and "advisory" in f.rule_description.lower() for f in flags)


def test_cont_001_fallback_advisory_no_fire_when_ok():
    assert check_cont_001({"dates_chronology_ok": "yes"}) == []


def test_cont_001_fallback_advisory_suppressed_when_check_fires():
    """Advisory is suppressed when a structural check already fired."""
    agg = {
        "dates_chronology_ok": "no",
        "programs": [{"name": "ADN", "start_date": "2020-01-01",
                      "end_date": "2019-01-01", "claimed_degree_type": "ADN"}],
    }
    flags = check_cont_001(agg)
    advisory = [f for f in flags if "advisory" in f.rule_description.lower()]
    assert advisory == []


# Multiple checks simultaneously

def test_cont_001_multiple_checks_fire():
    agg = {
        "programs": [{"name": "ADN", "start_date": "2020-01-01",
                      "end_date": "2019-01-01", "claimed_degree_type": "ADN"}],
        "courses": [
            _course("NUR101", "Fundamentals", 3, start="2020-08-24", end="2020-07-01"),
        ],
    }
    flags = check_cont_001(agg)
    assert len(flags) >= 2


# ── CONT_002 — GPA Arithmetic Verification ───────────────────────────────────

def _make_gpa_agg(term_gpa_stated, term_hours, cum_gpa_stated,
                  course_grade_points, final_cum_gpa=None, scale_max=4.0):
    """Build a minimal agg dict with one semester and matching courses."""
    courses = [
        _course(f"NUR10{i}", f"Course {i}", 3, grade_points=course_grade_points)
        for i in range(1, 6)  # 5 courses × 3 hrs = 15 hrs
    ]
    sem = {
        "term": "Fall 2020",
        "term_type": "fall",
        "start_date": "2020-08-24",
        "end_date": "2020-12-15",
        "courses": [c["course_code"] for c in courses],
        "term_gpa_stated": term_gpa_stated,
        "term_credit_hours_stated": term_hours,
        "cum_gpa_stated_after_term": cum_gpa_stated,
    }
    # Override course credit hours to match term_hours across 5 courses
    for c in courses:
        c["credit_hours"] = term_hours / 5
    return {
        "semesters": [sem],
        "courses": courses,
        "final_cum_gpa_stated": final_cum_gpa or term_gpa_stated,
        "grading_scale_maximum": scale_max,
    }


# Check 1: per-semester term GPA mismatch tiers

def test_cont_002_check1_high_mismatch_over_5pct():
    """Stated 4.00, computed 3.78 → 5.5% → HIGH."""
    agg = _make_gpa_agg(
        term_gpa_stated=4.00, term_hours=15,
        cum_gpa_stated=4.00, course_grade_points=3.78,
        final_cum_gpa=4.00,
    )
    flags = check_cont_002(agg)
    assert any(f.severity == "high" and "term gpa" in f.rule_description.lower()
               for f in flags)


def test_cont_002_check1_medium_mismatch_2_to_5pct():
    """Stated 4.00, computed 3.92 → 2% → MEDIUM."""
    agg = _make_gpa_agg(
        term_gpa_stated=4.00, term_hours=15,
        cum_gpa_stated=4.00, course_grade_points=3.92,
        final_cum_gpa=4.00,
    )
    flags = check_cont_002(agg)
    assert any(f.severity == "medium" and "term gpa" in f.rule_description.lower()
               for f in flags)


def test_cont_002_check1_no_fire_exact_match():
    agg = _make_gpa_agg(
        term_gpa_stated=3.5, term_hours=15,
        cum_gpa_stated=3.5, course_grade_points=3.5,
        final_cum_gpa=3.5,
    )
    flags = check_cont_002(agg)
    assert not any("term gpa" in f.rule_description.lower() for f in flags)


# Tier boundary tests

def test_cont_002_tier_boundary_4_9pct_is_medium():
    """4.9% mismatch → MEDIUM, not HIGH."""
    # stated=4.00, computed = 4.00 * (1 - 0.049) = 3.804
    agg = _make_gpa_agg(
        term_gpa_stated=4.00, term_hours=15,
        cum_gpa_stated=4.00, course_grade_points=3.804,
        final_cum_gpa=4.00,
    )
    flags = check_cont_002(agg)
    term_flags = [f for f in flags if "term gpa" in f.rule_description.lower()]
    assert term_flags, "Expected at least one term GPA flag"
    severities = {f.severity for f in term_flags}
    assert "medium" in severities
    assert "high" not in severities


def test_cont_002_tier_boundary_5_1pct_is_high():
    """5.1% mismatch → HIGH."""
    # stated=4.00, computed = 4.00 * (1 - 0.051) = 3.796
    agg = _make_gpa_agg(
        term_gpa_stated=4.00, term_hours=15,
        cum_gpa_stated=4.00, course_grade_points=3.796,
        final_cum_gpa=4.00,
    )
    flags = check_cont_002(agg)
    term_flags = [f for f in flags if "term gpa" in f.rule_description.lower()]
    assert any(f.severity == "high" for f in term_flags)


# Check 2: rolling cumulative GPA mismatch

def test_cont_002_check2_fires_cum_gpa_high_mismatch():
    """After two terms, cum GPA > 5% off from weighted average."""
    sems = [
        {
            "term": "Fall 2020", "term_type": "fall",
            "start_date": "2020-08-24", "end_date": "2020-12-15",
            "courses": [f"NUR10{i}" for i in range(1, 6)],
            "term_gpa_stated": 3.5, "term_credit_hours_stated": 15,
            "cum_gpa_stated_after_term": 3.5,
        },
        {
            "term": "Spring 2021", "term_type": "spring",
            "start_date": "2021-01-15", "end_date": "2021-05-15",
            "courses": [f"NUR20{i}" for i in range(1, 6)],
            "term_gpa_stated": 3.5, "term_credit_hours_stated": 15,
            "cum_gpa_stated_after_term": 4.0,  # inflated
        },
    ]
    courses = [
        _course(f"NUR10{i}", f"Course {i}", 3, grade_points=3.5)
        for i in range(1, 6)
    ] + [
        _course(f"NUR20{i}", f"Course {i}", 3, grade_points=3.5)
        for i in range(1, 6)
    ]
    agg = {"semesters": sems, "courses": courses, "grading_scale_maximum": 4.0}
    flags = check_cont_002(agg)
    assert any("cumulative gpa" in f.rule_description.lower() and f.severity == "high"
               for f in flags)


# Check 3: final cum GPA mismatch

def test_cont_002_check3_fires_final_gpa_high_over_10pct():
    """Final stated GPA 4.0, computed 3.5 → 12.5% → HIGH."""
    courses = [_course(f"NUR10{i}", f"Course {i}", 3, grade_points=3.5) for i in range(1, 6)]
    agg = {
        "courses": courses,
        "final_cum_gpa_stated": 4.0,
        "grading_scale_maximum": 4.0,
    }
    flags = check_cont_002(agg)
    assert any("final" in f.rule_description.lower() and f.severity == "high"
               for f in flags)


def test_cont_002_check3_fires_final_gpa_medium_5_to_10pct():
    """Final stated GPA 4.0, computed 3.72 → 7% → MEDIUM."""
    courses = [_course(f"NUR10{i}", f"Course {i}", 3, grade_points=3.72) for i in range(1, 6)]
    agg = {
        "courses": courses,
        "final_cum_gpa_stated": 4.0,
        "grading_scale_maximum": 4.0,
    }
    flags = check_cont_002(agg)
    assert any("final" in f.rule_description.lower() and f.severity == "medium"
               for f in flags)


# Check 4: term-to-cum reconciliation failure

def test_cont_002_check4_fires_reconciliation_failure():
    sems = [
        {
            "term": "Fall 2020", "term_type": "fall",
            "start_date": "2020-08-24", "end_date": "2020-12-15",
            "courses": [], "term_gpa_stated": 3.5, "term_credit_hours_stated": 15,
            "cum_gpa_stated_after_term": 3.5,
        },
        {
            "term": "Spring 2021", "term_type": "spring",
            "start_date": "2021-01-15", "end_date": "2021-05-15",
            "courses": [], "term_gpa_stated": 3.5, "term_credit_hours_stated": 15,
            "cum_gpa_stated_after_term": 3.5,
        },
    ]
    agg = {
        "semesters": sems,
        "final_cum_gpa_stated": 4.0,  # Should be 3.5 from weighted average
        "grading_scale_maximum": 4.0,
    }
    flags = check_cont_002(agg)
    assert any("reconcil" in f.rule_description.lower() and f.severity == "high"
               for f in flags)


def test_cont_002_check4_no_fire_consistent_reconciliation():
    sems = [
        {
            "term": "Fall 2020", "term_type": "fall",
            "start_date": "2020-08-24", "end_date": "2020-12-15",
            "courses": [], "term_gpa_stated": 3.5, "term_credit_hours_stated": 15,
            "cum_gpa_stated_after_term": 3.5,
        },
    ]
    agg = {
        "semesters": sems,
        "final_cum_gpa_stated": 3.5,
        "grading_scale_maximum": 4.0,
    }
    flags = check_cont_002(agg)
    assert not any("reconcil" in f.rule_description.lower() for f in flags)


# Check 5: GPA exceeds scale maximum

def test_cont_002_check5_fires_gpa_exceeds_scale():
    sems = [_single_semester(term_gpa=4.5, cum_gpa=4.5)]
    agg = {"semesters": sems, "grading_scale_maximum": 4.0}
    flags = check_cont_002(agg)
    assert any("exceeds" in f.rule_description.lower() and f.severity == "high"
               for f in flags)


def test_cont_002_check5_no_fire_within_scale():
    sems = [_single_semester(term_gpa=3.9, cum_gpa=3.9)]
    agg = {"semesters": sems, "grading_scale_maximum": 4.0}
    assert not any("exceeds" in f.rule_description.lower()
                   for f in check_cont_002(agg))


# Check 6: suspicious perfection

def test_cont_002_check6_fires_all_4_0_over_40_credits():
    sems = [
        _single_semester("Fall 2019", term_gpa=4.0, hours=15, cum_gpa=4.0),
        _single_semester("Spring 2020", term_gpa=4.0, hours=15, cum_gpa=4.0),
        _single_semester("Fall 2020", term_gpa=4.0, hours=12, cum_gpa=4.0),
    ]
    agg = {"semesters": sems, "grading_scale_maximum": 4.0, "final_cum_gpa_stated": 4.0}
    flags = check_cont_002(agg)
    assert any("perfect" in f.rule_description.lower() and f.severity == "low"
               for f in flags)


def test_cont_002_check6_no_fire_fewer_than_40_credits():
    sems = [_single_semester(term_gpa=4.0, hours=12, cum_gpa=4.0)]
    agg = {"semesters": sems, "grading_scale_maximum": 4.0, "final_cum_gpa_stated": 4.0}
    flags = check_cont_002(agg)
    assert not any("perfect" in f.rule_description.lower() for f in flags)


# Check 7: monotonic trend (all identical to 2 decimal places)

def test_cont_002_check7_fires_all_identical():
    sems = [
        _single_semester("Fall 2019", term_gpa=3.33, hours=15, cum_gpa=3.33),
        _single_semester("Spring 2020", term_gpa=3.33, hours=15, cum_gpa=3.33),
        _single_semester("Fall 2020", term_gpa=3.33, hours=15, cum_gpa=3.33),
    ]
    agg = {"semesters": sems, "grading_scale_maximum": 4.0, "final_cum_gpa_stated": 3.33}
    flags = check_cont_002(agg)
    assert any("identical" in f.rule_description.lower() and f.severity == "low"
               for f in flags)


def test_cont_002_check7_no_fire_varying_gpas():
    sems = [
        _single_semester("Fall 2019", term_gpa=3.0, hours=15, cum_gpa=3.0),
        _single_semester("Spring 2020", term_gpa=3.5, hours=15, cum_gpa=3.25),
        _single_semester("Fall 2020", term_gpa=3.7, hours=15, cum_gpa=3.4),
    ]
    agg = {"semesters": sems, "grading_scale_maximum": 4.0, "final_cum_gpa_stated": 3.4}
    flags = check_cont_002(agg)
    assert not any("identical" in f.rule_description.lower() for f in flags)


# Fallbacks

def test_cont_002_fallback_no_semesters_runs_only_3_and_5():
    """Without semester structure, only Checks 3 and 5 can fire."""
    courses = [_course(f"NUR10{i}", f"Course {i}", 3, grade_points=3.5) for i in range(1, 6)]
    agg = {
        "courses": courses,
        "final_cum_gpa_stated": 4.0,  # Check 3 fires (12.5%)
        "grading_scale_maximum": 4.0,
    }
    flags = check_cont_002(agg)
    assert any("final" in f.rule_description.lower() for f in flags)
    # Checks 1, 2, 4, 6, 7 need semesters and must not fire
    assert not any("term gpa" in f.rule_description.lower() for f in flags)
    assert not any("reconcil" in f.rule_description.lower() for f in flags)


def test_cont_002_fallback_pass_fail_skips_rule():
    agg = {
        "grading_scale_format": "pass_fail",
        "semesters": [_single_semester()],
        "final_cum_gpa_stated": 4.0,
    }
    assert check_cont_002(agg) == []


def test_cont_002_fallback_fewer_than_5_grades_skips_checks_1_and_2():
    """If fewer than 5 numeric grades, Checks 1 and 2 are skipped."""
    courses = [
        _course(f"NUR10{i}", f"Course {i}", 3, grade_points=3.5)
        for i in range(1, 4)  # only 3 graded courses
    ]
    sem = {
        "term": "Fall 2020", "term_type": "fall",
        "start_date": "2020-08-24", "end_date": "2020-12-15",
        "courses": [c["course_code"] for c in courses],
        "term_gpa_stated": 4.0, "term_credit_hours_stated": 9,
        "cum_gpa_stated_after_term": 4.0,
    }
    agg = {"semesters": [sem], "courses": courses, "final_cum_gpa_stated": 3.5}
    flags = check_cont_002(agg)
    assert not any("term gpa" in f.rule_description.lower() for f in flags)
    assert not any("cumulative gpa mismatch after" in f.rule_description.lower() for f in flags)


# Multiple checks simultaneously

def test_cont_002_multiple_checks_fire():
    """All 4.0 GPAs > 40 credits with scale max violated too."""
    sems = [
        _single_semester("Fall 2019", term_gpa=4.5, hours=15, cum_gpa=4.5),
        _single_semester("Spring 2020", term_gpa=4.5, hours=15, cum_gpa=4.5),
        _single_semester("Fall 2020", term_gpa=4.5, hours=15, cum_gpa=4.5),
    ]
    agg = {
        "semesters": sems,
        "final_cum_gpa_stated": 4.5,
        "grading_scale_maximum": 4.0,
    }
    flags = check_cont_002(agg)
    rule_descs = {f.rule_description for f in flags}
    assert any("exceeds" in d.lower() for d in rule_descs)


# ── CONT_003 — Program Duration Plausibility ─────────────────────────────────

def _prog(start, end, degree="ADN"):
    return {"name": f"Nursing {degree}", "start_date": start, "end_date": end,
            "claimed_degree_type": degree}


# Check 1: duration below minimum

def test_cont_003_check1_fires_below_minimum():
    """ADN minimum is 18 months; 5 months → HIGH."""
    agg = {
        "claimed_degree_type": "ADN",
        "programs": [_prog("2019-01-01", "2019-06-01")],
    }
    flags = check_cont_003(agg)
    assert any(f.rule_code == "CONT_003" and f.severity == "high"
               and "below minimum" in f.rule_description.lower() for f in flags)


def test_cont_003_check1_no_fire_rn_bsn_bridge_short_duration():
    """RN-BSN bridge minimum is 9 months; 10 months → no fire on Check 1."""
    agg = {
        "claimed_degree_type": "RN-BSN",
        "programs": [_prog("2021-01-01", "2021-11-01", "RN-BSN")],
    }
    flags = check_cont_003(agg)
    assert not any("below minimum" in f.rule_description.lower() for f in flags)


def test_cont_003_check1_no_fire_lpn_rn_bridge_short_duration():
    """LPN-RN bridge minimum is 9 months; 10 months → no fire on Check 1."""
    agg = {
        "claimed_degree_type": "LPN-RN",
        "programs": [_prog("2021-01-01", "2021-11-01", "LPN-RN")],
    }
    flags = check_cont_003(agg)
    assert not any("below minimum" in f.rule_description.lower() for f in flags)


def test_cont_003_check1_rn_bsn_fires_when_actually_too_short():
    """RN-BSN minimum is 9 months; 5 months → does fire."""
    agg = {
        "claimed_degree_type": "RN-BSN",
        "programs": [_prog("2021-01-01", "2021-06-01", "RN-BSN")],
    }
    flags = check_cont_003(agg)
    assert any("below minimum" in f.rule_description.lower() for f in flags)


# Check 2: duration above maximum

def test_cont_003_check2_fires_above_maximum():
    """ADN maximum is 48 months; 60 months → MEDIUM."""
    agg = {
        "claimed_degree_type": "ADN",
        "programs": [_prog("2015-01-01", "2020-01-01")],
    }
    flags = check_cont_003(agg)
    assert any(f.rule_code == "CONT_003" and f.severity == "medium"
               and "above maximum" in f.rule_description.lower() for f in flags)


def test_cont_003_check2_no_fire_within_range():
    agg = {
        "claimed_degree_type": "ADN",
        "programs": [_prog("2019-01-01", "2021-01-01")],  # 24 months, within 18–48
    }
    flags = check_cont_003(agg)
    assert not any("above maximum" in f.rule_description.lower() for f in flags)


# Check 3: credit-hour pace implausible

def test_cont_003_check3_fires_high_pace():
    """120 credit hours in 4 months → 30 ch/month > 15 → HIGH."""
    agg = {
        "claimed_degree_type": "ADN",
        "programs": [_prog("2020-01-01", "2020-05-01")],
        "total_credit_hours_stated": 120,
    }
    flags = check_cont_003(agg)
    assert any(f.rule_code == "CONT_003" and f.severity == "high"
               and "pace" in f.rule_description.lower() for f in flags)


def test_cont_003_check3_no_fire_reasonable_pace():
    """68 credit hours in 24 months → 2.8 ch/month → no flag."""
    agg = {
        "claimed_degree_type": "ADN",
        "programs": [_prog("2019-01-01", "2021-01-01")],
        "total_credit_hours_stated": 68,
    }
    flags = check_cont_003(agg)
    assert not any("pace" in f.rule_description.lower() for f in flags)


def test_cont_003_check3_fallback_no_credit_hours():
    """Fallback: total_credit_hours_stated missing → skip Check 3."""
    agg = {
        "claimed_degree_type": "ADN",
        "programs": [_prog("2020-01-01", "2020-05-01")],
        # no total_credit_hours_stated
    }
    flags = check_cont_003(agg)
    assert not any("pace" in f.rule_description.lower() for f in flags)


# Check 4: summer-only completion

def test_cont_003_check4_fires_summer_only():
    sems = [
        {
            "term": "Summer 2019", "term_type": "summer",
            "start_date": "2019-06-01", "end_date": "2019-08-15",
            "courses": [], "term_gpa_stated": 3.5,
            "term_credit_hours_stated": 12, "cum_gpa_stated_after_term": 3.5,
        },
        {
            "term": "Summer 2020", "term_type": "summer",
            "start_date": "2020-06-01", "end_date": "2020-08-15",
            "courses": [], "term_gpa_stated": 3.5,
            "term_credit_hours_stated": 12, "cum_gpa_stated_after_term": 3.5,
        },
    ]
    agg = {
        "claimed_degree_type": "ADN",
        "programs": [_prog("2019-01-01", "2021-01-01")],
        "semesters": sems,
    }
    flags = check_cont_003(agg)
    assert any(f.rule_code == "CONT_003" and f.severity == "low"
               and "summer" in f.rule_description.lower() for f in flags)


def test_cont_003_check4_no_fire_mixed_terms():
    sems = [
        _single_semester("Fall 2019", term_type="fall"),
        {
            "term": "Summer 2020", "term_type": "summer",
            "start_date": "2020-06-01", "end_date": "2020-08-15",
            "courses": [], "term_gpa_stated": 3.5,
            "term_credit_hours_stated": 12, "cum_gpa_stated_after_term": 3.5,
        },
    ]
    agg = {
        "claimed_degree_type": "ADN",
        "programs": [_prog("2019-01-01", "2021-01-01")],
        "semesters": sems,
    }
    flags = check_cont_003(agg)
    assert not any("summer" in f.rule_description.lower() for f in flags)


def test_cont_003_check4_fallback_no_semesters():
    """Fallback: semester term types missing → skip Check 4."""
    agg = {
        "claimed_degree_type": "ADN",
        "programs": [_prog("2019-01-01", "2021-01-01")],
        # no semesters
    }
    flags = check_cont_003(agg)
    assert not any("summer" in f.rule_description.lower() for f in flags)


# Check 5: unexplained extension

def test_cont_003_check5_fires_duration_over_max_no_loa():
    """ADN max is 48 months; 60 months, no LOA → MEDIUM."""
    agg = {
        "claimed_degree_type": "ADN",
        "programs": [_prog("2015-01-01", "2020-01-01")],
        # no leave_of_absence_markers
    }
    flags = check_cont_003(agg)
    assert any(f.rule_code == "CONT_003" and f.severity == "medium"
               and "unexplained" in f.rule_description.lower() for f in flags)


def test_cont_003_check5_no_fire_when_loa_present():
    """Fallback: LOA markers present → skip Check 5."""
    agg = {
        "claimed_degree_type": "ADN",
        "programs": [_prog("2015-01-01", "2020-01-01")],
        "leave_of_absence_markers": [{"start_date": "2017-01-01",
                                      "end_date": "2019-01-01", "reason": "medical"}],
    }
    flags = check_cont_003(agg)
    assert not any("unexplained" in f.rule_description.lower() for f in flags)


# Fallbacks

def test_cont_003_fallback_unclear_degree_skips_rule():
    agg = {
        "claimed_degree_type": "unclear",
        "programs": [_prog("2019-01-01", "2019-02-01")],
    }
    assert check_cont_003(agg) == []


def test_cont_003_fallback_missing_degree_skips_rule():
    agg = {"programs": [_prog("2019-01-01", "2019-02-01")]}
    assert check_cont_003(agg) == []


# Multiple checks simultaneously

def test_cont_003_multiple_checks_fire():
    """Below minimum AND high pace fire together."""
    agg = {
        "claimed_degree_type": "ADN",
        "programs": [_prog("2020-01-01", "2020-05-01")],  # 4 months (below 18)
        "total_credit_hours_stated": 120,  # 30 ch/month > 15
    }
    flags = check_cont_003(agg)
    descs = {f.rule_description for f in flags}
    assert any("below minimum" in d.lower() for d in descs)
    assert any("pace" in d.lower() for d in descs)


# ── CONT_004 — Duplicate Course Detection ────────────────────────────────────

# Check 1: exact duplication without retake

def test_cont_004_check1_fires_exact_duplicate_no_retake():
    courses = [
        _course("NUR101", "Fundamentals of Nursing", 3),
        _course("NUR101", "Fundamentals of Nursing", 3),  # duplicate
    ]
    agg = {"courses": courses}
    flags = check_cont_004(agg)
    assert any(f.rule_code == "CONT_004" and f.severity == "high"
               and "NUR101" in f.rule_description for f in flags)


def test_cont_004_check1_no_fire_with_retake_marker():
    """Retake marker on one instance → not counted as duplicate for Check 1."""
    courses = [
        _course("NUR101", "Fundamentals of Nursing", 3, retake=False),
        _course("NUR101", "Fundamentals of Nursing", 3, retake=True),
    ]
    agg = {"courses": courses}
    flags = check_cont_004(agg)
    # Only one without retake → below threshold of 2
    check1_flags = [f for f in flags if "NUR101" in f.rule_description]
    assert check1_flags == []


def test_cont_004_check1_no_fire_transfer_credits():
    """Transfer marker → excluded from duplicate analysis entirely."""
    courses = [
        _course("NUR101", "Fundamentals of Nursing", 3, transfer=False),
        _course("NUR101", "Fundamentals of Nursing", 3, transfer=True),
    ]
    agg = {"courses": courses}
    flags = check_cont_004(agg)
    check1_flags = [f for f in flags if "NUR101" in f.rule_description]
    assert check1_flags == []


def test_cont_004_check1_fallback_no_course_codes():
    """Fallback: no course codes extracted → skip Check 1."""
    courses = [
        {"name": "Fundamentals", "course_code": None, "course_title": "Fundamentals",
         "credit_hours": 3, "grade_points": 3.5, "start_date": None, "end_date": None,
         "retake_marker": False, "transfer_marker": False},
        {"name": "Fundamentals", "course_code": None, "course_title": "Fundamentals",
         "credit_hours": 3, "grade_points": 3.5, "start_date": None, "end_date": None,
         "retake_marker": False, "transfer_marker": False},
    ]
    agg = {"courses": courses}
    flags = check_cont_004(agg)
    # Check 1 must not fire (no course codes)
    assert not any("NUR" in f.rule_description for f in flags)


def test_cont_004_check1_no_retake_marker_treated_as_no_marker():
    """Fallback: retake_marker not extracted (None) → treated as no marker present."""
    courses = [
        {"name": "NUR101 Fundamentals", "course_code": "NUR101",
         "course_title": "Fundamentals", "credit_hours": 3, "grade_points": 3.5,
         "start_date": None, "end_date": None,
         "retake_marker": None, "transfer_marker": False},
        {"name": "NUR101 Fundamentals", "course_code": "NUR101",
         "course_title": "Fundamentals", "credit_hours": 3, "grade_points": 3.5,
         "start_date": None, "end_date": None,
         "retake_marker": None, "transfer_marker": False},
    ]
    agg = {"courses": courses}
    flags = check_cont_004(agg)
    assert any("NUR101" in f.rule_description for f in flags)


# Check 2: duplicate volume threshold

def test_cont_004_check2_fires_high_duplicate_volume():
    """6 of 7 unique course identifiers duplicated → ~86% > 20%."""
    courses = []
    for i in range(1, 8):
        code = f"NUR10{i}"
        courses.append(_course(code, f"Course {i}", 3))
        courses.append(_course(code, f"Course {i}", 3))  # each duplicated
    agg = {"courses": courses}
    flags = check_cont_004(agg)
    assert any("proportion" in f.rule_description.lower() and f.severity == "high"
               for f in flags)


def test_cont_004_check2_no_fire_low_duplicate_volume():
    """1 duplicate out of 10 courses → 10% ≤ 20%."""
    courses = [_course(f"NUR10{i}", f"Course {i}", 3) for i in range(1, 10)]
    courses.append(_course("NUR101", "Course 1", 3))  # one duplicate
    agg = {"courses": courses}
    flags = check_cont_004(agg)
    assert not any("proportion" in f.rule_description.lower() for f in flags)


def test_cont_004_transfer_credits_excluded_from_volume_check():
    """TR/TRANSFER courses must not count toward duplicate volume."""
    courses = []
    for i in range(1, 11):
        code = f"NUR10{i}"
        courses.append(_course(code, f"Course {i}", 3, transfer=False))
        courses.append(_course(code, f"Course {i}", 3, transfer=True))  # transfer, excluded
    agg = {"courses": courses}
    flags = check_cont_004(agg)
    # Without transfer courses, 10 non-transfer courses with no duplicates
    assert not any("proportion" in f.rule_description.lower() for f in flags)


# Multiple checks fire simultaneously

def test_cont_004_multiple_checks_fire():
    """Many exact duplicates → both Check 1 and Check 2 fire."""
    courses = []
    for i in range(1, 8):
        code = f"NUR10{i}"
        for _ in range(3):  # each code appears 3 times, no retake
            courses.append(_course(code, f"Course {i}", 3))
    agg = {"courses": courses}
    flags = check_cont_004(agg)
    descs = {f.rule_description for f in flags}
    assert any("duplicate" in d.lower() and "NUR" in d for d in descs)
    assert any("proportion" in d.lower() for d in descs)


def test_cont_004_no_fire_clean_courses():
    courses = [_course(f"NUR10{i}", f"Course {i}", 3) for i in range(1, 9)]
    assert check_cont_004({"courses": courses}) == []

"""Unit tests for educational content rules (CONT_001 – CONT_006)."""

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
    check_cont_005,
    check_cont_006,
)

# ── CONT_001 — Grade scale mismatch ───────────────────────────────────────────


def test_cont_001_fires_letter_grade_on_french_doc():
    agg = {"grading_scale_format": "letter_grade_us", "language_of_issue": "french"}
    flags = check_cont_001(agg)
    assert len(flags) == 1
    assert flags[0].rule_code == "CONT_001"
    assert flags[0].severity == "high"


def test_cont_001_fires_20pt_on_english_doc():
    agg = {"grading_scale_format": "20_point_french", "language_of_issue": "english"}
    flags = check_cont_001(agg)
    assert len(flags) == 1


def test_cont_001_no_fire_letter_grade_english():
    agg = {"grading_scale_format": "letter_grade_us", "language_of_issue": "english"}
    assert check_cont_001(agg) == []


def test_cont_001_no_fire_20pt_french():
    agg = {"grading_scale_format": "20_point_french", "language_of_issue": "french"}
    assert check_cont_001(agg) == []


def test_cont_001_no_fire_unclear_scale():
    agg = {"grading_scale_format": "unclear", "language_of_issue": "french"}
    assert check_cont_001(agg) == []


def test_cont_001_no_fire_unknown_language():
    agg = {"grading_scale_format": "letter_grade_us", "language_of_issue": "other"}
    assert check_cont_001(agg) == []


def test_cont_001_no_fire_missing_fields():
    assert check_cont_001({}) == []


def test_cont_001_rationale_mentions_both_values():
    flag = check_cont_001({
        "grading_scale_format": "letter_grade_us",
        "language_of_issue": "french",
    })[0]
    assert "letter_grade_us" in flag.rationale
    assert "french" in flag.rationale


# ── CONT_002 — Age/date chronology ────────────────────────────────────────────


def test_cont_002_fires_on_enrollment_implausibly_early():
    agg = {
        "dates_chronology_ok": "no",
        "dates_chronology_issue": "enrollment_implausibly_early",
    }
    flags = check_cont_002(agg)
    assert len(flags) == 1
    assert flags[0].rule_code == "CONT_002"
    assert flags[0].severity == "high"


def test_cont_002_fires_on_overlap():
    agg = {"dates_chronology_ok": "no", "dates_chronology_issue": "overlap"}
    assert len(check_cont_002(agg)) == 1


def test_cont_002_no_fire_when_ok():
    agg = {"dates_chronology_ok": "yes"}
    assert check_cont_002(agg) == []


def test_cont_002_no_fire_when_unclear():
    agg = {"dates_chronology_ok": "unclear"}
    assert check_cont_002(agg) == []


def test_cont_002_no_fire_missing_field():
    assert check_cont_002({}) == []


# ── CONT_003 — Non-nursing / duplicate courses ────────────────────────────────


def test_cont_003_fires_on_predominantly_non_nursing():
    agg = {"course_relevance": "predominantly_non_nursing", "suspicious_course_names": []}
    flags = check_cont_003(agg)
    assert any(f.rule_code == "CONT_003" for f in flags)


def test_cont_003_fires_on_mixed_with_suspicious_names():
    agg = {
        "course_relevance": "mixed_with_non_nursing",
        "suspicious_course_names": ["Bandaging", "Theater techniques & surgery"],
    }
    flags = check_cont_003(agg)
    course_flags = [f for f in flags if f.rule_code == "CONT_003"]
    assert len(course_flags) >= 1
    assert "Bandaging" in course_flags[0].rationale


def test_cont_003_fires_on_duplicate_courses():
    agg = {
        "course_relevance": "nursing_standard",
        "duplicate_courses_detected": "yes",
        "suspicious_course_names": [],
    }
    flags = check_cont_003(agg)
    assert any("Duplicate" in f.rule_description for f in flags)


def test_cont_003_fires_twice_for_both_signals():
    """Both non-nursing content and duplicates should each produce a flag."""
    agg = {
        "course_relevance": "predominantly_non_nursing",
        "duplicate_courses_detected": "yes",
        "suspicious_course_names": ["Bandaging"],
    }
    flags = check_cont_003(agg)
    assert len(flags) == 2


def test_cont_003_no_fire_clean():
    agg = {
        "course_relevance": "nursing_standard",
        "duplicate_courses_detected": "no",
        "suspicious_course_names": [],
    }
    assert check_cont_003(agg) == []


def test_cont_003_rationale_mentions_case_b():
    agg = {
        "course_relevance": "predominantly_non_nursing",
        "suspicious_course_names": [],
    }
    flag = check_cont_003(agg)[0]
    assert "Case B" in flag.rationale


# ── CONT_004 — Language of issue mismatch ─────────────────────────────────────


def test_cont_004_fires_french_doc_from_nigeria():
    agg = {
        "language_of_issue": "french",
        "country_of_study": "nigeria",
        "declared_language_of_instruction": None,
    }
    flags = check_cont_004(agg)
    assert len(flags) == 1
    assert flags[0].rule_code == "CONT_004"
    assert flags[0].severity == "medium"


def test_cont_004_no_fire_english_nigeria():
    agg = {
        "language_of_issue": "english",
        "country_of_study": "nigeria",
    }
    assert check_cont_004(agg) == []


def test_cont_004_no_fire_french_france():
    agg = {
        "language_of_issue": "french",
        "country_of_study": "france",
    }
    assert check_cont_004(agg) == []


def test_cont_004_no_fire_declared_instruction_language_accepted():
    """If declared instruction language matches doc language, no flag."""
    agg = {
        "language_of_issue": "french",
        "country_of_study": "nigeria",
        "declared_language_of_instruction": "french",
    }
    assert check_cont_004(agg) == []


def test_cont_004_no_fire_unknown_country():
    """No flag for unknown countries — not enough reference data."""
    agg = {
        "language_of_issue": "french",
        "country_of_study": "atlantis",
    }
    assert check_cont_004(agg) == []


def test_cont_004_no_fire_missing_country():
    agg = {"language_of_issue": "french"}
    assert check_cont_004(agg) == []


# ── CONT_005 — GPA arithmetic inconsistency ───────────────────────────────────


def test_cont_005_fires_on_inconsistent():
    flags = check_cont_005({"gpa_arithmetic_consistency": "inconsistent"})
    assert len(flags) == 1
    assert flags[0].rule_code == "CONT_005"
    assert flags[0].severity == "high"


def test_cont_005_no_fire_consistent():
    assert check_cont_005({"gpa_arithmetic_consistency": "consistent"}) == []


def test_cont_005_no_fire_unclear():
    assert check_cont_005({"gpa_arithmetic_consistency": "unclear"}) == []


def test_cont_005_no_fire_missing():
    assert check_cont_005({}) == []


def test_cont_005_rationale_mentions_case_a():
    flag = check_cont_005({"gpa_arithmetic_consistency": "inconsistent"})[0]
    assert "Case A" in flag.rationale


# ── CONT_006 — Enrollment duration anomaly ────────────────────────────────────


def test_cont_006_fires_on_unusually_short():
    flags = check_cont_006({"program_duration_consistency": "unusually_short"})
    assert len(flags) == 1
    assert flags[0].rule_code == "CONT_006"
    assert flags[0].severity == "medium"
    assert "shorter" in flags[0].rationale


def test_cont_006_fires_on_unusually_long():
    flags = check_cont_006({"program_duration_consistency": "unusually_long"})
    assert len(flags) == 1
    assert "longer" in flags[0].rationale


def test_cont_006_no_fire_consistent():
    assert check_cont_006({"program_duration_consistency": "consistent_with_degree"}) == []


def test_cont_006_no_fire_missing():
    assert check_cont_006({}) == []

"""Unit tests for program/institution rules (PROG_001 – PROG_003)."""

import os
import sys

import pytest

_RULE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "../../../services/rule_engine")
)
if _RULE_DIR not in sys.path:
    sys.path.insert(0, _RULE_DIR)

from rules.program import (  # noqa: E402
    check_prog_001,
    check_prog_002,
    check_prog_003,
)

# ── PROG_001 — Diploma mill / unaccredited program ────────────────────────────


def test_prog_001_fires_diploma_mill_yes():
    agg = {
        "diploma_mill_language_detected": "yes",
        "diploma_mill_phrases_found": ["No Need To Study"],
        "accreditation_claim": "ACEN",
    }
    flags = check_prog_001(agg)
    mill_flags = [f for f in flags if "Diploma mill" in f.rule_description]
    assert len(mill_flags) == 1
    assert mill_flags[0].severity == "high"
    assert "No Need To Study" in mill_flags[0].rationale


def test_prog_001_fires_diploma_mill_possible():
    agg = {
        "diploma_mill_language_detected": "possible",
        "diploma_mill_phrases_found": [],
        "accreditation_claim": "ACEN",
    }
    flags = check_prog_001(agg)
    assert any("Diploma mill" in f.rule_description for f in flags)


def test_prog_001_no_fire_diploma_mill_no():
    agg = {
        "diploma_mill_language_detected": "no",
        "accreditation_claim": "ACEN",
    }
    flags = check_prog_001(agg)
    # Should not fire for diploma mill, but may fire for accreditor — ACEN is approved
    mill_flags = [f for f in flags if "Diploma mill" in f.rule_description]
    assert mill_flags == []


def test_prog_001_fires_unknown_accreditor():
    agg = {
        "diploma_mill_language_detected": "no",
        "accreditation_claim": "Unknown Nursing Board of the Internet",
    }
    flags = check_prog_001(agg)
    accred_flags = [f for f in flags if "accreditation" in f.rule_description.lower()]
    assert len(accred_flags) == 1


def test_prog_001_fires_empty_accreditor():
    agg = {
        "diploma_mill_language_detected": "no",
        "accreditation_claim": "",
    }
    flags = check_prog_001(agg)
    accred_flags = [f for f in flags if "accreditation" in f.rule_description.lower()]
    assert len(accred_flags) == 1


def test_prog_001_no_fire_acen_accreditor():
    agg = {
        "diploma_mill_language_detected": "no",
        "accreditation_claim": "ACEN",
    }
    flags = check_prog_001(agg)
    accred_flags = [f for f in flags if "accreditation" in f.rule_description.lower()]
    assert accred_flags == []


def test_prog_001_no_fire_ccne_accreditor():
    agg = {
        "diploma_mill_language_detected": "no",
        "accreditation_claim": "ccne",  # lower-case should still match
    }
    flags = check_prog_001(agg)
    accred_flags = [f for f in flags if "accreditation" in f.rule_description.lower()]
    assert accred_flags == []


def test_prog_001_two_flags_mill_and_unknown_accreditor():
    agg = {
        "diploma_mill_language_detected": "yes",
        "diploma_mill_phrases_found": ["life experience degree"],
        "accreditation_claim": "Global Online Nursing Board",
    }
    flags = check_prog_001(agg)
    assert len(flags) == 2


# ── PROG_002 — Missing graduation confirmation ────────────────────────────────


def test_prog_002_fires_when_absent():
    flags = check_prog_002({"graduation_confirmation_present": "no"})
    assert len(flags) == 1
    assert flags[0].rule_code == "PROG_002"
    assert flags[0].severity == "high"


def test_prog_002_no_fire_when_present():
    assert check_prog_002({"graduation_confirmation_present": "yes"}) == []


def test_prog_002_no_fire_when_unclear():
    assert check_prog_002({"graduation_confirmation_present": "unclear"}) == []


def test_prog_002_no_fire_missing_field():
    assert check_prog_002({}) == []


def test_prog_002_rationale_mentions_case_c():
    flag = check_prog_002({"graduation_confirmation_present": "no"})[0]
    assert "Case C" in flag.rationale


# ── PROG_003 — Required domain absent ────────────────────────────────────────


def test_prog_003_fires_for_each_missing_required_domain():
    agg = {"required_nursing_domains_present": []}
    flags = check_prog_003(agg)
    assert len(flags) == 4  # adult_med_surg, obstetrics, pediatrics, psychiatric
    codes = [f.rule_code for f in flags]
    assert all(c == "PROG_003" for c in codes)
    assert all(f.severity == "high" for f in flags)


def test_prog_003_fires_for_single_missing_domain():
    agg = {
        "required_nursing_domains_present": [
            "obstetrics",
            "pediatrics",
            "psychiatric",
        ]
    }
    flags = check_prog_003(agg)
    assert len(flags) == 1
    assert "adult_med_surg" in flags[0].rule_description


def test_prog_003_no_fire_all_required_present():
    agg = {
        "required_nursing_domains_present": [
            "adult_med_surg",
            "obstetrics",
            "pediatrics",
            "psychiatric",
            "gerontology",
            "community_health",
        ]
    }
    assert check_prog_003(agg) == []


def test_prog_003_no_fire_just_required_present():
    """Only the 4 required domains — gerontology/community_health optional."""
    agg = {
        "required_nursing_domains_present": [
            "adult_med_surg",
            "obstetrics",
            "pediatrics",
            "psychiatric",
        ]
    }
    assert check_prog_003(agg) == []


def test_prog_003_no_fire_missing_field():
    # Missing field treated as empty list
    assert check_prog_003({}) == []


def test_prog_003_missing_domains_named_in_descriptions():
    agg = {"required_nursing_domains_present": ["adult_med_surg"]}
    flags = check_prog_003(agg)
    described = {f.rule_description for f in flags}
    assert any("obstetrics" in d for d in described)
    assert any("pediatrics" in d for d in described)
    assert any("psychiatric" in d for d in described)

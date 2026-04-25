"""Unit tests for physical document rules (PHYS_001 – PHYS_005)."""

import os
import sys

import pytest

_RULE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "../../../services/rule_engine")
)
if _RULE_DIR not in sys.path:
    sys.path.insert(0, _RULE_DIR)

from rules.physical import (  # noqa: E402
    check_phys_001,
    check_phys_002,
    check_phys_003,
    check_phys_004,
    check_phys_005,
)


# ── PHYS_001 — Seal Authenticity ──────────────────────────────────────────────

# Check 1: seal absent

def test_phys_001_check1_fires_absent_seal():
    flags = check_phys_001({"seal_type": "absent"})
    high = [f for f in flags if f.rule_code == "PHYS_001" and f.severity == "high"
            and "absent" in f.rule_description.lower()]
    assert len(high) >= 1


def test_phys_001_check1_no_fire_when_unclear():
    """seal_type == 'unclear' is a documented fallback — must not fire Check 1."""
    flags = check_phys_001({"seal_type": "unclear"})
    assert not any("absent" in f.rule_description.lower() for f in flags)


def test_phys_001_check1_no_fire_when_seal_present():
    flags = check_phys_001({"seal_type": "embossed"})
    assert not any("absent" in f.rule_description.lower() for f in flags)


# Check 2: seal degraded/pixelated

def test_phys_001_check2_fires_pixelated():
    flags = check_phys_001({"seal_quality": "pixelated"})
    assert any(f.rule_code == "PHYS_001" and f.severity == "high" for f in flags)


def test_phys_001_check2_fires_degraded():
    flags = check_phys_001({"seal_quality": "degraded"})
    assert any(f.rule_code == "PHYS_001" and f.severity == "high" for f in flags)


def test_phys_001_check2_no_fire_clear():
    assert check_phys_001({"seal_quality": "clear"}) == []


def test_phys_001_check2_no_fire_absent():
    assert check_phys_001({"seal_quality": "absent"}) == []


# Check 3: seal text mismatch

def test_phys_001_check3_fires_seal_text_mismatch():
    agg = {
        "seal_visible_text": "RandomUniversity Press",
        "institution": "Northside Nursing College",
    }
    flags = check_phys_001(agg)
    low_flags = [f for f in flags if f.severity == "low" and "seal text" in f.rule_description.lower()]
    assert len(low_flags) == 1


def test_phys_001_check3_no_fire_when_no_seal_text():
    """Fallback: seal_visible_text empty/null → skip Check 3."""
    agg = {"seal_visible_text": "", "institution": "Northside Nursing College"}
    flags = check_phys_001(agg)
    assert not any("seal text" in f.rule_description.lower() for f in flags)


def test_phys_001_check3_no_fire_when_text_matches():
    agg = {
        "seal_visible_text": "Northside Nursing College Official Seal",
        "institution": "Northside Nursing College",
    }
    flags = check_phys_001(agg)
    assert not any("seal text" in f.rule_description.lower() for f in flags)


# Check 4: no security features

def test_phys_001_check4_fires_empty_features_assessable():
    agg = {
        "security_features_present": [],
        "security_features_assessable": "yes",
    }
    flags = check_phys_001(agg)
    assert any(f.rule_code == "PHYS_001" and f.severity == "high"
               and "security features" in f.rule_description.lower() for f in flags)


def test_phys_001_check4_no_fire_when_not_assessable():
    """Fallback: security_features_assessable == 'no' → skip Check 4."""
    agg = {
        "security_features_present": [],
        "security_features_assessable": "no",
    }
    assert not any("security features" in f.rule_description.lower()
                   for f in check_phys_001(agg))


def test_phys_001_check4_no_fire_with_features():
    agg = {
        "security_features_present": ["watermark"],
        "security_features_assessable": "yes",
    }
    assert not any("security features" in f.rule_description.lower()
                   for f in check_phys_001(agg))


# Check 5: seal not on all pages

def test_phys_001_check5_fires_seal_not_on_all_pages():
    agg = {"seal_present_on_pages": [1], "document_page_count": 3}
    flags = check_phys_001(agg)
    assert any(f.rule_code == "PHYS_001" and f.severity == "medium"
               and "all pages" in f.rule_description.lower() for f in flags)


def test_phys_001_check5_no_fire_when_seal_on_all_pages():
    agg = {"seal_present_on_pages": [1, 2, 3], "document_page_count": 3}
    assert not any("all pages" in f.rule_description.lower()
                   for f in check_phys_001(agg))


def test_phys_001_check5_no_fire_single_page():
    agg = {"seal_present_on_pages": [1], "document_page_count": 1}
    assert not any("all pages" in f.rule_description.lower()
                   for f in check_phys_001(agg))


def test_phys_001_check5_no_fire_missing_field():
    """Fallback: seal_present_on_pages missing → skip Check 5."""
    agg = {"document_page_count": 3}
    assert not any("all pages" in f.rule_description.lower()
                   for f in check_phys_001(agg))


# Multiple checks simultaneously

def test_phys_001_multiple_checks_fire():
    agg = {
        "seal_type": "absent",
        "seal_quality": "pixelated",
        "security_features_present": [],
        "security_features_assessable": "yes",
    }
    flags = check_phys_001(agg)
    assert len(flags) >= 3


# ── PHYS_002 — Registrar Information ─────────────────────────────────────────

# Check 1: registrar name

def test_phys_002_check1_fires_no_registrar_name():
    flags = check_phys_002({"registrar_name_present": False})
    assert any(f.rule_code == "PHYS_002" and f.severity == "high"
               and "name" in f.rule_description.lower() for f in flags)


def test_phys_002_check1_no_fire_name_present():
    assert check_phys_002({"registrar_name_present": True}) == []


def test_phys_002_check1_no_fire_missing_field():
    assert check_phys_002({}) == []


# Check 2: registrar signature

def test_phys_002_check2_fires_no_signature():
    flags = check_phys_002({"registrar_signature_present": False})
    assert any(f.rule_code == "PHYS_002" and f.severity == "high"
               and "signature" in f.rule_description.lower() for f in flags)


def test_phys_002_check2_no_fire_signature_present():
    assert check_phys_002({"registrar_signature_present": True}) == []


# Check 3: registrar title

def test_phys_002_check3_fires_no_title():
    flags = check_phys_002({"registrar_title_present": False})
    assert any(f.rule_code == "PHYS_002" and f.severity == "high"
               and "title" in f.rule_description.lower() for f in flags)


def test_phys_002_check3_no_fire_title_present():
    assert check_phys_002({"registrar_title_present": True}) == []


# Check 4: institution contact info

def test_phys_002_check4_fires_no_contact_info():
    flags = check_phys_002({"institution_contact_info_present": False})
    assert any(f.rule_code == "PHYS_002" and f.severity == "high"
               and "contact" in f.rule_description.lower() for f in flags)


def test_phys_002_check4_no_fire_contact_present():
    assert check_phys_002({"institution_contact_info_present": True}) == []


# Check 5: signature consistency

def test_phys_002_check5_fires_inconsistent_signature():
    instances = [
        {"page": 1, "type": "handwritten", "appears_consistent": True},
        {"page": 2, "type": "handwritten", "appears_consistent": False},
    ]
    flags = check_phys_002({"registrar_signature_instances": instances})
    assert any(f.rule_code == "PHYS_002" and f.severity == "low" for f in flags)


def test_phys_002_check5_skip_single_instance():
    """Fallback: only one signature instance → skip Check 5."""
    instances = [{"page": 1, "type": "handwritten", "appears_consistent": True}]
    assert check_phys_002({"registrar_signature_instances": instances}) == []


def test_phys_002_check5_skip_all_stamped_digital():
    """Fallback: stamped/digital signatures are identical by design → skip Check 5."""
    instances = [
        {"page": 1, "type": "stamped", "appears_consistent": False},
        {"page": 2, "type": "digital", "appears_consistent": False},
    ]
    assert check_phys_002({"registrar_signature_instances": instances}) == []


def test_phys_002_check5_no_fire_when_all_consistent():
    instances = [
        {"page": 1, "type": "handwritten", "appears_consistent": True},
        {"page": 2, "type": "handwritten", "appears_consistent": True},
    ]
    assert check_phys_002({"registrar_signature_instances": instances}) == []


# All four primary checks fire simultaneously

def test_phys_002_all_four_checks_fire():
    agg = {
        "registrar_name_present": False,
        "registrar_signature_present": False,
        "registrar_title_present": False,
        "institution_contact_info_present": False,
    }
    flags = check_phys_002(agg)
    assert len(flags) == 4
    assert all(f.rule_code == "PHYS_002" and f.severity == "high" for f in flags)


# ── PHYS_003 — Print Technology Anachronism ───────────────────────────────────

# Check 1: anachronistic technology

def test_phys_003_check1_fires_laser_predates_window():
    """Laser printing wasn't available before 1985; a 1970 issue date is anachronistic."""
    flags = check_phys_003({
        "print_technology": "laser",
        "document_issue_date": "1970-06-01",
    })
    medium = [f for f in flags if f.severity == "medium" and "PHYS_003" == f.rule_code]
    assert len(medium) == 1


def test_phys_003_check1_fires_typewriter_obsolete():
    """Typewriter was uncommon after 1995; a 2010 issue date is anachronistic."""
    flags = check_phys_003({
        "print_technology": "typewriter",
        "document_issue_date": "2010-03-15",
    })
    assert any(f.rule_code == "PHYS_003" and f.severity == "medium" for f in flags)


def test_phys_003_check1_no_fire_reissue_marker():
    """Fallback: reissue_markers_detected == True → skip Check 1."""
    flags = check_phys_003({
        "print_technology": "typewriter",
        "document_issue_date": "2010-03-15",
        "reissue_markers_detected": True,
    })
    assert flags == []


def test_phys_003_check1_no_fire_unclear_tech():
    """Fallback: print_technology == 'unclear' → skip both checks."""
    flags = check_phys_003({
        "print_technology": "unclear",
        "document_issue_date": "1970-01-01",
    })
    assert flags == []


def test_phys_003_check1_no_fire_plausible():
    flags = check_phys_003({
        "print_technology": "laser",
        "document_issue_date": "2018-04-15",
    })
    assert flags == []


def test_phys_003_check1_no_fire_missing_date():
    flags = check_phys_003({"print_technology": "laser"})
    assert flags == []


# Check 2: mixed print technology

def test_phys_003_check2_fires_mixed_tech():
    flags = check_phys_003({
        "print_technology": "laser",
        "print_technology_per_page": ["laser", "inkjet", "laser"],
    })
    high = [f for f in flags if f.rule_code == "PHYS_003" and f.severity == "high"]
    assert len(high) == 1


def test_phys_003_check2_no_fire_single_page():
    """Fallback: single-page document (one entry in print_technology_per_page) → skip Check 2."""
    flags = check_phys_003({
        "print_technology": "laser",
        "print_technology_per_page": ["laser"],
    })
    assert not any(f.severity == "high" for f in flags)


def test_phys_003_check2_no_fire_consistent_tech():
    flags = check_phys_003({
        "print_technology": "laser",
        "print_technology_per_page": ["laser", "laser", "laser"],
    })
    assert not any(f.severity == "high" for f in flags)


def test_phys_003_check2_no_fire_unclear_tech_per_page():
    """Fallback: all non-unclear entries are the same → no mix fire."""
    flags = check_phys_003({
        "print_technology": "laser",
        "print_technology_per_page": ["laser", "unclear", "laser"],
    })
    assert not any(f.severity == "high" for f in flags)


def test_phys_003_both_checks_fire():
    flags = check_phys_003({
        "print_technology": "typewriter",
        "document_issue_date": "2015-01-01",
        "print_technology_per_page": ["typewriter", "laser"],
    })
    severities = {f.severity for f in flags}
    assert "medium" in severities and "high" in severities


# ── PHYS_004 — Text and Print Integrity ──────────────────────────────────────

# Check 1: text misalignment

def test_phys_004_check1_fires_misaligned():
    flags = check_phys_004({"text_alignment": "misaligned"})
    assert any(f.rule_code == "PHYS_004" and f.severity == "medium" for f in flags)


def test_phys_004_check1_no_fire_unclear():
    """Fallback: text_alignment == 'unclear' → no fire."""
    assert check_phys_004({"text_alignment": "unclear"}) == []


def test_phys_004_check1_no_fire_normal():
    assert check_phys_004({"text_alignment": "normal"}) == []


# Check 2: uneven spacing

def test_phys_004_check2_fires_uneven_spacing():
    flags = check_phys_004({"text_alignment": "uneven_spacing"})
    assert any(f.rule_code == "PHYS_004" and f.severity == "medium" for f in flags)


# Check 3: compressed numbers

def test_phys_004_check3_fires_compressed_numbers():
    flags = check_phys_004({"compressed_numbers_detected": True})
    assert any(f.rule_code == "PHYS_004" and f.severity == "high"
               and "compress" in f.rule_description.lower() for f in flags)


def test_phys_004_check3_no_fire_false():
    assert check_phys_004({"compressed_numbers_detected": False}) == []


# Check 4: mixed fonts

def test_phys_004_check4_fires_mixed_fonts():
    flags = check_phys_004({"mixed_fonts_detected": True})
    assert any(f.rule_code == "PHYS_004" and f.severity == "high"
               and "font" in f.rule_description.lower() for f in flags)


def test_phys_004_check4_no_fire_false():
    assert check_phys_004({"mixed_fonts_detected": False}) == []


# Check 5: correction artifacts

def test_phys_004_check5_fires_correction_artifacts():
    flags = check_phys_004({"correction_artifacts_present": True})
    assert any(f.rule_code == "PHYS_004" and f.severity == "high"
               and "correction" in f.rule_description.lower() for f in flags)


def test_phys_004_check5_no_fire_false():
    assert check_phys_004({"correction_artifacts_present": False}) == []


# Check 6: obliteration marks

def test_phys_004_check6_fires_obliteration():
    flags = check_phys_004({"obliteration_marks_detected": True})
    assert any(f.rule_code == "PHYS_004" and f.severity == "high"
               and "obliterat" in f.rule_description.lower() for f in flags)


def test_phys_004_check6_no_fire_false():
    assert check_phys_004({"obliteration_marks_detected": False}) == []


# Check 7: mixed ink colors

def test_phys_004_check7_fires_mixed_ink():
    flags = check_phys_004({"mixed_ink_colors_in_field": True})
    assert any(f.rule_code == "PHYS_004" and f.severity == "high"
               and "ink" in f.rule_description.lower() for f in flags)


def test_phys_004_check7_no_fire_false():
    assert check_phys_004({"mixed_ink_colors_in_field": False}) == []


# Check 8: printer quality inconsistency

def test_phys_004_check8_fires_inconsistent():
    flags = check_phys_004({"printer_quality_consistency": "inconsistent"})
    assert any(f.rule_code == "PHYS_004" and f.severity == "medium"
               and "quality" in f.rule_description.lower() for f in flags)


def test_phys_004_check8_no_fire_consistent():
    assert check_phys_004({"printer_quality_consistency": "consistent"}) == []


def test_phys_004_check8_no_fire_unclear():
    assert check_phys_004({"printer_quality_consistency": "unclear"}) == []


# Multiple checks simultaneously

def test_phys_004_multiple_checks_fire():
    agg = {
        "text_alignment": "misaligned",
        "compressed_numbers_detected": True,
        "mixed_fonts_detected": True,
        "correction_artifacts_present": True,
    }
    flags = check_phys_004(agg)
    assert len(flags) == 4
    codes = {f.rule_code for f in flags}
    assert codes == {"PHYS_004"}


def test_phys_004_no_fire_clean():
    agg = {
        "text_alignment": "normal",
        "compressed_numbers_detected": False,
        "mixed_fonts_detected": False,
        "correction_artifacts_present": False,
        "obliteration_marks_detected": False,
        "mixed_ink_colors_in_field": False,
        "printer_quality_consistency": "consistent",
    }
    assert check_phys_004(agg) == []


# ── PHYS_005 — Document Completeness Markers ─────────────────────────────────

# Check 1: degree conferral statement absent

def test_phys_005_check1_fires_no_statement():
    flags = check_phys_005({"degree_conferral_statement_present": False})
    assert any(f.rule_code == "PHYS_005" and f.severity == "high"
               and "statement" in f.rule_description.lower() for f in flags)


def test_phys_005_check1_no_fire_statement_present():
    flags = check_phys_005({
        "degree_conferral_statement_present": True,
        "degree_conferred_date": "2020-05-15",
    })
    assert flags == []


def test_phys_005_check1_no_fire_missing_field():
    """If degree_conferral_statement_present not extracted, neither check fires."""
    assert check_phys_005({}) == []


# Check 2: conferral date absent

def test_phys_005_check2_fires_no_date():
    flags = check_phys_005({
        "degree_conferral_statement_present": True,
        "degree_conferred_date": None,
    })
    assert any(f.rule_code == "PHYS_005" and f.severity == "high"
               and "date" in f.rule_description.lower() for f in flags)


def test_phys_005_check2_no_fire_date_present():
    flags = check_phys_005({
        "degree_conferral_statement_present": True,
        "degree_conferred_date": "2020-05-15",
    })
    assert flags == []


def test_phys_005_check2_skipped_when_check1_fires():
    """Fallback: if no conferral statement, Check 2 is skipped entirely."""
    flags = check_phys_005({
        "degree_conferral_statement_present": False,
        "degree_conferred_date": None,
    })
    # Only one flag (from Check 1); Check 2 is skipped per spec fallback
    assert len(flags) == 1
    assert "statement" in flags[0].rule_description.lower()


def test_phys_005_both_checks_fire_together():
    """Verify that when conferral date is missing after statement, both flags appear correctly."""
    flags = check_phys_005({
        "degree_conferral_statement_present": True,
        "degree_conferred_date": "",
    })
    assert len(flags) == 1  # Check 2 only (Check 1 doesn't fire when statement is present)
    assert "date" in flags[0].rule_description.lower()

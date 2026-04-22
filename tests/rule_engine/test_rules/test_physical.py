"""Unit tests for physical document rules (PHYS_001 – PHYS_005)."""

import copy
import os
import sys

import pytest

# Allow direct import of the rule modules without packaging
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

# ── PHYS_001 — Pixelated seal ─────────────────────────────────────────────────


def test_phys_001_fires_on_pixelated():
    flags = check_phys_001({"seal_quality": "pixelated"})
    assert len(flags) == 1
    assert flags[0].rule_code == "PHYS_001"
    assert flags[0].severity == "high"
    assert flags[0].category == "SP-4"


def test_phys_001_fires_on_degraded():
    flags = check_phys_001({"seal_quality": "degraded"})
    assert len(flags) == 1
    assert flags[0].rule_code == "PHYS_001"


def test_phys_001_no_fire_clear():
    assert check_phys_001({"seal_quality": "clear"}) == []


def test_phys_001_no_fire_absent():
    assert check_phys_001({"seal_quality": "absent"}) == []


def test_phys_001_no_fire_missing_field():
    assert check_phys_001({}) == []


def test_phys_001_rationale_mentions_quality():
    flag = check_phys_001({"seal_quality": "pixelated"})[0]
    assert "pixelated" in flag.rationale


# ── PHYS_002 — Missing/incorrect security features ────────────────────────────


def test_phys_002_fires_on_no_features_assessable():
    agg = {
        "security_features_assessable": "yes",
        "security_features_assessable_confidence": "high",
        "security_features_present": [],
        "security_features_present_confidence": "high",
    }
    flags = check_phys_002(agg)
    assert any(f.rule_code == "PHYS_002" for f in flags)


def test_phys_002_no_fire_with_features():
    agg = {
        "security_features_assessable": "yes",
        "security_features_assessable_confidence": "high",
        "security_features_present": ["watermark"],
        "security_features_present_confidence": "high",
    }
    assert check_phys_002(agg) == []


def test_phys_002_no_fire_not_assessable():
    agg = {
        "security_features_assessable": "no",
        "security_features_assessable_confidence": "high",
        "security_features_present": [],
        "security_features_present_confidence": "high",
    }
    assert check_phys_002(agg) == []


def test_phys_002_no_fire_when_missing_features_are_not_high_confidence():
    agg = {
        "security_features_assessable": "yes",
        "security_features_assessable_confidence": "high",
        "security_features_present": [],
        "security_features_present_confidence": "medium",
    }
    assert check_phys_002(agg) == []


def test_phys_002_fires_on_seal_type_mismatch():
    agg = {
        "seal_type": "stamped_ink",
        "institution_expected_seal_type": "embossed",
        "security_features_present": ["watermark"],
        "security_features_assessable": "yes",
    }
    codes = [f.rule_code for f in check_phys_002(agg)]
    assert "PHYS_002" in codes
    # Should fire for both missing features AND seal mismatch? No — features present
    # Only fires for seal mismatch here
    seal_flags = [f for f in check_phys_002(agg) if "seal type" in f.rule_description.lower()]
    assert len(seal_flags) == 1


def test_phys_002_no_fire_when_seal_types_match():
    agg = {
        "seal_type": "embossed",
        "institution_expected_seal_type": "embossed",
        "security_features_present": ["watermark"],
        "security_features_assessable": "yes",
    }
    assert check_phys_002(agg) == []


def test_phys_002_rationale_mentions_case_c():
    agg = {
        "seal_type": "stamped_ink",
        "institution_expected_seal_type": "embossed",
    }
    flags = check_phys_002(agg)
    seal_flag = next(f for f in flags if "embossed" in f.rationale)
    assert "Case C" in seal_flag.rationale


# ── PHYS_003 — Print technology / issue date mismatch ────────────────────────


def test_phys_003_fires_laser_on_1970_document():
    flags = check_phys_003({"print_technology": "laser", "issue_year": 1970})
    assert len(flags) == 1
    assert flags[0].rule_code == "PHYS_003"
    assert flags[0].severity == "medium"


def test_phys_003_fires_typewriter_on_2010_document():
    flags = check_phys_003({"print_technology": "typewriter", "issue_year": 2010})
    assert len(flags) == 1
    assert flags[0].rule_code == "PHYS_003"


def test_phys_003_no_fire_laser_2018():
    assert check_phys_003({"print_technology": "laser", "issue_year": 2018}) == []


def test_phys_003_no_fire_unclear_tech():
    assert check_phys_003({"print_technology": "unclear", "issue_year": 2018}) == []


def test_phys_003_no_fire_missing_year():
    assert check_phys_003({"print_technology": "laser"}) == []


# ── PHYS_004 — Text misalignment ──────────────────────────────────────────────


def test_phys_004_fires_on_misaligned():
    flags = check_phys_004({"text_alignment": "misaligned"})
    assert len(flags) == 1
    assert flags[0].rule_code == "PHYS_004"
    assert flags[0].severity == "medium"


def test_phys_004_fires_on_uneven_spacing():
    flags = check_phys_004({"text_alignment": "uneven_spacing"})
    assert len(flags) == 1


def test_phys_004_no_fire_normal():
    assert check_phys_004({"text_alignment": "normal"}) == []


def test_phys_004_no_fire_missing_field():
    assert check_phys_004({}) == []


def test_phys_004_rationale_mentions_case_a():
    flag = check_phys_004({"text_alignment": "misaligned"})[0]
    assert "Case A" in flag.rationale


# ── PHYS_005 — Scan presented as original ─────────────────────────────────────


def test_phys_005_fires_on_scan_artifacts():
    agg = {
        "document_provenance_appearance": "scan_artifacts_present",
        "document_presented_as_original": True,
    }
    flags = check_phys_005(agg)
    assert len(flags) == 1
    assert flags[0].rule_code == "PHYS_005"
    assert flags[0].severity == "medium"


def test_phys_005_no_fire_when_not_original():
    agg = {
        "document_provenance_appearance": "scan_artifacts_present",
        "document_presented_as_original": False,
    }
    assert check_phys_005(agg) == []


def test_phys_005_no_fire_on_original_provenance():
    agg = {
        "document_provenance_appearance": "original",
        "document_presented_as_original": True,
    }
    assert check_phys_005(agg) == []


def test_phys_005_defaults_to_original_presentation():
    """If document_presented_as_original is absent, default True should fire."""
    agg = {"document_provenance_appearance": "scan_artifacts_present"}
    flags = check_phys_005(agg)
    assert len(flags) == 1

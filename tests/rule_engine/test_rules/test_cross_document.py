"""Unit tests for cross-document consistency rules (CROSS_001 – CROSS_003)."""

import os
import sys

import pytest

_RULE_DIR = os.path.normpath(
    os.path.join(os.path.dirname(__file__), "../../../services/rule_engine")
)
if _RULE_DIR not in sys.path:
    sys.path.insert(0, _RULE_DIR)

from rules.cross_document import (  # noqa: E402
    check_cross_001,
    check_cross_002,
    check_cross_003,
)

# ── CROSS_001 — Applicant name mismatch ───────────────────────────────────────


def test_cross_001_fires_on_mismatch():
    flags = check_cross_001({"applicant_name_match": "mismatch"})
    assert len(flags) == 1
    assert flags[0].rule_code == "CROSS_001"
    assert flags[0].severity == "high"
    assert flags[0].category == "SP-1"


def test_cross_001_no_fire_match():
    assert check_cross_001({"applicant_name_match": "match"}) == []


def test_cross_001_no_fire_insufficient_data():
    assert check_cross_001({"applicant_name_match": "insufficient_data"}) == []


def test_cross_001_no_fire_missing_field():
    assert check_cross_001({}) == []


def test_cross_001_rationale_mentions_impersonation():
    flag = check_cross_001({"applicant_name_match": "mismatch"})[0]
    assert "impersonation" in flag.rationale.lower() or "substitution" in flag.rationale.lower()


# ── CROSS_002 — Institution name mismatch ─────────────────────────────────────


def test_cross_002_fires_on_mismatch():
    flags = check_cross_002({"institution_name_match": "mismatch"})
    assert len(flags) == 1
    assert flags[0].rule_code == "CROSS_002"
    assert flags[0].severity == "high"
    assert flags[0].category == "SP-4"


def test_cross_002_no_fire_match():
    assert check_cross_002({"institution_name_match": "match"}) == []


def test_cross_002_no_fire_insufficient_data():
    assert check_cross_002({"institution_name_match": "insufficient_data"}) == []


def test_cross_002_no_fire_missing_field():
    assert check_cross_002({}) == []


# ── CROSS_003 — Date mismatch > 90 days ───────────────────────────────────────


def test_cross_003_fires_on_mismatch_greater_than_90():
    flags = check_cross_003(
        {"dates_match_across_documents": "mismatch_greater_than_90_days"}
    )
    assert len(flags) == 1
    assert flags[0].rule_code == "CROSS_003"
    assert flags[0].severity == "high"
    assert flags[0].category == "SP-4"


def test_cross_003_no_fire_match():
    assert check_cross_003({"dates_match_across_documents": "match"}) == []


def test_cross_003_no_fire_insufficient_data():
    assert check_cross_003(
        {"dates_match_across_documents": "insufficient_data"}
    ) == []


def test_cross_003_no_fire_missing_field():
    assert check_cross_003({}) == []


def test_cross_003_rationale_mentions_90_days():
    flag = check_cross_003(
        {"dates_match_across_documents": "mismatch_greater_than_90_days"}
    )[0]
    assert "90" in flag.rationale

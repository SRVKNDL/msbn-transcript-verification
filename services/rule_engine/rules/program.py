"""Program and institution authenticity rules (PROG_001 – PROG_003).

SP-5 (educational authenticity) and SP-4 (document analysis).

Each function accepts an aggregation dict and returns list[Flag].

Aggregation fields consumed (see design/extraction-vocabulary.md Section 3):
  accreditation_claim             : string extracted from document
  diploma_mill_language_detected  : yes | no | possible
  diploma_mill_phrases_found      : list of strings
  institution_address_present     : yes | no | unclear
  institution_phone_present       : yes | no | unclear
  graduation_confirmation_present : yes | no | unclear
  required_nursing_domains_present: list of domain strings
"""

from rules.base import Flag, _src

# Placeholder approved accreditor list.
# MSBN must supply the official list before production use (see requirements-draft.md
# Section 3 and Open Items table item "Approved credentials evaluation agency list").
_APPROVED_ACCREDITORS = {
    "acen",
    "ccne",
    "cgfns",
    # Country-specific bodies — add MSBN-confirmed entries here
    "nmc",   # UK Nursing & Midwifery Council
    "anmac", # Australian Nursing & Midwifery Accreditation Council
    "cno",   # College of Nurses of Ontario
    "cnc",   # Canadian Nurses Association / provincial colleges
    "ncbn",  # Nigeria Council for Nursing
    "prc",   # Philippine Professional Regulation Commission
    "inc",   # Indian Nursing Council
}

# Required nursing domains that must be present in a valid transcript.
# Source: NCSBN sample evaluation report (requirements-draft.md Section 2).
# MSBN must confirm these as official thresholds before production use.
_REQUIRED_DOMAINS = frozenset([
    "adult_med_surg",
    "obstetrics",
    "pediatrics",
    "psychiatric",
])


def check_prog_001(agg: dict) -> list:
    """PROG_001 — Diploma mill credential or unaccredited institution.

    Fires when:
    1. diploma_mill_language_detected is 'yes' or 'possible'.
    2. accreditation_claim is absent or not in the approved accreditor list.
    """
    flags = []

    # Check 1: diploma mill language
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

    # Check 2: unrecognized accreditor
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
    """PROG_002 — Transcript lacks a graduation or degree conferral confirmation.

    Absence may indicate a fabricated affidavit of graduation
    (see MSBN Case C: student attended but did not pass exit exam).
    """
    present = agg.get("graduation_confirmation_present")
    if present == "no":
        return [
            Flag(
                rule_code="PROG_002",
                rule_description="No graduation or degree conferral confirmation",
                severity="high",
                category="SP-4",
                rationale=(
                    "The transcript does not include a graduation date, degree conferral "
                    "statement, or other explicit completion indicator. "
                    "Absence may indicate a fabricated affidavit of graduation "
                    "(see MSBN Case C: student submitted an affidavit the school never issued). "
                    "Staff must independently verify completion status with the institution."
                ),
                source_location=_src(agg, "graduation_confirmation_present"),
            )
        ]
    return []


def check_prog_003(agg: dict) -> list:
    """PROG_003 — One or more required nursing coursework domains are absent.

    Flags each domain with zero hours recorded. Severity is 'high' for a
    fully absent domain; the rule fires once per missing domain.

    NOTE: Hour-level threshold checking (medium severity 'deficient') requires
    per-domain hour extraction, which is deferred to Phase 3 (see
    extraction-vocabulary.md Section 7, open question 1).
    """
    present_raw = agg.get("required_nursing_domains_present")
    # None means extraction did not produce this field — not enough signal to flag.
    # An empty list means the field was produced but no domains were found.
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

"""Physical document authenticity rules (PHYS_001 – PHYS_005).

SP-4: Analysis of Authenticity of Documents.

Each function accepts an aggregation dict and returns list[Flag].
All thresholds and enum comparisons are deterministic Python — no LLM calls.

Aggregation fields consumed (see design/extraction-vocabulary.md Section 1):
  seal_quality                    : clear | degraded | pixelated | absent | unclear
  seal_type                       : embossed | stamped_ink | printed_flat | sticker_foil | absent | unclear
  institution_expected_seal_type  : expected seal type from reference table (may be absent)
  security_features_present       : list of detected features
  security_features_assessable    : yes | no
  print_technology                : typewriter | dot_matrix | laser | inkjet | photocopy | unclear
  issue_year                      : int, extracted from graduation/issue date (may be absent)
  text_alignment                  : normal | misaligned | uneven_spacing | unclear
  document_provenance_appearance  : original | color_copy | scan_artifacts_present | unclear
  document_presented_as_original  : bool, True when document is submitted as an authentic original
"""

from rules.base import Flag, _src

# Print technology plausibility windows.
# Outside these (year_from, year_to) ranges the technology is anomalous.
# "year_to" of None means still in use today.
_PRINT_TECH_WINDOW = {
    "typewriter": (1870, 1995),
    "dot_matrix": (1970, 2005),
    "laser": (1985, None),
    "inkjet": (1988, None),
    "photocopy": (1960, None),
}


def check_phys_001(agg: dict) -> list:
    """PHYS_001 — Institution seal or logo is pixelated or degraded.

    Fires when seal_quality indicates copy-of-copy degradation.
    """
    quality = agg.get("seal_quality")
    if quality in ("pixelated", "degraded"):
        return [
            Flag(
                rule_code="PHYS_001",
                rule_description="Pixelated or degraded institution seal/logo",
                severity="high",
                category="SP-4",
                rationale=(
                    f"Institution seal quality is '{quality}', which is consistent with "
                    "a copy-of-copy reproduction rather than an original document. "
                    "Authentic original transcripts should have a clear, sharp seal."
                ),
                source_location=_src(agg, "seal_quality"),
            )
        ]
    return []


def check_phys_002(agg: dict) -> list:
    """PHYS_002 — Missing/incorrect security features or wrong seal type.

    Fires in two situations:
    1. No security features present when assessment is reliable.
    2. Seal type on document does not match institution's known seal type.
    """
    flags = []

    # Check 1: assessable page with no security features.
    # Be conservative: faint watermarks and micro-printing are easy for the
    # extractor to miss on ordinary scans, so only escalate when both the
    # assessability judgment and the "no features present" extraction are high
    # confidence.
    assessable = agg.get("security_features_assessable")
    assessable_confidence = agg.get("security_features_assessable_confidence")
    features = agg.get("security_features_present") or []
    features_confidence = agg.get("security_features_present_confidence")
    if (
        assessable == "yes"
        and len(features) == 0
        and assessable_confidence == "high"
        and features_confidence == "high"
    ):
        flags.append(
            Flag(
                rule_code="PHYS_002",
                rule_description="Missing security features",
                severity="high",
                category="SP-4",
                rationale=(
                    "Document page quality permits reliable assessment of security "
                    "features, and the extractor had high confidence that no security "
                    "features (watermark, micro-printing, hologram, serial number) were "
                    "present. Legitimate transcripts from most institutions include at "
                    "least one security feature."
                ),
                source_location=_src(agg, "security_features_present"),
            )
        )

    # Check 2: seal type mismatch against institution reference
    actual_seal = agg.get("seal_type")
    expected_seal = agg.get("institution_expected_seal_type")
    if (
        actual_seal
        and expected_seal
        and actual_seal not in ("absent", "unclear")
        and expected_seal not in ("absent", "unclear")
        and actual_seal != expected_seal
    ):
        flags.append(
            Flag(
                rule_code="PHYS_002",
                rule_description="Seal type does not match institution record",
                severity="high",
                category="SP-4",
                rationale=(
                    f"Document seal type is '{actual_seal}' but the institution's "
                    f"reference record specifies '{expected_seal}'. "
                    "Seal type inconsistency is a confirmed forgery indicator "
                    "(see MSBN/NCSBN Case C: stamped seal where embossed is expected)."
                ),
                source_location=_src(agg, "seal_type"),
            )
        )

    return flags


def check_phys_003(agg: dict) -> list:
    """PHYS_003 — Print technology is inconsistent with the document's issue year.

    Fires when the detected print technology post-dates or pre-dates the
    plausibility window for that technology given the document's claimed year.
    """
    tech = agg.get("print_technology")
    issue_year = agg.get("issue_year")

    if not tech or tech == "unclear" or not issue_year:
        return []

    window = _PRINT_TECH_WINDOW.get(tech)
    if window is None:
        return []

    year_from, year_to = window
    anomalous = issue_year < year_from or (
        year_to is not None and issue_year > year_to
    )

    if anomalous:
        if issue_year < year_from:
            detail = (
                f"'{tech}' printing was not available until approximately {year_from}, "
                f"but document claims issue year {issue_year}."
            )
        else:
            detail = (
                f"'{tech}' printing was uncommon after approximately {year_to}, "
                f"but document claims issue year {issue_year}."
            )
        return [
            Flag(
                rule_code="PHYS_003",
                rule_description="Print technology inconsistent with claimed issue date",
                severity="medium",
                category="SP-4",
                rationale=detail,
                source_location=_src(agg, "print_technology"),
            )
        ]
    return []


def check_phys_004(agg: dict) -> list:
    """PHYS_004 — Text misalignment inconsistent with institutional printing.

    Fires when OCR/visual analysis detects misaligned text, which may indicate
    inserted or appended content (e.g., a grade value added after the fact).
    """
    alignment = agg.get("text_alignment")
    if alignment in ("misaligned", "uneven_spacing"):
        return [
            Flag(
                rule_code="PHYS_004",
                rule_description="Text misalignment detected",
                severity="medium",
                category="SP-4",
                rationale=(
                    f"Text alignment is '{alignment}'. Misaligned text blocks, table cells, "
                    "or individual entries are inconsistent with institutional printing standards "
                    "and may indicate inserted or appended content "
                    "(see MSBN/NCSBN Case A: '+2.0' addend inserted into grade column)."
                ),
                source_location=_src(agg, "text_alignment"),
            )
        ]
    return []


def check_phys_005(agg: dict) -> list:
    """PHYS_005 — Document appears to be a scan but is presented as an original.

    Fires when scan compression artifacts are detected on a document
    submitted as authentic original documentation.
    """
    provenance = agg.get("document_provenance_appearance")
    presented_as_original = agg.get("document_presented_as_original", True)

    if provenance == "scan_artifacts_present" and presented_as_original:
        return [
            Flag(
                rule_code="PHYS_005",
                rule_description="Scan or photocopy presented as original document",
                severity="medium",
                category="SP-4",
                rationale=(
                    "Document exhibits JPEG compression artifacts and/or color banding "
                    "consistent with a photocopy or scan, but was submitted as an original. "
                    "Original documents should not show scan reproduction artifacts."
                ),
                source_location=_src(agg, "document_provenance_appearance"),
            )
        ]
    return []

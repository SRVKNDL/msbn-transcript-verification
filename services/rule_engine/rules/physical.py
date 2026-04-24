"""Physical document checks for SP-4."""

from rules.base import Flag, _src

# Approximate years where each print technology is plausible.
# A None end year means the technology is still in ordinary use.
_PRINT_TECH_WINDOW = {
    "typewriter": (1870, 1995),
    "dot_matrix": (1970, 2005),
    "laser": (1985, None),
    "inkjet": (1988, None),
    "photocopy": (1960, None),
}


def check_phys_001(agg: dict) -> list:
    """Flag degraded institution seal or logo evidence."""
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
    """Flag missing security features or seal type mismatches."""
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
    """Flag print technology outside its plausible date range."""
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
    """Flag text alignment that looks manually inserted or edited."""
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
    """Flag scan artifacts on documents presented as originals."""
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

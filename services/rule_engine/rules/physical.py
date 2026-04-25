"""Physical document checks for PHYS_001–PHYS_005."""

from rules.base import Flag, _src

# Approximate plausibility windows for print technologies: (start_year, end_year|None).
_PRINT_TECH_WINDOW = {
    "typewriter": (1870, 1995),
    "dot_matrix": (1970, 2005),
    "laser": (1985, None),
    "inkjet": (1988, None),
    "photocopy": (1960, None),
}


def _parse_year(date_str) -> int | None:
    """Extract year as int from an ISO date string or bare year string."""
    if not date_str:
        return None
    try:
        return int(str(date_str)[:4])
    except (ValueError, TypeError):
        return None


def check_phys_001(agg: dict) -> list:
    """Seal authenticity — five checks covering presence, quality, text, security features, and page coverage."""
    flags = []

    seal_type = agg.get("seal_type")
    seal_quality = agg.get("seal_quality")
    institution = agg.get("institution") or ""
    seal_visible_text = agg.get("seal_visible_text") or ""
    security_features = agg.get("security_features_present")
    security_assessable = agg.get("security_features_assessable")
    seal_pages = agg.get("seal_present_on_pages")
    page_count = agg.get("document_page_count")

    # Check 1 — seal absent (HIGH); skip if seal_type == "unclear"
    if seal_type not in (None, "unclear") and seal_type == "absent":
        flags.append(Flag(
            rule_code="PHYS_001",
            rule_description="Institution seal absent from document",
            severity="high",
            category="SP-4",
            rationale=(
                "No institution seal is visible anywhere on the document. "
                "Authentic transcripts from accredited nursing programs include "
                "an institution seal."
            ),
            source_location=_src(agg, "seal_type"),
        ))

    # Check 2 — seal degraded or pixelated (HIGH)
    if seal_quality in ("pixelated", "degraded"):
        flags.append(Flag(
            rule_code="PHYS_001",
            rule_description="Institution seal quality is degraded or pixelated",
            severity="high",
            category="SP-4",
            rationale=(
                f"Institution seal quality is '{seal_quality}', consistent with a "
                "copy-of-copy reproduction rather than an original document. "
                "Authentic original transcripts should have a clear, sharp seal."
            ),
            source_location=_src(agg, "seal_quality"),
        ))

    # Check 3 — seal text doesn't appear to match institution name (LOW)
    # Skip if seal/watermark text isn't readable (seal_visible_text empty/null)
    if seal_visible_text and institution:
        inst_words = [w for w in institution.lower().split() if len(w) > 3]
        if inst_words and not any(w in seal_visible_text.lower() for w in inst_words):
            flags.append(Flag(
                rule_code="PHYS_001",
                rule_description="Seal text does not appear to match institution name",
                severity="low",
                category="SP-4",
                rationale=(
                    f"Readable seal/watermark text ('{seal_visible_text}') does not contain "
                    f"words from the institution name ('{institution}'). Watermark seals often "
                    "have partial text, so a mismatch is suspicious but not conclusive alone."
                ),
                source_location=_src(agg, "seal_visible_text"),
            ))

    # Check 4 — no security features present (HIGH)
    # Skip if security_features_assessable == "no"
    if (
        security_assessable != "no"
        and isinstance(security_features, list)
        and len(security_features) == 0
    ):
        flags.append(Flag(
            rule_code="PHYS_001",
            rule_description="No security features present",
            severity="high",
            category="SP-4",
            rationale=(
                "No security features (watermark, micro-printing, hologram, serial number) "
                "were detected. Legitimate transcripts from most accredited institutions "
                "include at least one physical security feature."
            ),
            source_location=_src(agg, "security_features_present"),
        ))

    # Check 5 — seal not present on all pages (MEDIUM)
    # Skip if page-level seal data not extracted or document is single-page
    if (
        isinstance(seal_pages, list)
        and isinstance(page_count, int)
        and page_count > 1
        and len(seal_pages) < page_count
    ):
        flags.append(Flag(
            rule_code="PHYS_001",
            rule_description="Seal not present on all pages",
            severity="medium",
            category="SP-4",
            rationale=(
                f"Institution seal found on {len(seal_pages)} of {page_count} page(s). "
                "Multi-page transcripts should bear the institution seal on every page."
            ),
            source_location=_src(agg, "seal_present_on_pages"),
        ))

    return flags


def check_phys_002(agg: dict) -> list:
    """Registrar attestation — structured block detection and completeness check."""
    flags = []

    registrar_block = agg.get("registrar_block") or {}
    detected = registrar_block.get("detected")

    # Check 1 — no registrar block detected anywhere (MEDIUM)
    if detected == "no":
        flags.append(Flag(
            rule_code="PHYS_002",
            rule_description="No registrar attestation found",
            severity="medium",
            category="SP-4",
            rationale=(
                "No registrar block (name, signature, or title) was detected anywhere on the "
                "document after scanning headers, footers, and margins. Authentic official "
                "transcripts are attested by the institution's registrar."
            ),
            source_location=_src(agg, "registrar_block"),
        ))
        return flags

    # Check 2 — block detected but entirely uninformative (MEDIUM)
    # Only fires when all three identifiers are simultaneously absent.
    if (
        detected == "yes"
        and registrar_block.get("signature_present") == "no"
        and registrar_block.get("name_text") is None
        and registrar_block.get("title_text") is None
    ):
        flags.append(Flag(
            rule_code="PHYS_002",
            rule_description="Registrar block present but lacks identifying information",
            severity="medium",
            category="SP-4",
            rationale=(
                "A registrar section was detected but provides no signature, no printed name, "
                "and no official title. A block with none of these identifiers does not satisfy "
                "the attestation requirement for an official transcript."
            ),
            source_location=_src(agg, "registrar_block"),
        ))

    # detected == "unclear" → defer to reviewer; no flag.
    return flags


def check_phys_003(agg: dict) -> list:
    """Print technology anachronism — anachronistic year for technology and mixed tech across pages."""
    flags = []
    tech = agg.get("print_technology")

    # Both checks skip if print_technology is "unclear"
    if tech == "unclear":
        return []

    # Check 1 — print tech anachronistic for issue year (MEDIUM)
    # Skip if reissue_markers_detected == True
    if not agg.get("reissue_markers_detected"):
        issue_year = _parse_year(agg.get("document_issue_date"))
        if tech and issue_year is not None:
            window = _PRINT_TECH_WINDOW.get(tech)
            if window is not None:
                year_from, year_to = window
                if issue_year < year_from:
                    flags.append(Flag(
                        rule_code="PHYS_003",
                        rule_description="Print technology predates its plausibility window",
                        severity="medium",
                        category="SP-4",
                        rationale=(
                            f"'{tech}' printing was not widely available until approximately "
                            f"{year_from}, but the document issue date indicates {issue_year}. "
                            "A document using technology that did not yet exist is a fabrication indicator."
                        ),
                        source_location=_src(agg, "print_technology"),
                    ))
                elif year_to is not None and issue_year > year_to:
                    flags.append(Flag(
                        rule_code="PHYS_003",
                        rule_description="Print technology obsolete for claimed issue date",
                        severity="medium",
                        category="SP-4",
                        rationale=(
                            f"'{tech}' printing was uncommon after approximately {year_to}, "
                            f"but the document issue date indicates {issue_year}. "
                            "Anachronistic print technology is a fabrication indicator."
                        ),
                        source_location=_src(agg, "print_technology"),
                    ))

    # Check 2 — mixed print technology within document (HIGH)
    # Skip if document is single-page (tech_per_page has 0 or 1 entries)
    tech_per_page = agg.get("print_technology_per_page") or []
    if len(tech_per_page) > 1:
        unique_techs = {t for t in tech_per_page if t and t != "unclear"}
        if len(unique_techs) > 1:
            flags.append(Flag(
                rule_code="PHYS_003",
                rule_description="Mixed print technologies across document pages",
                severity="high",
                category="SP-4",
                rationale=(
                    f"Different print technologies detected across pages: "
                    f"{', '.join(sorted(unique_techs))}. "
                    "Real institutions print entire documents in one batch on one machine. "
                    "Mixed print technology strongly suggests pages were assembled from different sources."
                ),
                source_location=_src(agg, "print_technology_per_page"),
            ))

    return flags


def check_phys_004(agg: dict) -> list:
    """Text and print integrity — alignment, spacing, compression, fonts, correction marks, ink."""
    flags = []

    text_alignment = agg.get("text_alignment")
    compressed_numbers = agg.get("compressed_numbers_detected")
    mixed_fonts = agg.get("mixed_fonts_detected")
    correction_artifacts = agg.get("correction_artifacts_present")
    obliteration = agg.get("obliteration_marks_detected")
    mixed_ink = agg.get("mixed_ink_colors_in_field")
    printer_quality = agg.get("printer_quality_consistency")

    # Check 1 — text alignment irregular (MEDIUM); skip if "unclear"
    if text_alignment == "misaligned":
        flags.append(Flag(
            rule_code="PHYS_004",
            rule_description="Text alignment irregular",
            severity="medium",
            category="SP-4",
            rationale=(
                "Text baselines or column edges are visibly misaligned. "
                "Irregular alignment is inconsistent with institutional printing standards "
                "and may indicate inserted or manually appended content."
            ),
            source_location=_src(agg, "text_alignment"),
        ))

    # Check 2 — irregular letter/word spacing (MEDIUM)
    if text_alignment == "uneven_spacing":
        flags.append(Flag(
            rule_code="PHYS_004",
            rule_description="Irregular letter or word spacing detected",
            severity="medium",
            category="SP-4",
            rationale=(
                "Uneven spacing between characters or words was detected. "
                "Irregular spacing may indicate character insertion or post-printing modification."
            ),
            source_location=_src(agg, "text_alignment"),
        ))

    # Check 3 — compressed or squeezed numbers (HIGH)
    if compressed_numbers is True:
        flags.append(Flag(
            rule_code="PHYS_004",
            rule_description="Compressed or squeezed numbers detected",
            severity="high",
            category="SP-4",
            rationale=(
                "Numbers appear compressed or squeezed to fit available space. "
                "Compressed numerals are a classic indicator of grade or GPA alteration — "
                "a digit was inserted into a fixed-width field."
            ),
            source_location=_src(agg, "compressed_numbers_detected"),
        ))

    # Check 4 — mixed font styles within document (HIGH)
    if mixed_fonts is True:
        flags.append(Flag(
            rule_code="PHYS_004",
            rule_description="Mixed font styles within document",
            severity="high",
            category="SP-4",
            rationale=(
                "Different fonts, sizes, or weights appear inconsistently across the document. "
                "Authentic transcripts are printed in a consistent typeface; mixed fonts suggest "
                "content was inserted from a different source."
            ),
            source_location=_src(agg, "mixed_fonts_detected"),
        ))

    # Check 5 — correction fluid or erasure marks (HIGH)
    if correction_artifacts is True:
        flags.append(Flag(
            rule_code="PHYS_004",
            rule_description="Correction fluid or erasure marks present",
            severity="high",
            category="SP-4",
            rationale=(
                "Visible correction fluid, erasures, or smudges were detected. "
                "Physical tampering with a printed document is a direct forgery indicator."
            ),
            source_location=_src(agg, "correction_artifacts_present"),
        ))

    # Check 6 — obliterated or interrupted text (HIGH)
    if obliteration is True:
        flags.append(Flag(
            rule_code="PHYS_004",
            rule_description="Obliterated or interrupted text detected",
            severity="high",
            category="SP-4",
            rationale=(
                "Words appear crossed out, obliterated, or interrupted without explanation. "
                "Unexplained text obliteration is a physical tampering indicator."
            ),
            source_location=_src(agg, "obliteration_marks_detected"),
        ))

    # Check 7 — mixed ink colors in same field (HIGH)
    if mixed_ink is True:
        flags.append(Flag(
            rule_code="PHYS_004",
            rule_description="Mixed ink colors within same field",
            severity="high",
            category="SP-4",
            rationale=(
                "Different ink colors appear within the same field (e.g., the grade column). "
                "Mixed ink in a single field indicates handwritten changes were added after "
                "the document was originally created."
            ),
            source_location=_src(agg, "mixed_ink_colors_in_field"),
        ))

    # Check 8 — printer quality inconsistency (MEDIUM)
    if printer_quality == "inconsistent":
        flags.append(Flag(
            rule_code="PHYS_004",
            rule_description="Printer quality inconsistency detected",
            severity="medium",
            category="SP-4",
            rationale=(
                "Blurry letters mixed with clear letters, or uneven print density, was detected. "
                "Quality inconsistency within a single document suggests content was printed "
                "on different equipment."
            ),
            source_location=_src(agg, "printer_quality_consistency"),
        ))

    return flags


def check_phys_005(agg: dict) -> list:
    """Document completeness markers — degree conferral statement and conferral date."""
    flags = []

    statement_present = agg.get("degree_conferral_statement_present")
    conferred_date = agg.get("degree_conferred_date")

    # Check 1 — degree conferral statement present (HIGH)
    if statement_present is False:
        flags.append(Flag(
            rule_code="PHYS_005",
            rule_description="Degree conferral statement absent",
            severity="high",
            category="SP-4",
            rationale=(
                "No degree conferral statement was found (e.g., 'Student has completed "
                "requirements for [degree]' or 'Degrees Earned: Nursing'). "
                "An official transcript for a completed program must state that the degree "
                "was conferred."
            ),
            source_location=_src(agg, "degree_conferral_statement_present"),
        ))
        # Check 2 is skipped: cannot have a date for a degree that is not stated
        return flags

    # Check 2 — degree conferred date present (HIGH)
    # Only evaluates when a conferral statement was found (statement_present is True)
    if statement_present is True and not conferred_date:
        flags.append(Flag(
            rule_code="PHYS_005",
            rule_description="Degree conferral date absent",
            severity="high",
            category="SP-4",
            rationale=(
                "A degree conferral statement was found but no specific conferral date "
                "(month/day/year) was provided. Authentic transcripts specify the exact "
                "date the degree was conferred."
            ),
            source_location=_src(agg, "degree_conferred_date"),
        ))

    return flags

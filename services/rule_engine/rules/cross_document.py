"""Cross-document consistency rules (CROSS_001 – CROSS_003).

SP-1 (identity verification) and SP-4 (document authenticity).

These rules evaluate fields that the AggregationLambda computed by comparing
fields across all documents in the application (transcript, diploma, CEA report,
affidavit of graduation).  They do NOT re-read individual extraction files.

Each function accepts an aggregation dict and returns list[Flag].

Aggregation fields consumed (see design/extraction-vocabulary.md Section 4):
  applicant_name_match            : match | mismatch | insufficient_data
  institution_name_match          : match | mismatch | insufficient_data
  dates_match_across_documents    : match | mismatch_greater_than_90_days | insufficient_data
  signature_match_across_documents: match | mismatch | insufficient_data  (advisory)
"""

from rules.base import Flag, _src


def check_cross_001(agg: dict) -> list:
    """CROSS_001 — Applicant name differs across submitted documents.

    Fires when the applicant name extracted from the transcript, diploma, and/or
    application does not match (beyond expected transliteration variation).
    """
    match = agg.get("applicant_name_match")
    if match == "mismatch":
        return [
            Flag(
                rule_code="CROSS_001",
                rule_description="Applicant name mismatch across documents",
                severity="high",
                category="SP-1",
                rationale=(
                    "The applicant name extracted from two or more submitted documents "
                    "(transcript, diploma, application, or licensure record) does not match "
                    "within expected transliteration variation. "
                    "Name inconsistency may indicate impersonation or document substitution."
                ),
                source_location=_src(agg, "applicant_name_match"),
            )
        ]
    return []


def check_cross_002(agg: dict) -> list:
    """CROSS_002 — Institution name differs across submitted documents.

    Fires when the institution name on the transcript does not match the diploma
    or credentials evaluation report (beyond normalized spelling differences).
    """
    match = agg.get("institution_name_match")
    if match == "mismatch":
        return [
            Flag(
                rule_code="CROSS_002",
                rule_description="Institution name mismatch across documents",
                severity="high",
                category="SP-4",
                rationale=(
                    "The institution name extracted from two or more submitted documents "
                    "(transcript, diploma, credentials evaluation report) does not match. "
                    "Institution name inconsistency may indicate that documents from different "
                    "institutions were combined or that one document was substituted."
                ),
                source_location=_src(agg, "institution_name_match"),
            )
        ]
    return []


def check_cross_003(agg: dict) -> list:
    """CROSS_003 — Graduation or completion dates differ across documents by > 90 days.

    Fires when the same graduation event is recorded with different dates on the
    transcript, diploma, and/or credentials evaluation report.
    """
    match = agg.get("dates_match_across_documents")
    if match == "mismatch_greater_than_90_days":
        return [
            Flag(
                rule_code="CROSS_003",
                rule_description="Graduation dates differ across documents by more than 90 days",
                severity="high",
                category="SP-4",
                rationale=(
                    "The graduation or completion date extracted from two or more submitted "
                    "documents differs by more than 90 days for the same event. "
                    "Date discrepancies of this magnitude across a transcript, diploma, and "
                    "credentials evaluation report are a strong indicator of document forgery "
                    "or substitution."
                ),
                source_location=_src(agg, "dates_match_across_documents"),
            )
        ]
    return []

"""Base types for the MSBN rule engine.

Every rule function takes an aggregation dict (loaded from aggregation.json)
and returns list[Flag]. An empty list means the rule did not fire.

Flag fields
-----------
rule_code       : e.g. "PHYS_001"
rule_description: short label matching requirements-draft.md
severity        : "high" | "medium" | "low"  (public-safety risk if undetected)
category        : Safe Practice category, "SP-1" through "SP-10"
rationale       : human-readable explanation of WHY the rule fired, referencing
                  the specific extracted values that triggered it
source_location : dict with page_number and text_spans copied from the
                  aggregation field that triggered the rule; None if unavailable
timestamp       : ISO-8601 UTC string, set at evaluation time
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional


@dataclass
class Flag:
    rule_code: str
    rule_description: str
    severity: str
    category: str
    rationale: str
    source_location: Optional[dict]
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def to_dict(self) -> dict:
        return {
            "rule_code": self.rule_code,
            "rule_description": self.rule_description,
            "severity": self.severity,
            "category": self.category,
            "rationale": self.rationale,
            "source_location": self.source_location,
            "timestamp": self.timestamp,
        }


def _src(agg: dict, field_name: str) -> Optional[dict]:
    """Return the source_location dict for a given aggregation field, or None."""
    return agg.get(f"{field_name}_source")

"""Shared rule engine types."""

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
    """Return the source metadata paired with an aggregation field."""
    return agg.get(f"{field_name}_source")

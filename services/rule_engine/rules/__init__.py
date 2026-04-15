"""Rule registry for the MSBN rule engine.

Each rule function accepts an aggregation dict and returns list[Flag].
The engine iterates ALL_RULES and collects every flag that fires.

Population-level rules (POP_001, POP_002, POP_003) require cross-application
data and are NOT run here. They run in PopulationCheckLambda.
TODO: When PopulationCheckLambda is implemented, import and run:
    from population_check.rules import check_pop_001, check_pop_002, check_pop_003
"""

from rules.content import (
    check_cont_001,
    check_cont_002,
    check_cont_003,
    check_cont_004,
    check_cont_005,
    check_cont_006,
)
from rules.physical import (
    check_phys_001,
    check_phys_002,
    check_phys_003,
    check_phys_004,
    check_phys_005,
)
from rules.program import (
    check_prog_001,
    check_prog_002,
    check_prog_003,
)

ALL_RULES = [
    # SP-4 — Physical document authenticity
    check_phys_001,
    check_phys_002,
    check_phys_003,
    check_phys_004,
    check_phys_005,
    # SP-5 — Educational content and chronology
    check_cont_001,
    check_cont_002,
    check_cont_003,
    check_cont_004,
    check_cont_005,
    check_cont_006,
    # SP-5 / SP-4 — Program authenticity
    check_prog_001,
    check_prog_002,
    check_prog_003,
    # SP-1 / SP-4 — Cross-document consistency (CROSS_001–003 deferred to Phase 4;
    # MSBN confirmed transcript-only scope for the POC on 2026-04-15)
]

RULE_CODES = [
    "PHYS_001", "PHYS_002", "PHYS_003", "PHYS_004", "PHYS_005",
    "CONT_001", "CONT_002", "CONT_003", "CONT_004", "CONT_005", "CONT_006",
    "PROG_001", "PROG_002", "PROG_003",
    # CROSS_001, CROSS_002, CROSS_003 deferred to Phase 4 (multi-document support)
]

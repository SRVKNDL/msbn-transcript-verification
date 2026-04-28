"""Rule registry for single-document transcript checks."""

from rules.content import (
    check_cont_001,
    check_cont_002,
    check_cont_003,
    check_cont_004,
)
from rules.physical import (
    check_phys_001,
    check_phys_002,
    check_phys_003,
    check_phys_004,
    check_phys_005,
    check_phys_006,
)
from rules.program import (
    check_prog_001,
    check_prog_002,
    check_prog_003,
    check_prog_004,
)

ALL_RULES = [
    # SP-4: physical document authenticity.
    check_phys_001,
    check_phys_002,
    check_phys_003,
    check_phys_004,
    check_phys_005,
    check_phys_006,
    # SP-5: educational content and chronology.
    check_cont_001,
    check_cont_002,
    check_cont_003,
    check_cont_004,
    # MS PN curriculum checks.
    check_prog_001,
    check_prog_002,
    check_prog_003,
    check_prog_004,
    # CROSS_001-003 stay deferred until multi-document upload support.
]

RULE_CODES = [
    "PHYS_001", "PHYS_002", "PHYS_003", "PHYS_004", "PHYS_005", "PHYS_006",
    "CONT_001", "CONT_002", "CONT_003", "CONT_004",
    "PROG_001", "PROG_002", "PROG_003", "PROG_004",
    # CROSS_001-003 deferred to Phase 4.
]

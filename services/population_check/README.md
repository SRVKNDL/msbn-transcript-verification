# PopulationCheckLambda

Applies population-level validation rules across all applications in the system.

**Responsibilities:**
- POP_001: Detect duplicate license numbers via DynamoDB GSI2 (LicenseDedup)
- POP_002: Flag curricula with low overlap within an institution cluster via GSI3
- POP_003: Flag submission volume anomalies (>3x baseline) via GSI3
- Write FLAG items to DynamoDB (advisory-only, Low severity until thresholds are validated)

**Note:** POP_002/003 activate only when a cluster of 3+ applications exists for a given institution/program/year.

**Runtime:** Python 3.11

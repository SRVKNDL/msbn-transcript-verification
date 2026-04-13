# RuleEngineLambda

Applies single-document validation rules against structured extraction output.

**Responsibilities:**
- Load extraction JSON and reference lookup tables from S3
- Apply all PHYS (physical document) rules: seal quality, print technology, signatures
- Apply all CONT (content) rules: GPA consistency, date logic, course names, language
- Apply all PROG (program) rules: accreditation, diploma mill phrases, program duration
- Write each generated flag as a FLAG item in DynamoDB with rule code, severity, rationale, and source location

**Rules are pure Python functions.** Thresholds are defined in `rules_config.yaml`, not hardcoded.

**Runtime:** Python 3.11

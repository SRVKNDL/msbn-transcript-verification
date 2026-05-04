# RuleEngineLambda

Applies single-document validation rules against structured extraction output.

## Responsibilities

- Load `aggregation.json` from S3
- Apply deterministic transcript rules from `rules/`
- Generate `FLAG` items with rule code, rationale, severity, and source location
- Replace stale flags for the same application before writing new ones

## Rule Families

- `PHYS`: physical document integrity checks
- `CONT`: content consistency and transcript logic checks
- `PROG`: program and curriculum validation checks

## Notes

- Rules are pure Python functions over the flattened aggregation document.
- The handler returns `flag_count` to Step Functions and the serialized flags
  for tests and debugging.

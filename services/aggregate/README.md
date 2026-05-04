# AggregationLambda

Flattens page-level extraction into the single transcript document consumed by
the rule engine.

## Responsibilities

- Read `extraction_transcript.json` from S3
- Merge page-level scalar fields using confidence-aware selection
- Merge arrays such as courses, semesters, programs, and security features
- Apply document-level derived fields and aliases
- Write `processed/{applicationId}/aggregation.json`

## Input

Step Functions event fields:

- `applicationId`
- `extraction_s3_key`
- optional `bucket`

## Output

Returns:

```json
{
  "applicationId": "<id>",
  "aggregation_s3_key": "processed/<id>/aggregation.json"
}
```

## Notes

- The current implementation is transcript-only.
- This Lambda does not perform cross-document comparison.

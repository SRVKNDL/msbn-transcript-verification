# QueueForReviewLambda

Final workflow step that moves an evaluated application into the reviewer queue.

## Responsibilities

- Read the flattened aggregation document from S3
- Update the DynamoDB `METADATA` item with:
  - `status = READY_FOR_REVIEW`
  - `flag_count`
  - reviewer-facing metadata such as applicant name, institution, country,
    license number, and program year when available
- Write a system `AUDIT` record recording the status change

## Input

Step Functions event fields:

- `applicationId`
- `flag_count`
- `aggregation_s3_key`
- `bucket`

## Output

```json
{
  "applicationId": "<id>",
  "status": "READY_FOR_REVIEW",
  "flag_count": 3
}
```

## Notes

- This Lambda does not send SNS or email notifications.
- Its primary job is queue state transition plus audit persistence.

# Intake Lambda

The Intake Lambda is the entry point for every application that enters the pipeline. When an
MSBN staff member uploads a PDF to the `uploads/` prefix of the transcripts S3 bucket, S3
fires an `ObjectCreated` event notification that invokes this function. For each record in
the event, the handler generates a UUID v4 `applicationId`, writes a `METADATA` item to
DynamoDB, and starts a Step Functions Standard Workflow execution. If the Step Functions call
fails, the handler re-raises the exception so the S3 event source retries delivery.

## Trigger

S3 `ObjectCreated` event on the `uploads/` prefix of the transcripts bucket. The event can
contain multiple records; the handler processes each one independently.

## DynamoDB METADATA record

Written to `msbn-applications` with `PK = APP#{applicationId}`, `SK = METADATA`.

```json
{
  "PK": "APP#a7f3b2c1-...",
  "SK": "METADATA",
  "entity_type": "METADATA",
  "applicationId": "a7f3b2c1-...",
  "status": "INTAKE_COMPLETE",
  "uploadedAt": "2026-04-14T18:32:01.123456+00:00",
  "s3Key": "uploads/transcript_smith_jane.pdf",
  "originalFilename": "transcript_smith_jane.pdf",
  "size_bytes": 204800
}
```

Status is set to `INTAKE_COMPLETE` at write time. The Step Functions pipeline updates it to
`EXTRACTING`, `EVALUATING`, `READY_FOR_REVIEW`, or `FAILED` as it progresses.

## Step Functions execution input

The execution name is set to `applicationId` for idempotency (one application → one
execution, easy to correlate in CloudWatch and the Step Functions console). The `pk` field
is precomputed so the pipeline's catch handler can write a `FAILED` status to DynamoDB
without a string-format intrinsic step.

```json
{
  "applicationId": "a7f3b2c1-...",
  "bucket": "msbn-transcripts-dev",
  "s3Key": "uploads/transcript_smith_jane.pdf",
  "pk": "APP#a7f3b2c1-..."
}
```

## Environment variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `TABLE_NAME` | No | `msbn-applications` | DynamoDB table name |
| `STATE_MACHINE_ARN` | Yes | `""` | ARN of the Step Functions pipeline |

The bucket name is read from the S3 event record, not from an environment variable.

## Running tests locally

```
make test
```

Tests use `moto` to mock DynamoDB and Step Functions. The `boto3` clients are constructed at
module level (one cold-start per test session) and patched by `moto` before each test
function runs.

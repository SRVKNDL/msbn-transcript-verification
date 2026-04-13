"""IntakeLambda — S3 PUT event → DynamoDB application record.

Triggered by S3 ObjectCreated events on the transcripts bucket (uploads/ prefix).
For each uploaded PDF, generates a unique applicationId, creates a METADATA item in
DynamoDB, and emits a structured JSON log.  Step Functions invocation is deferred to
the next slice; see the TODO block below.
"""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import unquote_plus

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Module-level resource is created once per cold start and re-used across
# warm invocations.  boto3.resource() makes no network calls at construction
# time, so moto can safely patch the underlying botocore session later.
_dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
_TABLE_NAME = os.environ.get("TABLE_NAME", "msbn-applications")


def handler(event: dict, context) -> dict:
    """Process S3 event notification for one or more new document uploads.

    Returns a statusCode-200 response dict.  S3 event sources do not use the
    return value, but a well-formed response keeps CloudWatch logs clean and
    simplifies local integration testing.
    """
    records = event.get("Records", [])
    if not records:
        logger.warning(json.dumps({"message": "IntakeLambda: no Records in event"}))
        return {"statusCode": 200, "body": json.dumps({"processed": 0})}

    results = []
    for record in records:
        results.append(_process_record(record))

    return {
        "statusCode": 200,
        "body": json.dumps({"processed": len(results), "applications": results}),
    }


def _parse_s3_record(record: dict) -> tuple:
    """Return (bucket, s3_key, size_bytes, original_filename) from an S3 event record.

    Raises ValueError on missing required fields or an unparseable key so the
    caller can decide whether to skip, dead-letter, or re-raise.
    """
    try:
        s3_info = record["s3"]
        bucket: str = s3_info["bucket"]["name"]
        raw_key: str = s3_info["object"]["key"]
        size_bytes: int = int(s3_info["object"].get("size", 0))
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Malformed S3 event record: {exc}") from exc

    # S3 notification keys are URL-encoded (spaces → '+', specials → '%XX').
    s3_key = unquote_plus(raw_key)

    # Extract the last path component as the display filename.
    original_filename = s3_key.rsplit("/", 1)[-1] if "/" in s3_key else s3_key
    if not original_filename:
        raise ValueError(f"Cannot derive filename from S3 key: {s3_key!r}")

    return bucket, s3_key, size_bytes, original_filename


def _process_record(record: dict) -> dict:
    """Write a METADATA item to DynamoDB and return the new applicationId."""
    bucket, s3_key, size_bytes, original_filename = _parse_s3_record(record)

    # UUID v4 (stdlib) chosen to avoid extra dependencies.
    # ULID (python-ulid) would be preferable in production: its time-sortable
    # property aligns with the GSI1-ReviewQueue access pattern and makes IDs
    # naturally ordered in logs and DynamoDB scans.
    application_id = str(uuid.uuid4())
    uploaded_at = datetime.now(timezone.utc).isoformat()

    table = _dynamodb.Table(_TABLE_NAME)
    item = {
        "PK": f"APP#{application_id}",
        "SK": "METADATA",
        "entity_type": "METADATA",
        "applicationId": application_id,
        "status": "INTAKE_COMPLETE",
        "uploadedAt": uploaded_at,
        "s3Key": s3_key,
        "originalFilename": original_filename,
        "size_bytes": size_bytes,
    }
    table.put_item(Item=item)

    logger.info(
        json.dumps(
            {
                "message": "IntakeLambda processed upload",
                "applicationId": application_id,
                "s3Key": s3_key,
                "originalFilename": original_filename,
                "size_bytes": size_bytes,
                "status": "INTAKE_COMPLETE",
            }
        )
    )

    # TODO: Start Step Functions execution with applicationId and document manifest.
    #
    #   sfn = boto3.client("stepfunctions", region_name="us-east-1")
    #   sfn.start_execution(
    #       stateMachineArn=os.environ["STATE_MACHINE_ARN"],
    #       name=application_id,
    #       input=json.dumps({
    #           "applicationId": application_id,
    #           "bucket": bucket,
    #           "s3Key": s3_key,
    #           "originalFilename": original_filename,
    #       }),
    #   )

    return {"applicationId": application_id, "s3Key": s3_key}

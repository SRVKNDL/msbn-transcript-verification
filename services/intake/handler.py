"""S3 upload entry point for the transcript pipeline."""

import json
import logging
import os
import uuid
from datetime import datetime, timezone
from urllib.parse import unquote_plus

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Reuse clients across warm invocations.
_dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
_sfn = boto3.client("stepfunctions", region_name="us-east-1")
_s3 = boto3.client("s3", region_name="us-east-1")

_TABLE_NAME = os.environ.get("TABLE_NAME", "msbn-applications")
_STATE_MACHINE_ARN = os.environ.get("STATE_MACHINE_ARN", "")


def handler(event: dict, context) -> dict:
    """Process one or more S3 upload events."""

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
    """Pull bucket/key/size/filename out of an S3 event record."""
    try:
        s3_info = record["s3"]
        bucket: str = s3_info["bucket"]["name"]
        raw_key: str = s3_info["object"]["key"]
        size_bytes: int = int(s3_info["object"].get("size", 0))
    except (KeyError, TypeError) as exc:
        raise ValueError(f"Malformed S3 event record: {exc}") from exc

    s3_key = unquote_plus(raw_key)  # S3 URL-encodes the key

    if s3_key.endswith("/"):
        return bucket, s3_key, size_bytes, ""

    original_filename = s3_key.rsplit("/", 1)[-1] if "/" in s3_key else s3_key
    if not original_filename:
        raise ValueError(f"Cannot derive filename from S3 key: {s3_key!r}")

    return bucket, s3_key, size_bytes, original_filename


def _process_record(record: dict) -> dict:
    """Write METADATA to Dynamo, kick off the pipeline, return the new ID."""
    bucket, s3_key, size_bytes, original_filename = _parse_s3_record(record)

    if s3_key.endswith("/"):
        logger.info(
            json.dumps(
                {
                    "message": "IntakeLambda skipping S3 placeholder object",
                    "s3_key": s3_key,
                }
            )
        )
        return {"skipped": True, "s3_key": s3_key}

    # UUID is good enough for the POC; switch to ULID if queue ordering needs it.
    application_id = str(uuid.uuid4())
    uploaded_at = datetime.now(timezone.utc).isoformat()

    table = _dynamodb.Table(_TABLE_NAME)
    upload_metadata = _get_upload_metadata(bucket=bucket, s3_key=s3_key)
    item = {
        "PK": f"APP#{application_id}",
        "SK": "METADATA",
        "entity_type": "METADATA",
        "applicationId": application_id,
        "status": "INTAKE_COMPLETE",
        "uploadedAt": uploaded_at,
        "s3_key": s3_key,
        "originalFilename": original_filename,
        "size_bytes": size_bytes,
        **upload_metadata,
    }
    table.put_item(Item=item)

    logger.info(
        json.dumps(
            {
                "message": "IntakeLambda processed upload",
                "applicationId": application_id,
                "s3_key": s3_key,
                "originalFilename": original_filename,
                "size_bytes": size_bytes,
                "status": "INTAKE_COMPLETE",
            }
        )
    )

    _start_pipeline(application_id=application_id, bucket=bucket, s3_key=s3_key)

    return {"applicationId": application_id, "s3_key": s3_key}


def _get_upload_metadata(*, bucket: str, s3_key: str) -> dict:
    try:
        response = _s3.head_object(Bucket=bucket, Key=s3_key)
    except ClientError as exc:
        logger.warning(
            json.dumps(
                {
                    "message": "IntakeLambda could not read upload metadata",
                    "s3_key": s3_key,
                    "errorCode": exc.response["Error"]["Code"],
                }
            )
        )
        return {}

    metadata = response.get("Metadata") or {}
    return {
        "applicant_name": (
            metadata.get("applicant-name") or metadata.get("applicant_name") or ""
        ),
        "institution": metadata.get("institution") or "",
        "country": metadata.get("country") or "",
        "program": metadata.get("program") or "",
        "program_year": (
            metadata.get("program-year") or metadata.get("program_year") or ""
        ),
        "license_number": (
            metadata.get("license-number") or metadata.get("license_number") or ""
        ),
    }


def _start_pipeline(*, application_id: str, bucket: str, s3_key: str) -> None:
    """Fire off the SFN execution. Re-raises on failure so S3 retries."""
    execution_input = json.dumps(
        {
            "applicationId": application_id,
            "bucket": bucket,
            "s3_key": s3_key,
            # Step Functions can write FAILED without building the key itself.
            "pk": f"APP#{application_id}",
        }
    )
    try:
        response = _sfn.start_execution(
            stateMachineArn=_STATE_MACHINE_ARN,
            name=application_id,
            input=execution_input,
        )
        logger.info(
            json.dumps(
                {
                    "message": "IntakeLambda started Step Functions execution",
                    "applicationId": application_id,
                    "executionArn": response["executionArn"],
                }
            )
        )
    except ClientError as exc:
        logger.error(
            json.dumps(
                {
                    "message": "IntakeLambda: failed to start Step Functions execution",
                    "applicationId": application_id,
                    "error": str(exc),
                    "errorCode": exc.response["Error"]["Code"],
                }
            )
        )
        raise

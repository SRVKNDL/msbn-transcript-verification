"""Move evaluated applications into the reviewer queue."""

import json
import logging
import os
from datetime import datetime, timezone

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ["TABLE_NAME"]
BUCKET_NAME = os.environ.get("BUCKET_NAME", "")

_dynamo = boto3.resource("dynamodb")
_table = _dynamo.Table(TABLE_NAME)
_s3 = boto3.client("s3")


def handler(event, context):
    """Transition application to READY_FOR_REVIEW and record the audit event."""

    application_id = event["applicationId"]
    flag_count = int(event.get("flag_count", 0))
    aggregation = _read_aggregation(event)

    now = datetime.now(timezone.utc).isoformat()

    logger.info(
        json.dumps(
            {
                "applicationId": application_id,
                "action": "queue_for_review_start",
                "flag_count": flag_count,
            }
        )
    )

    # UpdateItem handles retries where METADATA may already exist.
    # "status" is reserved, so use an expression name.
    update_expression = (
        "SET #st = :status,"
        " flag_count = :fc,"
        " ready_for_review_at = :ts,"
        " last_updated_ts = :ts,"
        " submission_ts = :ts,"
        " applicant_name = :applicant,"
        " institution = :institution,"
        " country = :country"
    )
    expression_values = {
        ":status": "READY_FOR_REVIEW",
        ":fc": flag_count,
        ":ts": now,
        ":applicant": _clean_value(aggregation.get("applicant_name"))
        or "Unknown applicant",
        ":institution": _clean_value(aggregation.get("institution"))
        or "Unknown institution",
        ":country": _clean_value(aggregation.get("country")) or "USA",
    }

    license_number = _clean_value(aggregation.get("license_number"))
    if license_number:
        update_expression += ", license_number = :license"
        expression_values[":license"] = license_number

    program_year = _clean_value(aggregation.get("program_year"))
    if program_year:
        update_expression += ", program_year = :program_year"
        expression_values[":program_year"] = program_year

    _table.update_item(
        Key={"PK": f"APP#{application_id}", "SK": "METADATA"},
        UpdateExpression=update_expression,
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues=expression_values,
    )

    # Timestamp in SK keeps audit records naturally ordered.
    _table.put_item(
        Item={
            "PK": f"APP#{application_id}",
            "SK": f"AUDIT#{now}",
            "entity_type": "AUDIT",
            "actor": "system",
            "event_type": "STATUS_CHANGED",
            "previous_state": {"status": "EVALUATING"},
            "new_state": {
                "status": "READY_FOR_REVIEW",
                "flag_count": flag_count,
            },
            "timestamp": now,
            "applicationId": application_id,
        }
    )

    logger.info(
        json.dumps(
            {
                "applicationId": application_id,
                "action": "queue_for_review_complete",
                "status": "READY_FOR_REVIEW",
                "flag_count": flag_count,
            }
        )
    )

    return {
        "applicationId": application_id,
        "status": "READY_FOR_REVIEW",
        "flag_count": flag_count,
    }


def _read_aggregation(event: dict) -> dict:
    """Load flattened transcript metadata if the workflow provided it."""
    key = event.get("aggregation_s3_key")
    bucket = event.get("bucket") or BUCKET_NAME
    if not key or not bucket:
        return {}

    try:
        obj = _s3.get_object(Bucket=bucket, Key=key)
        return json.loads(obj["Body"].read().decode("utf-8"))
    except Exception:
        logger.exception(
            "QueueForReviewLambda could not read aggregation metadata",
            extra={"applicationId": event.get("applicationId"), "key": key},
        )
        return {}


def _clean_value(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"unclear", "unknown", "null", "none", "n/a"}:
        return None
    return text

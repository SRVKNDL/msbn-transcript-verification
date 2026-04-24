"""Move evaluated applications into the reviewer queue."""

import json
import logging
import os
from datetime import datetime, timezone

import boto3

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ["TABLE_NAME"]

_dynamo = boto3.resource("dynamodb")
_table = _dynamo.Table(TABLE_NAME)


def handler(event, context):
    """Transition application to READY_FOR_REVIEW and record the audit event."""

    application_id = event["applicationId"]
    flag_count = int(event.get("flag_count", 0))

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
    _table.update_item(
        Key={"PK": f"APP#{application_id}", "SK": "METADATA"},
        UpdateExpression=(
            "SET #st = :status,"
            " flag_count = :fc,"
            " ready_for_review_at = :ts,"
            " last_updated_ts = :ts,"
            " submission_ts = :ts"
        ),
        ExpressionAttributeNames={"#st": "status"},
        ExpressionAttributeValues={
            ":status": "READY_FOR_REVIEW",
            ":fc": flag_count,
            ":ts": now,
        },
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

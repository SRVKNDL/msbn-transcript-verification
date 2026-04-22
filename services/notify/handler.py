"""QueueForReviewLambda: Final Step Functions pipeline state.

Marks an application as READY_FOR_REVIEW in DynamoDB and appends an
AUDIT record so the dashboard timeline (SP-9) shows a complete history.

Input (from Step Functions, forwarded from ValidateLambda):
    {
        "applicationId": "<id>",
        "flag_count": <int>,
        "flags": [...]        # list forwarded for reference; not stored here
    }

Output (returned to Step Functions):
    {
        "applicationId": "<id>",
        "status": "READY_FOR_REVIEW",
        "flag_count": <int>
    }

DynamoDB writes
---------------
1. UpdateItem on the METADATA record (PK=APP#<id>, SK=METADATA):
   - status          → "READY_FOR_REVIEW"
   - flag_count      → int
   - ready_for_review_at → ISO-8601 UTC
   - last_updated_ts → ISO-8601 UTC
   - submission_ts   → ISO-8601 UTC  (GSI1-ReviewQueue sort key: oldest first)

2. PutItem for an AUDIT record (PK=APP#<id>, SK=AUDIT#<timestamp>):
   - entity_type  → "AUDIT"
   - actor        → "system"
   - event_type   → "STATUS_CHANGED"
   - previous_state → {"status": "EVALUATING"}
   - new_state    → {"status": "READY_FOR_REVIEW", "flag_count": <int>}
"""

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

    # ── 1. Update METADATA ─────────────────────────────────────────────────────
    # UpdateItem upserts: works whether or not METADATA exists yet.
    # Uses ExpressionAttributeNames to avoid the reserved word "status".
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

    # ── 2. Append AUDIT record ─────────────────────────────────────────────────
    # SK encodes the event time so audit items sort chronologically.
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

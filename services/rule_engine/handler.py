"""RuleEngineLambda: Deterministic rule engine for transcript fraud detection.

Reads aggregation.json from S3, applies every rule in the rules registry,
writes FLAG items to DynamoDB, and returns a summary to Step Functions.

Input event (from Step Functions):
    {
        "applicationId": "<id>",
        "aggregation_s3_key": "processed/<id>/aggregation.json"
    }

Output (returned to Step Functions):
    {
        "applicationId": "<id>",
        "flag_count": <int>,
        "flags": [ <flag dict>, ... ]
    }

DynamoDB item layout:
    PK  = APP#<applicationId>
    SK  = FLAG#<rule_code>#<seq:04d>
    entity_type = FLAG
    + all Flag fields (rule_code, rule_description, severity, category,
      rationale, source_location, timestamp)

No LLM calls are made here. All logic is pure Python against the structured
extraction vocabulary defined in design/extraction-vocabulary.md.
"""

import json
import logging
import os

import boto3

from rules import ALL_RULES

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ["TABLE_NAME"]
BUCKET_NAME = os.environ["BUCKET_NAME"]

_s3 = boto3.client("s3")
_dynamo = boto3.resource("dynamodb")
_table = _dynamo.Table(TABLE_NAME)


def handler(event, context):
    """Evaluate all fraud-detection rules against aggregation.json.

    Steps:
    1. Read aggregation.json from S3 (processed/ prefix).
    2. Run every rule in ALL_RULES; collect Flag objects.
    3. Write each flag as a FLAG item in DynamoDB.
    4. Return a summary dict to Step Functions.
    """

    application_id = event["applicationId"]
    s3_key = event["aggregation_s3_key"]

    logger.info(
        json.dumps(
            {
                "applicationId": application_id,
                "action": "validate_start",
                "s3_key": s3_key,
            }
        )
    )

    # ── 1. Read aggregation.json ───────────────────────────────────────────────
    response = _s3.get_object(Bucket=BUCKET_NAME, Key=s3_key)
    aggregation = json.loads(response["Body"].read().decode("utf-8"))

    # ── 2. Run rule engine ────────────────────────────────────────────────────
    flags = []
    for rule_fn in ALL_RULES:
        results = rule_fn(aggregation)
        flags.extend(results)

    # ── 3. Write FLAG items to DynamoDB ───────────────────────────────────────
    for seq, flag in enumerate(flags):
        item = {
            "PK": f"APP#{application_id}",
            "SK": f"FLAG#{flag.rule_code}#{seq:04d}",
            "entity_type": "FLAG",
            "applicationId": application_id,
            "rule_code": flag.rule_code,
            "rule_description": flag.rule_description,
            "severity": flag.severity,
            "category": flag.category,
            "rationale": flag.rationale,
            "timestamp": flag.timestamp,
        }
        if flag.source_location is not None:
            item["source_location"] = flag.source_location
        _table.put_item(Item=item)

    # ── 4. Return summary ─────────────────────────────────────────────────────
    flag_count = len(flags)
    logger.info(
        json.dumps(
            {
                "applicationId": application_id,
                "action": "validate_complete",
                "flag_count": flag_count,
            }
        )
    )

    return {
        "applicationId": application_id,
        "flag_count": flag_count,
        "flags": [f.to_dict() for f in flags],
    }

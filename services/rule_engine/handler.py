"""Run deterministic transcript rules and persist any flags."""

import json
import logging
import os

import boto3
from boto3.dynamodb.conditions import Key

from rules import ALL_RULES

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

TABLE_NAME = os.environ["TABLE_NAME"]
BUCKET_NAME = os.environ["BUCKET_NAME"]

_s3 = boto3.client("s3")
_dynamo = boto3.resource("dynamodb")
_table = _dynamo.Table(TABLE_NAME)


def handler(event, context):
    """Evaluate all registered rules against an aggregation document."""

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

    # Read the flattened document created by AggregationLambda.
    response = _s3.get_object(Bucket=BUCKET_NAME, Key=s3_key)
    aggregation = json.loads(response["Body"].read().decode("utf-8"))

    # Rules are pure functions over the aggregation dict.
    flags = []
    for rule_fn in ALL_RULES:
        results = rule_fn(aggregation)
        flags.extend(results)

    _delete_existing_flags(application_id)

    # Store flags under the application partition for the dashboard.
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

    # Step Functions only needs the count; tests also assert the flag payload.
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


def _delete_existing_flags(application_id: str) -> None:
    """Make validation idempotent by clearing stale flags for this application."""
    pk = f"APP#{application_id}"
    query_kwargs = {
        "KeyConditionExpression": Key("PK").eq(pk) & Key("SK").begins_with("FLAG#"),
        "ProjectionExpression": "PK, SK",
    }

    with _table.batch_writer() as batch:
        while True:
            response = _table.query(**query_kwargs)
            for item in response.get("Items", []):
                batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})

            last_key = response.get("LastEvaluatedKey")
            if not last_key:
                break
            query_kwargs["ExclusiveStartKey"] = last_key

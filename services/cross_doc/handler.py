"""CrossDocLambda: Applies cross-document validation rules across all documents in an application."""

import json
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event, context):
    """Run cross-document rules (CROSS_001-003) after all documents are extracted.

    Compares fields across multiple extraction JSONs for a single
    application (e.g., name consistency between transcript and diploma).
    """
    logger.info("CrossDocLambda invoked: %s", json.dumps(event))

    # TODO: Load all extraction JSONs for this application from S3
    # TODO: Apply CROSS_001 (name match), CROSS_002, CROSS_003
    # TODO: Write FLAG items to DynamoDB

    return {"statusCode": 200, "body": json.dumps({"message": "stub"})}

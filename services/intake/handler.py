"""IntakeLambda: Handles S3 upload events for new transcript applications."""

import json
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event, context):
    """Process S3 event notification for a new document upload.

    Creates an application record in DynamoDB with status RECEIVED,
    then starts a Step Functions workflow execution.
    """
    logger.info("IntakeLambda invoked: %s", json.dumps(event))

    # TODO: Parse S3 event to get bucket, key, application_id, doc_type
    # TODO: Create METADATA item in DynamoDB (status=RECEIVED)
    # TODO: Start Step Functions execution with application_id + document manifest

    return {"statusCode": 200, "body": json.dumps({"message": "stub"})}

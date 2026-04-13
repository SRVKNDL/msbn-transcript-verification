"""NotifyLambda: Sends email notifications to the reviewer queue via SNS."""

import json
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event, context):
    """Notify reviewers that an application is ready for review.

    Publishes to an SNS topic subscribed by the reviewer email list.
    """
    logger.info("NotifyLambda invoked: %s", json.dumps(event))

    # TODO: Extract application_id and flag summary from event
    # TODO: Publish notification to SNS topic

    return {"statusCode": 200, "body": json.dumps({"message": "stub"})}

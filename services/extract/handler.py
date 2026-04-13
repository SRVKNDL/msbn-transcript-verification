"""ExtractLambda: Converts PDF pages to images and calls Bedrock Nova for structured extraction."""

import json
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event, context):
    """Extract structured data from a single document.

    Steps:
    1. Retrieve PDF from S3
    2. Convert each page to PNG (poppler/pdf2image)
    3. Write page images to S3 processed/ prefix
    4. Call Bedrock Nova per page with extraction prompt
    5. Aggregate into extraction.json and write to S3
    6. Update DynamoDB document status to EXTRACTED
    """
    logger.info("ExtractLambda invoked: %s", json.dumps(event))

    # TODO: Implement extraction pipeline (see architecture-plan.md Section 1.3)

    return {"statusCode": 200, "body": json.dumps({"message": "stub"})}

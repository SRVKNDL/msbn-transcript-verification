"""AggregationLambda: Cross-document field comparison for a single application.

Runs after all per-document ExtractLambda invocations complete.
Reads every extraction_{doc_type}.json for the application, compares
cross-document fields (signature, institution name, applicant name,
enrollment dates), and writes aggregation.json to S3.

See: design/extraction-vocabulary.md Section 4 for the CROSS_* field definitions.
See: design/architecture-plan.md Section 1.4 for the aggregation step context.
"""

import json
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


def handler(event, context):
    """Compare cross-document fields across all extractions for an application.

    Steps:
    1. Read all extraction_{doc_type}.json files from S3 processed/ prefix
    2. Populate CROSS_* fields (signature_match_across_documents,
       institution_name_match, applicant_name_match,
       dates_match_across_documents)
    3. Write aggregation.json to S3 processed/{application_id}/
    4. Update DynamoDB with the aggregation S3 path
    """
    logger.info("AggregationLambda invoked: %s", json.dumps(event))

    # TODO: Read extraction JSONs for this application from S3
    # TODO: Compare cross-document fields (see extraction-vocabulary.md Section 4)
    # TODO: Write aggregation.json to S3
    # TODO: Update DynamoDB with aggregation S3 path

    return {"status": "ok"}

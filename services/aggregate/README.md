# AggregationLambda

Compares cross-document fields across all extracted documents for a single application.

**Responsibilities:**
- Read all `extraction_{doc_type}.json` files for an application from S3
- Populate the Section 4 `CROSS_*` vocabulary fields (`signature_match_across_documents`,
  `institution_name_match`, `applicant_name_match`, `dates_match_across_documents`)
- Write `processed/{application_id}/aggregation.json` to S3
- Update DynamoDB with the aggregation S3 path

**Trigger:** Step Functions state after the parallel Extract Map state completes
**Runtime:** Python 3.11
**Downstream:** CrossDocLambda reads `aggregation.json` to evaluate `CROSS_001–003` rules

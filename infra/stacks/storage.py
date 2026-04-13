"""Storage construct: S3 bucket and DynamoDB single-table.

S3 bucket layout (see architecture-plan.md Section 4.1):
  - raw/          Immutable uploaded PDFs
  - processed/    Extraction JSON, page images
  - reference/    Lookup tables (accreditation, grade scales, etc.)
  - frontend/     React build artifacts (served via CloudFront)

DynamoDB single-table design (see architecture-plan.md Section 4.2):
  - Table: msbn-applications
  - PK: APP#{application_id}
  - SK: METADATA | DOCUMENT#{doc_type} | FLAG#{rule}#{seq} | AUDIT#{ts} | DECISION
  - GSIs: ReviewQueue, LicenseDedup, InstitutionCluster
"""

from constructs import Construct


class StorageConstruct(Construct):
    """S3 bucket and DynamoDB table for the MSBN pipeline."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # TODO: Create S3 bucket (msbn-transcripts-{env}) with:
        #   - SSE-S3 encryption on all objects
        #   - Versioning enabled on raw/ prefix
        #   - Public access blocked
        #   - Event notification for raw/ uploads (triggers IntakeLambda)

        # TODO: Create DynamoDB table (msbn-applications) with:
        #   - On-demand billing mode
        #   - PK (String), SK (String)
        #   - GSI1-ReviewQueue: status -> submission_ts
        #   - GSI2-LicenseDedup: license_number#country -> PK
        #   - GSI3-InstitutionCluster: institution#program#grad_year -> PK

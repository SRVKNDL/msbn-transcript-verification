"""Storage construct: S3 transcripts bucket and DynamoDB single-table.

S3 bucket layout (architecture-plan.md Section 4.1):
  uploads/    Raw uploaded PDFs (triggers IntakeLambda)
  processed/  Extraction JSON and per-page images
  reference/  Lookup tables (accreditation, grade scales, etc.)
  frontend/   React build artifacts (served via CloudFront)

DynamoDB single-table design (architecture-plan.md Section 4.2, Q11 provisional):
  Table:  msbn-applications
  PK:     APP#{applicationId}
  SK:     METADATA | DOCUMENT#{doc_type} | FLAG#{rule}#{seq}
          | AUDIT#{ISO8601} | DECISION

  GSI1-ReviewQueue:     status -> submission_ts  (dashboard list view)
  GSI2-LicenseDedup:    GSI2PK -> GSI2SK         (POP_001 dedup)
  GSI3-InstitutionCluster: GSI3PK -> GSI3SK      (POP_002/003 clustering)
"""

from aws_cdk import (
    RemovalPolicy,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
)
from constructs import Construct


class StorageConstruct(Construct):
    """S3 transcripts bucket and DynamoDB single-table for the MSBN pipeline."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── S3 bucket ──────────────────────────────────────────────────────────
        # Versioning on (architecture-plan.md Section 4.1: "Versioning is
        # enabled on raw/ prefix" — enabling at bucket level is the simplest
        # approach for a POC; prefix-level lifecycle rules can narrow it later).
        # SSE-S3 encryption: no extra key management cost at POC volume.
        # enforce_ssl: rejects plain-HTTP requests (Hub Guide security rule).
        # RETAIN on destroy: never accidentally delete applicant data in a
        # stack teardown.
        self.bucket = s3.Bucket(
            self,
            "TranscriptsBucket",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        # ── DynamoDB table ─────────────────────────────────────────────────────
        # On-demand billing: no capacity planning, zero idle cost.
        # PITR on: point-in-time recovery for the audit trail (SP-9).
        # RETAIN on destroy: same rationale as the bucket above.
        self.table = dynamodb.Table(
            self,
            "ApplicationsTable",
            table_name="msbn-applications",
            partition_key=dynamodb.Attribute(
                name="PK", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="SK", type=dynamodb.AttributeType.STRING
            ),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True,
            ),
            removal_policy=RemovalPolicy.RETAIN,
        )

        # GSI1-ReviewQueue ─────────────────────────────────────────────────────
        # Dashboard query: all applications with a given status, newest first.
        # Projection ALL because the dashboard needs the full METADATA item.
        self.table.add_global_secondary_index(
            index_name="GSI1-ReviewQueue",
            partition_key=dynamodb.Attribute(
                name="status", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="submission_ts", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.ALL,
        )

        # GSI2-LicenseDedup ────────────────────────────────────────────────────
        # POP_001: detect duplicate license number submissions.
        # GSI2PK stores the composite "license_number#country" value.
        # Sort key is the table PK (APP#{applicationId}) so a KEYS_ONLY query
        # returns the colliding applicationId directly, no second lookup needed.
        self.table.add_global_secondary_index(
            index_name="GSI2-LicenseDedup",
            partition_key=dynamodb.Attribute(
                name="GSI2PK", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="PK", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.KEYS_ONLY,
        )

        # GSI3-InstitutionCluster ──────────────────────────────────────────────
        # POP_002/003: cluster applications by institution + program + grad year.
        # GSI3PK stores the composite "institution#program#grad_year" value.
        # Sort key is the table PK for the same reason as GSI2.
        self.table.add_global_secondary_index(
            index_name="GSI3-InstitutionCluster",
            partition_key=dynamodb.Attribute(
                name="GSI3PK", type=dynamodb.AttributeType.STRING
            ),
            sort_key=dynamodb.Attribute(
                name="PK", type=dynamodb.AttributeType.STRING
            ),
            projection_type=dynamodb.ProjectionType.KEYS_ONLY,
        )

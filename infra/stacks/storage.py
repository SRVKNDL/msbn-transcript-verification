"""S3 and DynamoDB storage for the pipeline."""

from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_dynamodb as dynamodb,
    aws_s3 as s3,
)
from constructs import Construct


class StorageConstruct(Construct):
    """S3 transcripts bucket and DynamoDB single-table for the MSBN pipeline."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # Version raw and processed objects at bucket level for the POC.
        # Retain the bucket on stack teardown so case data is not deleted by CDK.
        self.bucket = s3.Bucket(
            self,
            "TranscriptsBucket",
            versioned=True,
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            enforce_ssl=True,
            removal_policy=RemovalPolicy.RETAIN,
            lifecycle_rules=[
                s3.LifecycleRule(
                    noncurrent_version_expiration=Duration.days(30),
                    abort_incomplete_multipart_upload_after=Duration.days(7),
                ),
            ],
        )

        # On-demand billing keeps the POC simple; PITR protects the audit trail.
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

        # Dashboard queue: status partition, submission time sort.
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

        # POP_001 lookup by normalized license number and country.
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

        # POP_002/003 lookup by institution, program, and graduation year.
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

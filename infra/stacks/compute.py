"""Compute construct: Lambda functions for the MSBN processing pipeline.

Lambda functions (architecture-plan.md Section 1):
  IntakeLambda          — zip deploy; S3-triggered
  ExtractLambda         — container image (poppler + pdf2image); Session 1 skeleton
  AggregationLambda     — stub (cross-document field comparison)
  RuleEngineLambda      — implemented (17 rules → 14 active)
  CrossDocLambda        — stub (Phase 4)
  PopulationCheckLambda — stub
  DashboardApiLambda    — stub
"""

import os

from aws_cdk import (
    Duration,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_s3 as s3,
)
from constructs import Construct

from stacks.storage import StorageConstruct


class ComputeConstruct(Construct):
    """Lambda functions for the MSBN transcript verification pipeline."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        storage: StorageConstruct,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ── IntakeLambda ───────────────────────────────────────────────────────
        # Triggered by S3 ObjectCreated events on uploads/.
        # Writes a METADATA item to DynamoDB; Step Functions start deferred.
        self.intake_lambda = lambda_.Function(
            self,
            "IntakeLambda",
            function_name="msbn-intake",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                os.path.normpath(
                    os.path.join(
                        os.path.dirname(__file__), "../../services/intake"
                    )
                )
            ),
            memory_size=512,
            timeout=Duration.seconds(30),
            # Hub Guide cost rule: retain logs for 7 days only.
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "TABLE_NAME": storage.table.table_name,
            },
        )

        # Least-privilege IAM ──────────────────────────────────────────────────
        # PutItem only: Intake never reads or modifies existing records.
        storage.table.grant(self.intake_lambda, "dynamodb:PutItem")

        # GetObject on uploads/ only: grants the Lambda access to inspect the
        # uploaded file in future slices without widening to the whole bucket.
        storage.bucket.grant_read(self.intake_lambda, "uploads/*")

        # S3 event notification is configured at the stack level to avoid
        # cross-stack cyclic dependencies when the bucket lives in a
        # separate stack.  See MsbnComputeStack for the wiring.

        # ── ExtractLambda ─────────────────────────────────────────────────────
        # Container image Lambda: poppler-utils + pdf2image + pillow exceed the
        # 250 MB zip limit, so this function uses a Docker image asset built
        # from services/extract/Dockerfile.  ECR is enabled (Q1 resolved).
        #
        # Session 2: Bedrock Nova invocation per page.
        #
        # IAM:
        #   s3:GetObject     on uploads/*   — download source PDF
        #   s3:PutObject     on processed/* — write page images + extraction JSON
        #   bedrock:InvokeModel scoped to Nova Lite and Pro ARNs in us-east-1
        #   dynamodb:PutItem on applications table — write DOCUMENT#TRANSCRIPT record
        # Runaway-Bedrock protection:
        # - Timeout caps per-invocation cost (180s vs the 15-min Lambda max).
        # - Reserved concurrency caps total parallel Bedrock spend in the
        #   event of an S3 event storm.
        self.extract_lambda = lambda_.DockerImageFunction(
            self,
            "ExtractLambda",
            function_name="msbn-extract",
            code=lambda_.DockerImageCode.from_image_asset(
                os.path.normpath(
                    os.path.join(
                        os.path.dirname(__file__), "../../services/extract"
                    )
                )
            ),
            # 2 GB: PDF rendering (pdf2image) and in-memory page images can be
            # large; 512 MB default causes OOM on multi-page transcripts.
            memory_size=2048,
            timeout=Duration.seconds(180),
            reserved_concurrent_executions=5,
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "BUCKET_NAME": storage.bucket.bucket_name,
                # Default to Nova Pro for better visual extraction fidelity on
                # faint transcript features such as watermarks and seal details.
                "BEDROCK_MODEL_ID": "amazon.nova-pro-v1:0",
            },
        )

        # Least-privilege IAM for ExtractLambda ───────────────────────────────
        # GetObject on uploads/*: download the source PDF.
        storage.bucket.grant_read(self.extract_lambda, "uploads/*")
        # PutObject on processed/*: write page images and extraction JSON.
        # grant_put also adds s3:AbortMultipartUpload for large-object uploads.
        storage.bucket.grant_put(self.extract_lambda, "processed/*")

        # bedrock:InvokeModel scoped to the two specific Nova models we use.
        # Nova Lite is the default; Nova Pro is the high-complexity fallback.
        self.extract_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0",
                    "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0",
                ],
            )
        )

        # PutItem to write the DOCUMENT#TRANSCRIPT record after extraction.
        # ExtractLambda never reads or updates existing items.
        storage.table.grant(self.extract_lambda, "dynamodb:PutItem")

        # ── AggregationLambda ─────────────────────────────────────────────────
        # Flattens per-page extraction JSON into a document-level aggregation.json
        # that ValidateLambda consumes. Winner-take-all (highest confidence) for
        # scalar fields; union-merge for array fields.
        # Cross-document comparison (Phase 4) will extend this same Lambda.
        self.aggregate_lambda = lambda_.Function(
            self,
            "AggregationLambda",
            function_name="msbn-aggregate",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                os.path.normpath(
                    os.path.join(
                        os.path.dirname(__file__), "../../services/aggregate"
                    )
                )
            ),
            memory_size=512,
            timeout=Duration.seconds(60),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "BUCKET_NAME": storage.bucket.bucket_name,
            },
        )

        # Least-privilege IAM for AggregationLambda ───────────────────────────
        # GetObject on processed/*: read extraction_transcript.json.
        # PutObject on processed/*: write aggregation.json.
        storage.bucket.grant_read(self.aggregate_lambda, "processed/*")
        storage.bucket.grant_put(self.aggregate_lambda, "processed/*")

        # ── ValidateLambda (RuleEngine) ────────────────────────────────────────
        # Deterministic rule engine: reads aggregation.json from S3, evaluates
        # PHYS/CONT/PROG/CROSS rules, writes FLAG items to DynamoDB.
        # No Bedrock calls — pure Python logic only.
        self.validate_lambda = lambda_.Function(
            self,
            "ValidateLambda",
            function_name="msbn-validate",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                os.path.normpath(
                    os.path.join(
                        os.path.dirname(__file__), "../../services/rule_engine"
                    )
                )
            ),
            memory_size=512,
            timeout=Duration.seconds(30),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "TABLE_NAME": storage.table.table_name,
                "BUCKET_NAME": storage.bucket.bucket_name,
            },
        )

        # Least-privilege IAM for ValidateLambda ──────────────────────────────
        # PutItem only: the rule engine writes FLAG records; it never modifies
        # existing application or metadata items.
        storage.table.grant(self.validate_lambda, "dynamodb:PutItem")

        # GetObject on processed/ only: aggregation.json lives under this prefix.
        # Reference tables (accreditation list, grading scales) will be under
        # reference/ in Phase 3; add GetObject on reference/* at that point.
        storage.bucket.grant_read(self.validate_lambda, "processed/*")

        # ── QueueForReviewLambda ───────────────────────────────────────────────
        # Final pipeline state: updates METADATA to READY_FOR_REVIEW,
        # sets GSI1PK/GSI1SK for the review-queue GSI, and writes an
        # AUDIT record. No SNS publish yet — that is a Phase 3 addition.
        self.queue_for_review_lambda = lambda_.Function(
            self,
            "QueueForReviewLambda",
            function_name="msbn-queue-for-review",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                os.path.normpath(
                    os.path.join(
                        os.path.dirname(__file__), "../../services/notify"
                    )
                )
            ),
            memory_size=512,
            timeout=Duration.seconds(30),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "TABLE_NAME": storage.table.table_name,
            },
        )

        # Least-privilege IAM for QueueForReviewLambda ────────────────────────
        # UpdateItem: mutates the existing METADATA record (status, flag_count,
        #   GSI keys, timestamps). Does not need PutItem for METADATA.
        # PutItem: creates the append-only AUDIT record. Does not need UpdateItem
        #   on AUDIT items (they are never modified after creation).
        # Both actions scoped to the single applications table.
        storage.table.grant(
            self.queue_for_review_lambda,
            "dynamodb:UpdateItem",
            "dynamodb:PutItem",
        )

        # ── CrossDocLambda (stub) ──────────────────────────────────────────────
        # TODO: Runtime: Python 3.11, Code: services/cross_doc/
        #   IAM: DynamoDB Query (all DOCUMENT items for an application),
        #        PutItem (FLAG items).

        # ── PopulationCheckLambda (stub) ───────────────────────────────────────
        # TODO: Runtime: Python 3.11, Code: services/population_check/
        #   IAM: DynamoDB Query on GSI2-LicenseDedup and GSI3-InstitutionCluster,
        #        PutItem (FLAG items).

        # ── DashboardApiLambda ────────────────────────────────────────────────
        # REST backend for the reviewer dashboard.  Routes dispatched by
        # API Gateway HTTP API route key (GET /applications, etc.).
        # Cognito JWT authorizer is configured in ApiConstruct.
        self.dashboard_api_lambda = lambda_.Function(
            self,
            "DashboardApiLambda",
            function_name="msbn-dashboard-api",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="handler.handler",
            code=lambda_.Code.from_asset(
                os.path.normpath(
                    os.path.join(
                        os.path.dirname(__file__), "../../services/dashboard_api"
                    )
                )
            ),
            memory_size=512,
            timeout=Duration.seconds(30),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "TABLE_NAME": storage.table.table_name,
                "BUCKET_NAME": storage.bucket.bucket_name,
            },
        )

        # Least-privilege IAM for DashboardApiLambda ─────────────────────────
        # Query + GetItem: list view (GSI1), detail view (METADATA, FLAGS,
        #   DOCUMENT), audit trail (AUDIT prefix).
        # UpdateItem: reviewer flag decisions, METADATA status transitions.
        # PutItem: append-only AUDIT records.
        storage.table.grant(
            self.dashboard_api_lambda,
            "dynamodb:Query",
            "dynamodb:GetItem",
            "dynamodb:UpdateItem",
            "dynamodb:PutItem",
        )

        # GetObject on processed/*: presigned URLs for page images.
        storage.bucket.grant_read(self.dashboard_api_lambda, "processed/*")

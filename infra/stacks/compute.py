"""Lambda definitions for the transcript pipeline."""

import os

from aws_cdk import (
    Duration,
    aws_ecr_assets as ecr_assets,
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

        # IntakeLambda: S3 upload entry point.
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
            # POC cost control: keep logs for one week.
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "TABLE_NAME": storage.table.table_name,
                "BUCKET_NAME": storage.bucket.bucket_name,
            },
        )

        # Intake creates metadata but does not read or mutate existing records.
        storage.table.grant(self.intake_lambda, "dynamodb:PutItem")

        # Keep future upload inspection scoped to the uploads prefix.
        storage.bucket.grant_read(self.intake_lambda, "uploads/*")

        # S3 notification wiring lives in MsbnComputeStack to avoid stack cycles.

        # ExtractLambda uses a container because poppler/pdf2image are too large
        # for a zip Lambda. Timeout and reserved concurrency cap Bedrock spend.
        self.extract_lambda = lambda_.DockerImageFunction(
            self,
            "ExtractLambda",
            function_name="msbn-extract",
            code=lambda_.DockerImageCode.from_image_asset(
                os.path.normpath(
                    os.path.join(
                        os.path.dirname(__file__), "../../services/extract"
                    )
                ),
                platform=ecr_assets.Platform.LINUX_AMD64,
            ),
            architecture=lambda_.Architecture.X86_64,
            # PDF rendering needs enough memory for multi-page transcripts.
            memory_size=2048,
            timeout=Duration.seconds(180),
            reserved_concurrent_executions=5,
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "BUCKET_NAME": storage.bucket.bucket_name,
                # Nova Pro handles faint watermarks and seal details better.
                "BEDROCK_MODEL_ID": "amazon.nova-pro-v1:0",
                "BEDROCK_MAX_NEW_TOKENS": "5000",
            },
        )

        # Extract reads source PDFs.
        storage.bucket.grant_read(self.extract_lambda, "uploads/*")
        # Extract writes rendered pages and extraction JSON.
        storage.bucket.grant_put(self.extract_lambda, "processed/*")

        # Scope Bedrock access to the Nova models used by the extractor.
        self.extract_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0",
                    "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0",
                ],
            )
        )

        # PrefillLambda: fast, non-authoritative extraction for upload forms.
        # It uses preview/* objects so S3 intake notifications do not start the
        # full Step Functions workflow.
        self.prefill_lambda = lambda_.DockerImageFunction(
            self,
            "PrefillLambda",
            function_name="msbn-prefill",
            code=lambda_.DockerImageCode.from_image_asset(
                os.path.normpath(
                    os.path.join(
                        os.path.dirname(__file__), "../../services/prefill"
                    )
                ),
                platform=ecr_assets.Platform.LINUX_AMD64,
            ),
            architecture=lambda_.Architecture.X86_64,
            memory_size=1536,
            timeout=Duration.seconds(25),
            log_retention=logs.RetentionDays.ONE_WEEK,
            environment={
                "BUCKET_NAME": storage.bucket.bucket_name,
                "BEDROCK_MODEL_ID": "amazon.nova-lite-v1:0",
            },
        )

        storage.bucket.grant_put(self.prefill_lambda, "preview/*")
        storage.bucket.grant_read(self.prefill_lambda, "preview/*")
        self.prefill_lambda.add_to_role_policy(
            iam.PolicyStatement(
                actions=["bedrock:InvokeModel"],
                resources=[
                    "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0",
                ],
            )
        )

        # Extract only writes the transcript document record.
        storage.table.grant(self.extract_lambda, "dynamodb:PutItem")

        # AggregationLambda: page-level extraction to aggregation.json.
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

        # Aggregation reads and writes under processed/.
        storage.bucket.grant_read(self.aggregate_lambda, "processed/*")
        storage.bucket.grant_put(self.aggregate_lambda, "processed/*")

        # ValidateLambda: deterministic rule engine, no Bedrock calls.
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

        # The rule engine writes FLAG records only.
        storage.table.grant(self.validate_lambda, "dynamodb:PutItem")

        # Add reference/* read access when external lookup tables land.
        storage.bucket.grant_read(self.validate_lambda, "processed/*")

        # QueueForReviewLambda: final pipeline state before human review.
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

        # QueueForReview updates METADATA and appends AUDIT records.
        storage.table.grant(
            self.queue_for_review_lambda,
            "dynamodb:UpdateItem",
            "dynamodb:PutItem",
        )
        storage.bucket.grant_read(self.queue_for_review_lambda, "processed/*")

        # CrossDocLambda is deferred until multi-document uploads are in scope.

        # PopulationCheckLambda is deferred until population checks land.

        # DashboardApiLambda: reviewer-facing HTTP API handlers.
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

        # Dashboard API reads cases and writes reviewer decisions/audit events.
        storage.table.grant(
            self.dashboard_api_lambda,
            "dynamodb:Query",
            "dynamodb:GetItem",
            "dynamodb:UpdateItem",
            "dynamodb:PutItem",
        )

        # Uploads enter through pre-signed PUT URLs and are previewed through
        # short-lived pre-signed GET URLs in the reviewer UI.
        storage.bucket.grant_put(self.dashboard_api_lambda, "uploads/*")
        storage.bucket.grant_read(self.dashboard_api_lambda, "uploads/*")
        storage.bucket.grant_read(self.dashboard_api_lambda, "processed/*")

"""Compute construct: Lambda functions for the MSBN processing pipeline.

Only IntakeLambda is implemented in this slice.  All other Lambdas remain as
stubs with TODO comments; their IAM and packaging notes are preserved so the
next developer can fill them in without re-reading the architecture doc.

Seven Lambda functions (architecture-plan.md Section 1):
  IntakeLambda          — implemented here
  ExtractLambda         — stub (needs container image + poppler)
  RuleEngineLambda      — stub
  CrossDocLambda        — stub
  PopulationCheckLambda — stub
  NotifyLambda          — stub
  DashboardApiLambda    — stub
"""

import os

from aws_cdk import (
    Duration,
    aws_lambda as lambda_,
    aws_logs as logs,
    aws_s3 as s3,
    aws_s3_notifications as s3n,
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
                "BUCKET_NAME": storage.bucket.bucket_name,
            },
        )

        # Least-privilege IAM ──────────────────────────────────────────────────
        # PutItem only: Intake never reads or modifies existing records.
        storage.table.grant(self.intake_lambda, "dynamodb:PutItem")

        # GetObject on uploads/ only: grants the Lambda access to inspect the
        # uploaded file in future slices without widening to the whole bucket.
        storage.bucket.grant_read(self.intake_lambda, "uploads/*")

        # S3 event notification ────────────────────────────────────────────────
        # CDK automatically adds the Lambda resource-based policy so S3 can
        # invoke the function, and creates the BucketNotification custom
        # resource in CloudFormation.
        storage.bucket.add_event_notification(
            s3.EventType.OBJECT_CREATED,
            s3n.LambdaDestination(self.intake_lambda),
            s3.NotificationKeyFilter(prefix="uploads/"),
        )

        # ── ExtractLambda (stub) ───────────────────────────────────────────────
        # TODO: Deploy as a container image (poppler + pdf2image dependency,
        #   ~80 MB unzipped, exceeds Lambda zip limit).
        #   Runtime: Python 3.11 container image (ECR — confirm with Hub team).
        #   Code: services/extract/
        #   memory_size: 1024 MB  timeout: Duration.minutes(5)
        #   IAM: Bedrock InvokeModel (Nova Lite + Pro ARNs), S3 GetObject on
        #        raw/, S3 PutObject on processed/, DynamoDB UpdateItem.

        # ── RuleEngineLambda (stub) ────────────────────────────────────────────
        # TODO: Runtime: Python 3.11, Code: services/rule_engine/
        #   IAM: S3 GetObject on processed/ and reference/,
        #        DynamoDB PutItem (FLAG items), UpdateItem (flag_count).

        # ── CrossDocLambda (stub) ──────────────────────────────────────────────
        # TODO: Runtime: Python 3.11, Code: services/cross_doc/
        #   IAM: DynamoDB Query (all DOCUMENT items for an application),
        #        PutItem (FLAG items).

        # ── PopulationCheckLambda (stub) ───────────────────────────────────────
        # TODO: Runtime: Python 3.11, Code: services/population_check/
        #   IAM: DynamoDB Query on GSI2-LicenseDedup and GSI3-InstitutionCluster,
        #        PutItem (FLAG items).

        # ── NotifyLambda (stub) ────────────────────────────────────────────────
        # TODO: Runtime: Python 3.11, Code: services/notify/
        #   IAM: SNS Publish on the reviewer-notification topic.

        # ── DashboardApiLambda (stub) ──────────────────────────────────────────
        # TODO: Runtime: Python 3.11, Code: services/dashboard_api/
        #   IAM: DynamoDB Query/GetItem (read-only), S3 GetObject (presigned URLs),
        #        DynamoDB UpdateItem (reviewer decisions and flag status).
        #   Integrated with API Gateway HTTP API + Cognito JWT authorizer.

"""MsbnComputeStack: all Lambdas + Step Functions + IAM.

Depends on MsbnStorageStack (imports bucket and table via cross-stack refs).
"""

import aws_cdk as cdk
from aws_cdk import (
    aws_dynamodb as dynamodb,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_s3 as s3,
    custom_resources as cr,
)
from constructs import Construct

from stacks.compute import ComputeConstruct
from stacks.workflow import WorkflowConstruct


class MsbnComputeStack(cdk.Stack):
    """Lambda functions and Step Functions state machine for the pipeline."""

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        *,
        bucket: s3.IBucket,
        table: dynamodb.ITable,
        **kwargs,
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ComputeConstruct expects a StorageConstruct-shaped object with
        # .bucket and .table attributes.  Create a lightweight namespace.
        storage_ref = _StorageRef(bucket=bucket, table=table)

        compute = ComputeConstruct(self, "Compute", storage=storage_ref)

        workflow = WorkflowConstruct(
            self,
            "Workflow",
            extract_lambda=compute.extract_lambda,
            aggregate_lambda=compute.aggregate_lambda,
            validate_lambda=compute.validate_lambda,
            queue_for_review_lambda=compute.queue_for_review_lambda,
            table=table,
        )

        # Break the Compute <-> Workflow dependency cycle.
        compute.intake_lambda.add_environment(
            "STATE_MACHINE_ARN", workflow.state_machine.state_machine_arn
        )
        workflow.state_machine.grant_start_execution(compute.intake_lambda)

        # ── S3 event notification ─────────────────────────────────────────────
        # Wired here (not in ComputeConstruct) to avoid a cyclic cross-stack
        # dependency: add_event_notification creates a custom resource scoped
        # to the bucket's stack, which would reference this stack's Lambda ARN,
        # creating a cycle.  Using L1/custom-resource constructs keeps all
        # notification resources in this stack.

        # 1. Allow S3 to invoke IntakeLambda.
        lambda_.CfnPermission(
            self,
            "S3InvokeIntakePermission",
            action="lambda:InvokeFunction",
            function_name=compute.intake_lambda.function_name,
            principal="s3.amazonaws.com",
            source_arn=bucket.bucket_arn,
            source_account=self.account,
        )

        # 2. Configure S3 bucket notification via AWS SDK call.
        cr.AwsCustomResource(
            self,
            "S3BucketNotification",
            on_create=cr.AwsSdkCall(
                service="S3",
                action="putBucketNotificationConfiguration",
                parameters={
                    "Bucket": bucket.bucket_name,
                    "NotificationConfiguration": {
                        "LambdaFunctionConfigurations": [
                            {
                                "Events": ["s3:ObjectCreated:*"],
                                "LambdaFunctionArn": compute.intake_lambda.function_arn,
                                "Filter": {
                                    "Key": {
                                        "FilterRules": [
                                            {
                                                "Name": "prefix",
                                                "Value": "uploads/",
                                            }
                                        ]
                                    }
                                },
                            }
                        ]
                    },
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    "msbn-s3-notification-config"
                ),
            ),
            on_update=cr.AwsSdkCall(
                service="S3",
                action="putBucketNotificationConfiguration",
                parameters={
                    "Bucket": bucket.bucket_name,
                    "NotificationConfiguration": {
                        "LambdaFunctionConfigurations": [
                            {
                                "Events": ["s3:ObjectCreated:*"],
                                "LambdaFunctionArn": compute.intake_lambda.function_arn,
                                "Filter": {
                                    "Key": {
                                        "FilterRules": [
                                            {
                                                "Name": "prefix",
                                                "Value": "uploads/",
                                            }
                                        ]
                                    }
                                },
                            }
                        ]
                    },
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    "msbn-s3-notification-config"
                ),
            ),
            on_delete=cr.AwsSdkCall(
                service="S3",
                action="putBucketNotificationConfiguration",
                parameters={
                    "Bucket": bucket.bucket_name,
                    "NotificationConfiguration": {},
                },
                physical_resource_id=cr.PhysicalResourceId.of(
                    "msbn-s3-notification-config"
                ),
            ),
            policy=cr.AwsCustomResourcePolicy.from_statements(
                [
                    iam.PolicyStatement(
                        actions=["s3:PutBucketNotification*"],
                        resources=[bucket.bucket_arn],
                    ),
                ]
            ),
        )

        # Expose for the API stack.
        self.dashboard_api_lambda = compute.dashboard_api_lambda


class _StorageRef:
    """Lightweight adapter so ComputeConstruct can accept cross-stack refs."""

    def __init__(self, *, bucket: s3.IBucket, table: dynamodb.ITable) -> None:
        self.bucket = bucket
        self.table = table

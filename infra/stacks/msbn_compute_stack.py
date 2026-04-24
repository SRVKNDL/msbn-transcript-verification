"""Compute stack: Lambdas, workflow, and S3 trigger wiring."""

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

        # ComputeConstruct only needs bucket/table attributes.
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

        # Wire the state machine ARN after both constructs exist.
        compute.intake_lambda.add_environment(
            "STATE_MACHINE_ARN", workflow.state_machine.state_machine_arn
        )
        workflow.state_machine.grant_start_execution(compute.intake_lambda)

        # Keep the S3 notification resources in this stack to avoid a
        # StorageStack -> ComputeStack -> StorageStack cycle.

        # S3 must be allowed to invoke IntakeLambda before notifications attach.
        intake_invoke_permission = lambda_.CfnPermission(
            self,
            "S3InvokeIntakePermission",
            action="lambda:InvokeFunction",
            function_name=compute.intake_lambda.function_name,
            principal="s3.amazonaws.com",
            source_arn=bucket.bucket_arn,
            source_account=self.account,
        )

        # Configure the bucket notification with a custom resource.
        s3_bucket_notification = cr.AwsCustomResource(
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
        # S3 validates the Lambda permission when the notification is configured.
        s3_bucket_notification.node.add_dependency(intake_invoke_permission)
        # The API stack needs this Lambda for route integration.
        self.dashboard_api_lambda = compute.dashboard_api_lambda


class _StorageRef:
    """Adapter for passing imported storage resources into ComputeConstruct."""

    def __init__(self, *, bucket: s3.IBucket, table: dynamodb.ITable) -> None:
        self.bucket = bucket
        self.table = table

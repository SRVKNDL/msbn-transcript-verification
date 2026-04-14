"""Main CDK stack that composes all constructs for the MSBN Transcript Verification system."""

import aws_cdk as cdk
from constructs import Construct

from stacks.api import ApiConstruct
from stacks.compute import ComputeConstruct
from stacks.storage import StorageConstruct
from stacks.workflow import WorkflowConstruct


class MsbnTranscriptStack(cdk.Stack):
    """Top-level stack for the MSBN Transcript Verification POC.

    Composes four constructs:
    - StorageConstruct:  S3 transcripts bucket and DynamoDB single-table
    - ComputeConstruct:  Lambda functions (IntakeLambda + 3 pipeline stubs)
    - ApiConstruct:      API Gateway HTTP API and Cognito user pool (stub)
    - WorkflowConstruct: Step Functions state machine (skeleton wired this slice)

    Construct order matters for the circular-dependency break:
      1. Storage  — no dependencies
      2. Compute  — depends on Storage for env vars and IAM grants
      3. Workflow — depends on Compute (Lambda ARNs) and Storage (DynamoDB table)
      4. Post-wiring: add STATE_MACHINE_ARN env var and IAM grant to IntakeLambda
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        storage = StorageConstruct(self, "Storage")

        compute = ComputeConstruct(self, "Compute", storage=storage)

        workflow = WorkflowConstruct(
            self,
            "Workflow",
            extract_lambda=compute.extract_lambda,
            aggregate_lambda=compute.aggregate_lambda,
            validate_lambda=compute.validate_lambda,
            queue_for_review_lambda=compute.queue_for_review_lambda,
            table=storage.table,
        )

        # Break the Compute ↔ Workflow dependency cycle by adding the state
        # machine ARN to the Intake Lambda environment after both constructs
        # are created.
        compute.intake_lambda.add_environment(
            "STATE_MACHINE_ARN", workflow.state_machine.state_machine_arn
        )

        # Least-privilege: IntakeLambda may only start THIS specific state machine.
        # grant_start_execution generates:
        #   states:StartExecution on arn:aws:states:...:stateMachine:msbn-transcript-pipeline
        workflow.state_machine.grant_start_execution(compute.intake_lambda)

        # Api remains as a stub; instantiate so it appears in the CloudFormation
        # template and can be incrementally filled in.
        ApiConstruct(self, "Api")

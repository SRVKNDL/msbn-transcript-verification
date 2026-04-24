"""Single-stack CDK app used by earlier deployment slices."""

import aws_cdk as cdk
from constructs import Construct

from stacks.api import ApiConstruct
from stacks.compute import ComputeConstruct
from stacks.storage import StorageConstruct
from stacks.workflow import WorkflowConstruct


class MsbnTranscriptStack(cdk.Stack):
    """Top-level stack for local synth and backwards compatibility."""

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

        # Add the workflow ARN after Compute and Workflow are both built.
        compute.intake_lambda.add_environment(
            "STATE_MACHINE_ARN", workflow.state_machine.state_machine_arn
        )

        # Intake may only start this state machine.
        workflow.state_machine.grant_start_execution(compute.intake_lambda)

        # Reviewer dashboard API.
        ApiConstruct(
            self,
            "Api",
            dashboard_api_lambda=compute.dashboard_api_lambda,
        )

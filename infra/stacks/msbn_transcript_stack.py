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
    - ComputeConstruct:  Lambda functions (IntakeLambda implemented; others stubbed)
    - ApiConstruct:      API Gateway HTTP API and Cognito user pool (stub)
    - WorkflowConstruct: Step Functions state machine (stub)
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        storage = StorageConstruct(self, "Storage")
        ComputeConstruct(self, "Compute", storage=storage)

        # Api and Workflow remain as stubs; instantiate so they appear in the
        # CloudFormation template and can be incrementally filled in.
        ApiConstruct(self, "Api")
        WorkflowConstruct(self, "Workflow")

"""Main CDK stack that composes all constructs for the MSBN Transcript Verification system."""

import aws_cdk as cdk
from constructs import Construct



class MsbnTranscriptStack(cdk.Stack):
    """Top-level stack for the MSBN Transcript Verification POC.

    Composes four constructs:
    - StorageConstruct: S3 bucket and DynamoDB table
    - ComputeConstruct: Lambda functions for the processing pipeline
    - ApiConstruct: API Gateway HTTP API and Cognito user pool
    - WorkflowConstruct: Step Functions state machine
    """

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # TODO: Instantiate constructs and wire them together.
        #       Each construct is defined in its own file under stacks/.
        #       See design/architecture-plan.md for the full service map.

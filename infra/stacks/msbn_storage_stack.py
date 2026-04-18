"""MsbnStorageStack: S3 bucket + DynamoDB table + lifecycle rules.

Deployed first. No dependencies on other stacks.
"""

import aws_cdk as cdk
from constructs import Construct

from stacks.storage import StorageConstruct


class MsbnStorageStack(cdk.Stack):
    """S3 transcripts bucket and DynamoDB single-table."""

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        storage = StorageConstruct(self, "Storage")

        # Expose for cross-stack references.
        self.bucket = storage.bucket
        self.table = storage.table

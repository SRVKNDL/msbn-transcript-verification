#!/usr/bin/env python3
"""CDK app entry point for the MSBN Transcript Verification system.

Four stacks, deployed in order:
  1. MsbnStorageStack  — S3 bucket + DynamoDB table
  2. MsbnAuthStack     — Cognito User Pool + Client
  3. MsbnComputeStack  — Lambdas + Step Functions (depends on Storage)
  4. MsbnApiStack      — API Gateway (depends on Compute + Auth)
"""

import aws_cdk as cdk

from stacks.msbn_storage_stack import MsbnStorageStack
from stacks.msbn_auth_stack import MsbnAuthStack
from stacks.msbn_compute_stack import MsbnComputeStack
from stacks.msbn_api_stack import MsbnApiStack

app = cdk.App()

env = cdk.Environment(region="us-east-1")

# 1. Storage — no dependencies
storage_stack = MsbnStorageStack(app, "MsbnStorageStack", env=env)

# 2. Auth — no dependencies
auth_stack = MsbnAuthStack(app, "MsbnAuthStack", env=env)

# 3. Compute — depends on Storage
compute_stack = MsbnComputeStack(
    app,
    "MsbnComputeStack",
    env=env,
    bucket=storage_stack.bucket,
    table=storage_stack.table,
)

# 4. Api — depends on Compute + Auth
api_stack = MsbnApiStack(
    app,
    "MsbnApiStack",
    env=env,
    dashboard_api_lambda=compute_stack.dashboard_api_lambda,
    prefill_lambda=compute_stack.prefill_lambda,
    user_pool=auth_stack.user_pool,
    user_pool_client=auth_stack.user_pool_client,
)

app.synth()

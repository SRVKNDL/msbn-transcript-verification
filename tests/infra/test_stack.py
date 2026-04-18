"""CDK assertion tests for MsbnTranscriptStack.

Validates cost-safety, security, and operational guardrails added
during the pre-deploy audit.
"""

import json
import os
import sys

import pytest

# The infra package lives outside the normal test PYTHONPATH.
# Insert it so `from stacks.…` imports resolve.
_infra_dir = os.path.join(os.path.dirname(__file__), "..", "..", "infra")
if _infra_dir not in sys.path:
    sys.path.insert(0, os.path.abspath(_infra_dir))

os.environ.setdefault("JSII_SILENCE_WARNING_UNTESTED_NODE_VERSION", "1")

import aws_cdk as cdk
from aws_cdk.assertions import Capture, Match, Template

from stacks.msbn_transcript_stack import MsbnTranscriptStack


@pytest.fixture(scope="module")
def template():
    """Synthesize the stack once and return the assertion Template."""
    app = cdk.App()
    stack = MsbnTranscriptStack(
        app, "TestStack", env=cdk.Environment(region="us-east-1")
    )
    return Template.from_stack(stack)


# ── 1. Extract Lambda: timeout and reserved concurrency ───────────────────────


class TestExtractLambdaHardening:
    def test_timeout_is_180(self, template):
        template.has_resource_properties(
            "AWS::Lambda::Function",
            Match.object_like({
                "FunctionName": "msbn-extract",
                "Timeout": 180,
            }),
        )

    def test_reserved_concurrency_is_5(self, template):
        template.has_resource_properties(
            "AWS::Lambda::Function",
            Match.object_like({
                "FunctionName": "msbn-extract",
                "ReservedConcurrentExecutions": 5,
            }),
        )


# ── 2. Aggregate Lambda: timeout ─────────────────────────────────────────────


class TestAggregateLambdaTimeout:
    def test_timeout_is_60(self, template):
        template.has_resource_properties(
            "AWS::Lambda::Function",
            Match.object_like({
                "FunctionName": "msbn-aggregate",
                "Timeout": 60,
            }),
        )


# ── 3. S3 lifecycle rules ────────────────────────────────────────────────────


class TestS3LifecycleRules:
    def test_bucket_has_lifecycle_configuration(self, template):
        template.has_resource_properties(
            "AWS::S3::Bucket",
            Match.object_like({
                "LifecycleConfiguration": {
                    "Rules": Match.array_with([
                        Match.object_like({
                            "NoncurrentVersionExpiration": {
                                "NoncurrentDays": 30,
                            },
                            "AbortIncompleteMultipartUpload": {
                                "DaysAfterInitiation": 7,
                            },
                            "Status": "Enabled",
                        }),
                    ]),
                },
            }),
        )


# ── 4. Bedrock IAM: explicit model ARNs ──────────────────────────────────────


class TestBedrockIamScope:
    def test_bedrock_policy_has_exact_model_arns(self, template):
        # Find the ExtractLambda's role default policy.
        policies = template.find_resources("AWS::IAM::Policy")
        bedrock_statements = []
        for _logical_id, resource in policies.items():
            statements = (
                resource.get("Properties", {})
                .get("PolicyDocument", {})
                .get("Statement", [])
            )
            for stmt in statements:
                actions = stmt.get("Action", [])
                if isinstance(actions, str):
                    actions = [actions]
                if "bedrock:InvokeModel" in actions:
                    bedrock_statements.append(stmt)

        assert len(bedrock_statements) == 1, (
            f"Expected exactly 1 bedrock:InvokeModel statement, found {len(bedrock_statements)}"
        )

        resources = bedrock_statements[0]["Resource"]
        if isinstance(resources, str):
            resources = [resources]

        expected = {
            "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-lite-v1:0",
            "arn:aws:bedrock:us-east-1::foundation-model/amazon.nova-pro-v1:0",
        }
        assert set(resources) == expected, (
            f"Bedrock IAM resources should be exactly {expected}, got {set(resources)}"
        )


# ── 5. Cognito password policy ───────────────────────────────────────────────


class TestCognitoPasswordPolicy:
    def test_password_policy(self, template):
        template.has_resource_properties(
            "AWS::Cognito::UserPool",
            Match.object_like({
                "Policies": {
                    "PasswordPolicy": {
                        "MinimumLength": 12,
                        "RequireNumbers": True,
                        "RequireUppercase": True,
                        "RequireLowercase": True,
                        "RequireSymbols": True,
                    },
                },
            }),
        )


# ── 6. API Gateway throttling ────────────────────────────────────────────────


class TestApiGatewayThrottling:
    def test_default_stage_has_throttling(self, template):
        template.has_resource_properties(
            "AWS::ApiGatewayV2::Stage",
            Match.object_like({
                "DefaultRouteSettings": {
                    "ThrottlingBurstLimit": 50,
                    "ThrottlingRateLimit": 25,
                },
            }),
        )

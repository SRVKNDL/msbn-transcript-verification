"""CDK assertion tests for the MSBN multi-stack deployment.

Validates cost-safety, security, and operational guardrails across
all four stacks: Storage, Auth, Compute, Api.
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

from stacks.msbn_storage_stack import MsbnStorageStack
from stacks.msbn_auth_stack import MsbnAuthStack
from stacks.msbn_compute_stack import MsbnComputeStack
from stacks.msbn_api_stack import MsbnApiStack


@pytest.fixture(scope="module")
def stacks():
    """Synthesize all four stacks and return their Templates."""
    app = cdk.App()
    env = cdk.Environment(region="us-east-1")

    storage = MsbnStorageStack(app, "TestStorageStack", env=env)
    auth = MsbnAuthStack(app, "TestAuthStack", env=env)
    compute = MsbnComputeStack(
        app,
        "TestComputeStack",
        env=env,
        bucket=storage.bucket,
        table=storage.table,
    )
    api = MsbnApiStack(
        app,
        "TestApiStack",
        env=env,
        dashboard_api_lambda=compute.dashboard_api_lambda,
        user_pool=auth.user_pool,
        user_pool_client=auth.user_pool_client,
    )

    return {
        "storage": Template.from_stack(storage),
        "auth": Template.from_stack(auth),
        "compute": Template.from_stack(compute),
        "api": Template.from_stack(api),
    }


@pytest.fixture(scope="module")
def storage_template(stacks):
    return stacks["storage"]


@pytest.fixture(scope="module")
def auth_template(stacks):
    return stacks["auth"]


@pytest.fixture(scope="module")
def compute_template(stacks):
    return stacks["compute"]


@pytest.fixture(scope="module")
def api_template(stacks):
    return stacks["api"]


# ── 1. Extract Lambda: timeout and reserved concurrency ───────────────────────


class TestExtractLambdaHardening:
    def test_timeout_is_180(self, compute_template):
        compute_template.has_resource_properties(
            "AWS::Lambda::Function",
            Match.object_like({
                "FunctionName": "msbn-extract",
                "Timeout": 180,
            }),
        )

    def test_reserved_concurrency_is_5(self, compute_template):
        compute_template.has_resource_properties(
            "AWS::Lambda::Function",
            Match.object_like({
                "FunctionName": "msbn-extract",
                "ReservedConcurrentExecutions": 5,
            }),
        )

    def test_default_model_is_nova_pro(self, compute_template):
        compute_template.has_resource_properties(
            "AWS::Lambda::Function",
            Match.object_like({
                "FunctionName": "msbn-extract",
                "Environment": {
                    "Variables": Match.object_like({
                        "BEDROCK_MODEL_ID": "amazon.nova-pro-v1:0",
                    })
                },
            }),
        )


# ── 2. Aggregate Lambda: timeout ─────────────────────────────────────────────


class TestAggregateLambdaTimeout:
    def test_timeout_is_60(self, compute_template):
        compute_template.has_resource_properties(
            "AWS::Lambda::Function",
            Match.object_like({
                "FunctionName": "msbn-aggregate",
                "Timeout": 60,
            }),
        )


class TestWorkflowPayloads:
    def test_extract_task_forwards_full_state_not_literal_dollar(self, compute_template):
        resources = compute_template.find_resources("AWS::StepFunctions::StateMachine")
        assert len(resources) == 1, f"Expected 1 state machine, found {len(resources)}"

        definition = next(iter(resources.values()))["Properties"]["DefinitionString"]
        definition_json = json.dumps(definition)

        assert '"Payload":"$"' not in definition_json
        assert '"Payload.$":"$"' not in definition_json


# ── 3. S3 lifecycle rules ────────────────────────────────────────────────────


class TestS3LifecycleRules:
    def test_bucket_has_lifecycle_configuration(self, storage_template):
        storage_template.has_resource_properties(
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
    def test_bedrock_policy_has_exact_model_arns(self, compute_template):
        # Find the ExtractLambda's role default policy.
        policies = compute_template.find_resources("AWS::IAM::Policy")
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


# ── 5. Cognito password policy and auth hardening ───────────────────────────


class TestCognitoPasswordPolicy:
    def test_password_policy(self, auth_template):
        auth_template.has_resource_properties(
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

    def test_custom_role_attribute_in_schema(self, auth_template):
        auth_template.has_resource_properties(
            "AWS::Cognito::UserPool",
            Match.object_like({
                "Schema": Match.array_with([
                    Match.object_like({
                        "Name": "role",
                        "AttributeDataType": "String",
                        "Mutable": True,
                    }),
                ]),
            }),
        )

    def test_mfa_is_off(self, auth_template):
        auth_template.has_resource_properties(
            "AWS::Cognito::UserPool",
            Match.object_like({
                "MfaConfiguration": "OFF",
            }),
        )

    def test_no_sms_iam_role(self, auth_template):
        """MFA OFF means no SMS role should exist in the auth stack."""
        roles = auth_template.find_resources("AWS::IAM::Role")
        assert len(roles) == 0, (
            f"Expected no IAM roles in auth stack (SMS role should be gone), "
            f"found {len(roles)}: {list(roles.keys())}"
        )

    def test_client_auth_flows_srp_admin_and_refresh_only(self, auth_template):
        auth_template.has_resource_properties(
            "AWS::Cognito::UserPoolClient",
            Match.object_like({
                "ExplicitAuthFlows": Match.array_equals([
                    "ALLOW_ADMIN_USER_PASSWORD_AUTH",
                    "ALLOW_USER_SRP_AUTH",
                    "ALLOW_REFRESH_TOKEN_AUTH",
                ]),
            }),
        )

    def test_no_user_password_auth(self, auth_template):
        """ALLOW_USER_PASSWORD_AUTH must not be present on the client."""
        clients = auth_template.find_resources("AWS::Cognito::UserPoolClient")
        for _id, resource in clients.items():
            flows = resource.get("Properties", {}).get("ExplicitAuthFlows", [])
            assert "ALLOW_USER_PASSWORD_AUTH" not in flows, (
                "Client should not allow USER_PASSWORD_AUTH — use admin-initiate-auth for testing"
            )

    def test_hosted_ui_oauth_code_flow(self, auth_template):
        """SPA uses Cognito Hosted UI with authorization-code OAuth flow."""
        auth_template.has_resource_properties(
            "AWS::Cognito::UserPoolClient",
            Match.object_like({
                "AllowedOAuthFlowsUserPoolClient": True,
                "AllowedOAuthFlows": ["code"],
                "AllowedOAuthScopes": ["openid", "email", "profile"],
                "CallbackURLs": ["http://localhost:3000/"],
                "LogoutURLs": ["http://localhost:3000/"],
                "SupportedIdentityProviders": ["COGNITO"],
            }),
        )

    def test_hosted_ui_domain_exists(self, auth_template):
        """Hosted UI requires a user-pool domain for login redirects."""
        auth_template.resource_count_is("AWS::Cognito::UserPoolDomain", 1)


# ── 6. API Gateway throttling ────────────────────────────────────────────────


class TestApiGatewayThrottling:
    def test_default_stage_has_throttling(self, api_template):
        api_template.has_resource_properties(
            "AWS::ApiGatewayV2::Stage",
            Match.object_like({
                "DefaultRouteSettings": {
                    "ThrottlingBurstLimit": 50,
                    "ThrottlingRateLimit": 25,
                },
            }),
        )

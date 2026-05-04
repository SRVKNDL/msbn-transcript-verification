# Infrastructure

Python AWS CDK app for the MSBN transcript verification system.

## What It Provisions

- S3 bucket for raw uploads and processed artifacts
- DynamoDB table for application metadata, flags, and audit events
- Lambda functions for intake, extraction, aggregation, validation, queueing,
  and dashboard API handling
- Step Functions state machine for transcript processing
- Cognito user pool and app client for reviewer authentication
- API Gateway HTTP API for the dashboard backend

## Stack Layout

The app is split into four stacks:

- `MsbnStorageStack`
- `MsbnAuthStack`
- `MsbnComputeStack`
- `MsbnApiStack`

Deployment order and verification steps are documented in the root
[DEPLOY_RUNBOOK.md](../DEPLOY_RUNBOOK.md).

## Local Commands

Synthesize from the `infra/` directory:

```bash
cd infra
cdk synth
```

Or from the repository root:

```bash
make synth
```

Bootstrap for a first deploy in a new account/region:

```bash
cd infra
cdk bootstrap
```

## Directory Layout

```text
app.py                CDK app entry point
cdk.json              CDK configuration
requirements.txt      CDK dependencies
stacks/
  storage.py          S3 + DynamoDB
  auth.py             Cognito resources
  compute.py          Lambda functions and permissions
  workflow.py         Step Functions workflow
  api.py              API Gateway HTTP API
```

## Notes

- Target region is currently `us-east-1`.
- Do not run deploy commands without using the deploy runbook.
- `cdk.out/` is generated output and is ignored by Git.

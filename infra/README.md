# MSBN Transcript Verification — Infrastructure

AWS CDK (Python) project for the MSBN transcript verification pipeline.

## Prerequisites

- Python 3.11+
- Node.js 20+ (CDK CLI runs on Node)
- AWS CDK CLI: `npm install -g aws-cdk`
- AWS credentials configured for us-east-1

## Setup

```bash
cd infra/
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Bootstrap (one-time per account/region)

```bash
cdk bootstrap aws://ACCOUNT_ID/us-east-1
```

## Synthesize (validate templates without deploying)

```bash
cdk synth
```

This generates CloudFormation templates in `cdk.out/`. Review them before
any deployment.

## Project structure

```
infra/
  app.py                  CDK app entry point
  cdk.json                CDK configuration
  requirements.txt        Python dependencies
  stacks/
    msbn_transcript_stack.py   Main stack (composes all constructs)
    storage.py                 S3 bucket + DynamoDB table
    compute.py                 Lambda functions
    api.py                     API Gateway + Cognito
    workflow.py                Step Functions state machine
```

## Deployment

Do **not** deploy without team review and cost confirmation.
See the root CLAUDE.md for budget constraints ($1,000 total).

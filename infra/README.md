# infra

CDK app (Python) for the transcript verification pipeline.
Synthesizes to a single CloudFormation stack: `MsbnTranscriptStack`.

## Prerequisites

- Python 3.11
- Node 20 (CDK CLI runs on Node)
- AWS CDK CLI: `npm install -g aws-cdk`
- AWS credentials configured

## Synth

Generate the CloudFormation template without deploying:

    cd infra
    cdk synth

Or from the project root:

    make synth

Output goes to `cdk.out/`. Safe to run locally; no AWS calls are made.

## Deploy

First-time setup requires a bootstrap step:

    cdk bootstrap

Then deploy:

    cdk deploy

Do not deploy without checking the cost constraints in the root CLAUDE.md.

## Layout

    app.py                       CDK app entry point
    cdk.json                     CDK configuration
    requirements.txt             Python deps (aws-cdk-lib, constructs)
    stacks/
      msbn_transcript_stack.py   Top-level stack; composes all constructs
      storage.py                 S3 bucket + DynamoDB table
      compute.py                 Lambda functions
      api.py                     API Gateway + Cognito (stub)
      workflow.py                Step Functions state machine (stub)

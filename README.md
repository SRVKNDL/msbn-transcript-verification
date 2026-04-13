# Transcript Verification

AI-assisted transcript verification for nurse licensure review.
Extracts data from uploaded transcripts, validates against
accreditation and coursework requirements, and surfaces anomalies
for human review.

Advisory only. All licensing decisions are made by a human reviewer.

## Stack

- Python 3.11, AWS CDK
- AWS Lambda, Bedrock, S3, DynamoDB, API Gateway, Step Functions, Cognito
- React, TypeScript, Vite
- pytest, ruff

## Setup

Requires Python 3.11, Node 20, and the AWS CDK CLI (`npm install -g aws-cdk`).

    make install
    make test
    make synth

## Layout

    infra/       CDK stack and constructs
    services/    Lambda handlers
    frontend/    Reviewer dashboard
    tests/       pytest suites

## Development

    make test     run all tests
    make synth    generate CloudFormation template
    make lint     run ruff
    make clean    remove build artifacts

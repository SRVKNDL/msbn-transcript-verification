# MSBN Transcript Verification

AI-assisted transcript review for the Mississippi State Board of Nursing proof
of concept. The system ingests transcript PDFs, extracts structured facts with
Amazon Bedrock Nova, evaluates deterministic fraud and eligibility rules, and
queues the application for a human reviewer.

This project is advisory only. The software raises review flags; it does not
make licensing decisions.

## Current Scope

- Transcript-only processing for the POC.
- Bedrock extracts facts from page images.
- Python rules evaluate those facts against documented requirements.
- DynamoDB stores application state, flags, decisions, and audit history.
- React dashboard supports reviewer queue, case review, upload flow, and audit views.

Multi-document checks for diplomas, CEA reports, affidavits, and cross-document
identity matching are documented for a later phase.

## Architecture

The deployed path is serverless-first, following the Mississippi AI Innovation
Hub guidance:

1. Staff upload a transcript PDF to S3 under `uploads/`.
2. S3 invokes `IntakeLambda`, which creates the application metadata record and
   starts the Step Functions workflow.
3. `ExtractLambda` renders PDF pages to PNG, calls Bedrock Nova per page, and
   writes extraction JSON to S3.
4. `AggregationLambda` flattens per-page extraction into `aggregation.json`.
5. `RuleEngineLambda` runs deterministic PHYS, CONT, and PROG rules and writes
   `FLAG` items to DynamoDB.
6. `QueueForReviewLambda` marks the application `READY_FOR_REVIEW` and appends
   an audit event.
7. `DashboardApiLambda` exposes queue, detail, decision, and audit endpoints to
   the reviewer dashboard through API Gateway and Cognito.

See [design/architecture-plan.md](design/architecture-plan.md) for the full
pipeline design and [design/data-model.md](design/data-model.md) for the
DynamoDB table layout.

## Tech Stack

- Python 3.11
- AWS CDK, Lambda, Step Functions, S3, DynamoDB, API Gateway, Cognito
- Amazon Bedrock Nova Lite / Nova Pro
- React, TypeScript, Vite
- pytest, moto, ruff, TypeScript compiler

## Repository Layout

```text
design/      Requirements, architecture, extraction vocabulary, data model
docs/        Source material and AI Innovation Hub guidance
infra/       CDK app and AWS constructs
services/    Lambda handlers and service-specific README files
frontend/    Reviewer dashboard
tests/       Unit and integration tests
```

## Local Setup

Prerequisites:

- Python 3.11+
- Node 20+
- AWS CDK CLI: `npm install -g aws-cdk`

Install project dependencies:

```bash
make install
```

Run the backend test suite:

```bash
make test
```

Build the frontend:

```bash
cd frontend
npm run build
```

Synthesize the CDK stacks without deploying:

```bash
make synth
```

## Development Commands

```bash
make test      # run pytest
make synth     # synthesize CloudFormation
make lint      # ruff + TypeScript checks
make clean     # remove generated artifacts
```

Frontend-only commands:

```bash
cd frontend
npm run dev
npm run build
```

## Data and Security Notes

- Use only synthetic, public, or properly anonymized transcript samples.
- Do not commit credentials, real applicant PII, or sensitive government data.
- Keep generated AWS resources in `us-east-1` unless the team approves a change.
- The CDK uses serverless services, short log retention, on-demand DynamoDB, and
  retained storage resources to match POC cost and safety constraints.

## Deployment

Deployment is intentionally separate from local development. Read
[DEPLOY_RUNBOOK.md](DEPLOY_RUNBOOK.md) before running any CDK deploy command.

At a minimum, confirm:

- Bedrock access is enabled for the Nova models.
- The AWS budget alerts are in place.
- `make test` passes.
- `make synth` completes cleanly.
- The target account and region are correct.

## Project References

- [design/requirements-draft.md](design/requirements-draft.md) - provisional
  rule requirements and MSBN validation notes
- [design/extraction-vocabulary.md](design/extraction-vocabulary.md) - Bedrock
  extraction fields and enum values
- [DEPLOY_RUNBOOK.md](DEPLOY_RUNBOOK.md) - deployment checklist and teardown
- [infra/README.md](infra/README.md) - CDK-specific notes

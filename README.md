# MSBN Transcript Verification

AI-assisted transcript review workflow for the Mississippi Board of Nursing.
The system ingests transcript PDFs, extracts structured evidence with Amazon
Bedrock and Textract, applies deterministic validation rules, and routes each
application into a reviewer dashboard with audit history.

This system is advisory. It raises review flags and records reviewer actions;
it does not make licensing decisions automatically.

## What The System Does

- Accepts transcript PDF uploads through the dashboard.
- Starts an event-driven AWS pipeline from S3 upload to reviewer queue.
- Extracts transcript fields and supporting evidence per page.
- Aggregates page-level extraction into one rule-engine document.
- Applies deterministic `PHYS`, `CONT`, and `PROG` checks.
- Stores application status, reviewer decisions, and audit events in DynamoDB.
- Exposes queue, detail, review, upload, and audit views through a React app.

## Current Scope

- Single-document transcript review is implemented.
- Reviewer upload, queue, review, and audit flows are implemented.
- Cross-document and population-level checks are present only as placeholders
  for future phases.

## Pipeline Overview

1. A reviewer uploads a transcript PDF.
2. The frontend requests a presigned upload URL from `DashboardApiLambda`.
3. The PDF lands in S3 under `uploads/`.
4. S3 triggers `IntakeLambda`, which writes `METADATA` and starts Step Functions.
5. `ExtractLambda` runs Textract, renders transcript pages, and invokes Bedrock.
6. `AggregationLambda` writes `processed/{applicationId}/aggregation.json`.
7. `RuleEngineLambda` writes `FLAG` items to DynamoDB.
8. `QueueForReviewLambda` updates the application to `READY_FOR_REVIEW` and
   appends a system audit event.
9. `DashboardApiLambda` serves the reviewer UI through API Gateway + Cognito.

## Tech Stack

- Python 3.11
- AWS CDK
- AWS Lambda, Step Functions, S3, DynamoDB, API Gateway, Cognito
- Amazon Bedrock Nova Pro
- Amazon Textract
- React 19, TypeScript, Vite
- pytest, moto, ruff, TypeScript compiler

## Repository Layout

```text
infra/       CDK app and stack definitions
services/    Lambda services and service-level documentation
frontend/    Reviewer dashboard
tests/       Unit, service, infrastructure, and integration tests
design/      Stable reference docs kept with the codebase
scripts/     Helper scripts for deployment and account setup
```

## Local Setup

Prerequisites:

- Python 3.11+
- Node 20+
- AWS CDK CLI: `npm install -g aws-cdk`

Install dependencies:

```bash
make install
```

Run the main checks:

```bash
make test
make lint
make synth
```

Frontend-only workflow:

```bash
cd frontend
npm run dev
npm run build
```

## Operational Notes

- Use only synthetic, public, or properly anonymized transcript samples.
- Do not commit credentials, applicant PII, or account-specific secrets.
- The project is currently pinned to `us-east-1`.
- Review [DEPLOY_RUNBOOK.md](DEPLOY_RUNBOOK.md) before any deploy activity.

## Key Docs

- [DEPLOY_RUNBOOK.md](DEPLOY_RUNBOOK.md): deployment, verification, teardown
- [infra/README.md](infra/README.md): infrastructure structure and stack layout
- [frontend/DEPLOYMENT.md](frontend/DEPLOYMENT.md): frontend release process
- [design/data-model.md](design/data-model.md): DynamoDB entity layout
- [design/extraction-vocabulary.md](design/extraction-vocabulary.md): extraction fields

# MSBN Transcript Verification

AI-assisted transcript verification for the Mississippi State Board of Nursing (MSBN).
Built on AWS serverless services as part of the AWS Innovation Hub POC with the
University of Southern Mississippi.

**Advisory only — every AI output is reviewed and confirmed or overridden by MSBN staff.**

---

## Overview

International applicants to the MSBN submit transcripts, diplomas, CEA reports, and
affidavits of graduation. This system automatically extracts structured data from those
documents using Amazon Bedrock Nova, then applies deterministic Python rules to flag
anomalies (GPA inconsistencies, date logic errors, physical document anomalies, duplicate
license numbers, and more) for human review.

Every flag includes a rule code, human-readable rationale, and the exact source location
(page + text span) in the original document. Reviewers see the flagged location highlighted
in the dashboard and confirm or override each flag before submitting a final decision.
All actions are logged to an immutable DynamoDB audit trail.

---

## Architecture

```
Upload PDF
    │
    ▼
S3 (raw/) ──► IntakeLambda ──► DynamoDB (RECEIVED) ──► Step Functions
                                                               │
                    ┌──────────────────────────────────────────┘
                    │
                    ▼
            ┌── ExtractLambda (× N docs, parallel Map state)
            │     Bedrock Nova Lite/Pro → extraction JSON → S3 (processed/)
            │
            ├── RuleEngineLambda
            │     PHYS / CONT / PROG rules (pure Python) → FLAG items → DynamoDB
            │
            ├── CrossDocLambda
            │     CROSS_001-003 (name, institution, date consistency)
            │
            ├── PopulationCheckLambda
            │     POP_001-003 (license dedup, curriculum cluster, volume anomaly)
            │
            └── NotifyLambda → SNS → Reviewer email

Reviewer authenticates via Cognito → API Gateway → DashboardApiLambda
    Renders page images from S3 presigned URLs
    Overlays flag highlights using source coordinates
    Accepts Confirm / Override decisions → DynamoDB audit trail
```

Full detail: `design/architecture-plan.md` (see note below about the `design/` folder).

---

## Folder Structure

```
msbn-transcript-verification/
│
├── infra/                        AWS CDK (Python) infrastructure
│   ├── app.py                    CDK app entry point
│   ├── cdk.json                  CDK configuration
│   ├── requirements.txt          CDK Python deps
│   ├── README.md                 Bootstrap + synth instructions
│   └── stacks/
│       ├── msbn_transcript_stack.py   Main stack (composes constructs)
│       ├── storage.py                 S3 bucket + DynamoDB table
│       ├── compute.py                 Lambda functions
│       ├── api.py                     API Gateway + Cognito
│       └── workflow.py                Step Functions state machine
│
├── services/                     Lambda function source code
│   ├── intake/                   S3 event → DynamoDB → Step Functions
│   ├── extract/                  PDF → Bedrock Nova → extraction JSON
│   ├── rule_engine/              Single-document rules (PHYS, CONT, PROG)
│   ├── cross_doc/                Cross-document rules (CROSS_001-003)
│   ├── population_check/         Population rules (POP_001-003)
│   ├── notify/                   SNS email notification
│   └── dashboard_api/            REST backend for reviewer dashboard
│
├── frontend/                     React + TypeScript dashboard (Vite)
│   ├── src/
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── index.html
│   ├── package.json
│   └── vite.config.ts
│
├── tests/                        pytest unit tests mirroring services/
│   ├── conftest.py               Shared fixtures (events, Lambda context)
│   ├── intake/
│   ├── extract/
│   ├── rule_engine/
│   ├── cross_doc/
│   ├── population_check/
│   ├── notify/
│   └── dashboard_api/
│
├── design/                       [GITIGNORED — team members need local copies]
│   ├── architecture-plan.md      Full AWS architecture and data model
│   ├── requirements-draft.md     Rule set derived from NCSBN + MS admin code
│   └── open-questions.md         Decisions needed before implementation
│
├── docs/                         [GITIGNORED — reference PDFs]
│   ├── proposal.pdf
│   ├── hub-guide.pdf
│   └── ncsbn-ien-manual.pdf
│
├── CLAUDE.md                     Project instructions for Claude Code [GITIGNORED]
├── Makefile                      install / synth / test / lint / clean
└── pytest.ini                    pytest configuration
```

> **Note:** The `design/` and `docs/` folders are gitignored. Team members must
> keep local copies of `design/architecture-plan.md`, `design/requirements-draft.md`,
> and the reference PDFs. Ask Saurav or the team lead for the latest versions.

---

## Setup

### Prerequisites

- Python 3.11
- Node.js 20
- AWS CDK CLI: `npm install -g aws-cdk`
- AWS credentials configured for `us-east-1`

### Install dependencies

```bash
make install
```

This creates virtual environments under `infra/.venv`, per-Lambda `.venv` dirs,
a shared test `.venv-test`, and installs frontend Node modules.

---

## Synthesize infrastructure (safe — no deployment)

```bash
make synth
```

Generates CloudFormation templates in `infra/cdk.out/`. Review before any deployment.
See `infra/README.md` for the CDK bootstrap step (one-time, per account/region).

---

## Run tests

```bash
make test
```

All tests are unit tests against Lambda handler stubs — no AWS credentials required.

---

## Lint

```bash
make lint
```

Runs `ruff` on Python and `tsc --noEmit` on TypeScript.

---

## Clean

```bash
make clean
```

Removes `cdk.out/`, `frontend/dist/`, `__pycache__`, and `.pytest_cache` directories.

---

## Deployment

**Do not deploy without team review and cost confirmation.**

See `CLAUDE.md` for budget constraints ($1,000 total; CloudWatch alarms at $500/$750/$900).
All deployments must go through a PR and be approved before running `cdk deploy`.

---

## Team

| Name | Role |
|---|---|
| Sudeep Kumal | Backend Engineer |
| Bishal Bagale | Data Engineer |
| Sabin Baral | UI/UX and Frontend |
| Saurav Kandel | Computer Vision |
| Shushil Pant | Database |
| Sujal Maharjan | ML Engineer |

University of Southern Mississippi — AWS Innovation Hub POC for MSBN.

# DashboardApiLambda

REST backend for the MSBN reviewer dashboard, fronted by API Gateway HTTP API.

## Responsibilities

- List applications by status via DynamoDB `GSI1-ReviewQueue`
- Return application details, flags, source spans, and transcript preview info
- Generate presigned S3 URLs for rendered page images
- Accept flag confirmation/override decisions
- Save and retrieve in-progress review drafts
- Accept overall reviewer outcomes:
  - `READY_FOR_LICENSING_REVIEW`
  - `RETURN_TO_APPLICANT`
  - `DENIED`
  - `DEFERRED`
- Write reviewer actions and system events to the audit trail
- Generate presigned upload URLs for new transcript intake

## Auth

Protected by a Cognito JWT authorizer in API Gateway.

## Runtime

Python 3.11

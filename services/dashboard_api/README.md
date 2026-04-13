# DashboardApiLambda

REST backend for the MSBN reviewer dashboard, fronted by API Gateway HTTP API.

**Responsibilities:**
- List applications by status (review queue) via DynamoDB GSI1
- Return application details with flag list and source locations
- Generate presigned S3 URLs for page images (5-minute expiry)
- Accept flag confirmations/overrides from reviewers
- Accept final decisions (APPROVED/DENIED/DEFERRED) with mandatory Nursys checks
- Write all reviewer actions to the DynamoDB audit trail

**Auth:** Cognito JWT authorizer on API Gateway
**Runtime:** Python 3.11

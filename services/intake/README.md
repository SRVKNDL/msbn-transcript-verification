# IntakeLambda

Triggered by S3 event notifications when a PDF is uploaded to the `raw/` prefix.

**Responsibilities:**
- Parse the S3 event to identify the application and document type
- Create an application METADATA record in DynamoDB (status: `RECEIVED`)
- Start a Step Functions Standard Workflow execution with the application ID and document manifest

**Trigger:** S3 `ObjectCreated` event on `raw/` prefix
**Runtime:** Python 3.11

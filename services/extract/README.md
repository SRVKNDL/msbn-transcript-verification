# ExtractLambda

Converts PDF documents into structured JSON via Bedrock Nova multimodal extraction.

**Responsibilities:**
- Retrieve PDF from S3 `raw/` prefix
- Render each page to PNG using poppler/pdf2image
- Store page images in S3 `processed/{app_id}/` prefix
- Call Bedrock Nova (Lite default, Pro for complex cases) with each page image
- Aggregate per-page extraction into a single `extraction_{doc_type}.json`
- Update DynamoDB document status to `EXTRACTED`

**Deployment:** Container image (poppler binaries required)
**Runtime:** Python 3.11
**Timeout:** 5 minutes

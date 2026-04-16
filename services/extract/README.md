# ExtractLambda

Converts transcript PDFs into a structured extraction JSON for downstream rule evaluation.

**Deployment:** Container image (requires poppler binaries; exceeds Lambda zip limit)  
**Runtime:** Python 3.11 on `public.ecr.aws/lambda/python:3.11`  
**Memory:** 2048 MB — PDF rendering is memory-intensive  
**Timeout:** 5 minutes

## What it does (Session 1 — skeleton)

1. Reads `applicationId`, `s3_key`, and `bucket` from the Step Functions event.
2. Downloads the PDF from S3 `uploads/` to `/tmp`.
3. Converts each page to a PNG image using `pdf2image` (backed by `poppler-utils`).
4. Writes page images to `processed/{applicationId}/page_transcript_{n}.png` in S3.
5. Produces a stub extraction record per page — all vocabulary fields present but
   set to `"STUB"` or `null`.
6. Writes the extraction document to `processed/{applicationId}/extraction_transcript.json`.
7. Returns `{"applicationId", "page_count", "extraction_s3_key"}`.

## TODO (Session 2 — Bedrock integration)

- Add `bedrock:InvokeModel` IAM permission (Nova Lite + Pro ARNs).
- For each page image, invoke Bedrock Nova Lite with the extraction prompt
  (`design/extraction-vocabulary.md` Sections 1–3).
- Replace all `"STUB"` values with real extracted values from Nova's response.
- Add `bedrock_model_id`, `prompt_version`, and `extraction_ts` to the extraction
  document for audit trail traceability.
- Handle Nova confidence scores and surface `low`-confidence fields for reviewer
  attention.
- Write DynamoDB `DOCUMENT#{doc_type}` item with extraction S3 path and model
  version used.

## Input (Step Functions event)

```json
{
  "applicationId": "<uuid>",
  "s3_key":        "uploads/<applicationId>/transcript.pdf",
  "bucket":        "<bucket-name>"
}
```

## Output (return value + S3 writes)

```json
{
  "applicationId":     "<uuid>",
  "page_count":        2,
  "extraction_s3_key": "processed/<applicationId>/extraction_transcript.json"
}
```

S3 objects created:

| Key | Description |
|-----|-------------|
| `processed/{appId}/page_transcript_{n}.png` | Per-page PNG for dashboard rendering |
| `processed/{appId}/extraction_transcript.json` | Stub extraction (Session 1) / Nova output (Session 2) |

## Dependencies

| Package | Purpose |
|---------|---------|
| `pdf2image` | PDF → PNG conversion (wraps `pdftoppm` from `poppler-utils`) |
| `pypdf` | PDF metadata (page count validation, used in Session 2) |
| `pillow` | Image handling and PNG serialization |
| `boto3` | S3 download/upload |

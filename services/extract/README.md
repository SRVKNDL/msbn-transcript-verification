# ExtractLambda

Converts transcript PDFs into a structured extraction JSON for downstream rule evaluation.

**Deployment:** Container image (requires poppler binaries; exceeds Lambda zip limit)  
**Runtime:** Python 3.11 on `public.ecr.aws/lambda/python:3.11`  
**Memory:** 2048 MB — PDF rendering is memory-intensive  
**Timeout:** 5 minutes

## What it does

1. Reads `applicationId`, `s3_key`, and `bucket` from the Step Functions event.
2. Starts Textract document analysis on the source S3 PDF with `TABLES`, `FORMS`,
   `QUERIES`, `SIGNATURES`, and `LAYOUT`.
3. Polls paginated Textract results and normalizes raw text, table cells, forms,
   layout blocks, query answers, and signatures by page.
4. Writes the normalized Textract evidence package to
   `processed/{applicationId}/textract_TRANSCRIPT.json`.
5. Downloads the PDF from S3 `uploads/` to `/tmp`.
6. Converts each page to a PNG image using `pdf2image` (backed by `poppler-utils`).
7. Writes page images to `processed/{applicationId}/page_transcript_{n}.png` in S3.
8. Invokes Bedrock Nova per page with the page image and matching Textract
   page context.
9. Writes the extraction document to `processed/{applicationId}/extraction_transcript.json`.
10. Returns the S3 keys needed by downstream workflow steps.

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
  "textract_s3_key":   "processed/<applicationId>/textract_TRANSCRIPT.json",
  "extraction_s3_key": "processed/<applicationId>/extraction_transcript.json"
}
```

S3 objects created:

| Key | Description |
|-----|-------------|
| `processed/{appId}/page_transcript_{n}.png` | Per-page PNG for dashboard rendering |
| `processed/{appId}/textract_TRANSCRIPT.json` | Normalized Textract raw text, tables, forms, layouts, queries, and signatures |
| `processed/{appId}/extraction_transcript.json` | Per-page extraction used by aggregation and review workflows |

## Dependencies

| Package | Purpose |
|---------|---------|
| `pdf2image` | PDF → PNG conversion (wraps `pdftoppm` from `poppler-utils`) |
| `pypdf` | PDF page metadata and validation |
| `pillow` | Image handling and PNG serialization |
| `boto3` | S3, Textract, and Bedrock clients |

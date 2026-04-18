# DynamoDB Data Model — `msbn-applications`

Single-table design. All record types share one table, discriminated by sort key prefix.
On-demand billing. PITR enabled. Removal policy: RETAIN (never deleted on stack teardown).

## Primary key

| Attribute | Type | Pattern |
|---|---|---|
| `PK` | String (partition key) | `APP#{applicationId}` |
| `SK` | String (sort key) | See record types below |

## Record types

### METADATA

One per application. Written by IntakeLambda on upload; updated by the Step Functions
pipeline at each status transition. Read by the dashboard list view and the flag resolution
workflow.

Fields set at intake:

```json
{
  "PK": "APP#a7f3b2c1-4d5e-6f7a-8b9c-0d1e2f3a4b5c",
  "SK": "METADATA",
  "entity_type": "METADATA",
  "applicationId": "a7f3b2c1-4d5e-6f7a-8b9c-0d1e2f3a4b5c",
  "status": "INTAKE_COMPLETE",
  "uploadedAt": "2026-04-14T18:32:01.123456+00:00",
  "s3_key": "uploads/transcript_smith_jane.pdf",
  "originalFilename": "transcript_smith_jane.pdf",
  "size_bytes": 204800
}
```

Additional fields written by the pipeline after extraction:

```json
{
  "applicant_name": "Jane Smith",
  "submission_ts": "2026-04-14T18:32:01+00:00",
  "last_updated_ts": "2026-04-14T18:35:44+00:00",
  "assigned_reviewer": "cognito-sub-xyz",
  "workflow_arn": "arn:aws:states:us-east-1:123456789012:execution:msbn-pipeline:a7f3b2c1-...",
  "document_count": 2,
  "flag_count": 3,
  "high_severity_count": 1,
  "license_number": "RN-12345",
  "GSI1PK": "READY_FOR_REVIEW",
  "GSI1SK": "2026-04-14T18:32:01+00:00",
  "GSI2PK": "RN-12345#PHL",
  "GSI3PK": "University of Santo Tomas#BSN#2024"
}
```

**Who writes it:** IntakeLambda (initial write), pipeline Lambdas (status updates),
DashboardLambda (reviewer assignment, flag counts).  
**Who reads it:** DashboardLambda, PopulationCheckLambda (via GSI2/GSI3).

---

### DOCUMENT#{doc_type}

One item per document per application (`doc_type` is `TRANSCRIPT`, `DIPLOMA`, `CEA`, etc.).
Tracks the S3 paths for the raw PDF and the extraction JSON, plus the model version used.
Written by ExtractLambda after extraction completes. Read by RuleEngineLambda,
CrossDocLambda, and the dashboard.

```json
{
  "PK": "APP#a7f3b2c1-...",
  "SK": "DOCUMENT#TRANSCRIPT",
  "entity_type": "DOCUMENT",
  "doc_type": "TRANSCRIPT",
  "status": "EXTRACTED",
  "s3_raw_key": "uploads/transcript_smith_jane.pdf",
  "s3_extraction_key": "processed/a7f3b2c1-.../extraction_TRANSCRIPT.json",
  "s3_aggregation_key": "processed/a7f3b2c1-.../aggregation.json",
  "model_id": "amazon.nova-lite-v1:0",
  "prompt_version": "v1.2",
  "page_count": 4,
  "extracted_at": "2026-04-14T18:35:11+00:00"
}
```

**Who writes it:** ExtractLambda.  
**Who reads it:** RuleEngineLambda, CrossDocLambda, DashboardLambda.

---

### FLAG#{rule_code}#{seq}

One item per flag raised by the rule engine. `seq` is a zero-padded integer (e.g., `001`)
that disambiguates multiple flags from the same rule on the same application. Append-only;
reviewer actions update `reviewer_status`, `reviewer_id`, `reviewer_ts`, and
`reviewer_notes` in place (these are the only mutable fields).

```json
{
  "PK": "APP#a7f3b2c1-...",
  "SK": "FLAG#CONT_005#001",
  "entity_type": "FLAG",
  "rule_code": "CONT_005",
  "severity": "High",
  "rationale": "Reported GPA 3.4 differs from computed mean 2.74 by 23.9%.",
  "source_location": {
    "page_number": 2,
    "text_spans": ["Overall GPA: 3.4"]
  },
  "reviewer_status": "OPEN",
  "reviewer_id": null,
  "reviewer_ts": null,
  "reviewer_notes": null,
  "extraction_s3_ref": "processed/a7f3b2c1-.../extraction_TRANSCRIPT.json"
}
```

`source_location` uses the shape defined in `extraction-vocabulary.md`
Section 5: `{page_number: int, text_spans: [str]}`. `text_spans` is always
an array (length 1 for single-location citations, longer for fields
derived from multiple supporting phrases). This is the shape the rule
engine emits and the dashboard consumes. Pixel-level bounding boxes
are a Phase 3+ addition (requires Textract) and would be attached as a
separate optional key, not nested inside `source_location`.

**Who writes it:** RuleEngineLambda, CrossDocLambda, PopulationCheckLambda.  
**Who reads it:** DashboardLambda. DashboardLambda also writes the reviewer fields.

---

### AUDIT#{ISO8601_timestamp}

Append-only audit log. One item per state change or reviewer action. Never updated or
deleted. The timestamp in the SK is the event time in ISO 8601 UTC
(`2026-04-14T18:35:44.000Z`), which keeps items in chronological order within a `Query`
on the partition key.

```json
{
  "PK": "APP#a7f3b2c1-...",
  "SK": "AUDIT#2026-04-14T18:35:44.000Z",
  "entity_type": "AUDIT",
  "actor": "system",
  "event_type": "FLAG_RAISED",
  "previous_state": null,
  "new_state": {
    "rule_code": "CONT_005",
    "severity": "High",
    "rationale": "Reported GPA 3.4 differs from computed mean 2.74 by 23.9%."
  }
}
```

Valid `event_type` values: `STATUS_CHANGED`, `FLAG_RAISED`, `FLAG_CONFIRMED`,
`FLAG_OVERRIDDEN`, `REVIEWER_ASSIGNED`, `DECISION_SUBMITTED`, `NURSYS_ACKNOWLEDGED`.

`actor` is `"system"` for pipeline events and the Cognito sub for reviewer actions.

**Who writes it:** Every Lambda in the pipeline (system events), DashboardLambda
(reviewer events).  
**Who reads it:** DashboardLambda (Timeline View, SP-9).

---

### DECISION

One per application, written when a reviewer submits a final decision. Only one DECISION
item can exist per application (the SK is the literal string `DECISION`, not a timestamp).

```json
{
  "PK": "APP#a7f3b2c1-...",
  "SK": "DECISION",
  "entity_type": "DECISION",
  "reviewer_id": "cognito-sub-xyz",
  "decision": "DENIED",
  "decision_ts": "2026-04-14T20:11:03+00:00",
  "notes": "CONT_005 confirmed. Transcript GPA inconsistency not explained by applicant.",
  "nursys_acknowledged": true,
  "nursys_ack_ts": "2026-04-14T20:14:22+00:00"
}
```

`nursys_acknowledged` and `nursys_ack_ts` are required for `DENIED` decisions (SP-10/NRB
Policy 7). The DashboardLambda rejects a submit request for a denial that is missing these
fields.

**Who writes it:** DashboardLambda on final decision submit.  
**Who reads it:** DashboardLambda, audit/reporting queries.

---

## Global Secondary Indexes

### GSI1-ReviewQueue

| Attribute | Value |
|---|---|
| Partition key | `status` (e.g., `READY_FOR_REVIEW`) |
| Sort key | `submission_ts` (ISO 8601, sort ascending = oldest first) |
| Projection | ALL |
| Populated on | METADATA items only |

The dashboard list view queries this index to fetch all applications with a given status,
ordered by submission time. Projection ALL means no second lookup is needed to render the
list row.

### GSI2-LicenseDedup

| Attribute | Value |
|---|---|
| Partition key | `GSI2PK` — composite `license_number#country` (e.g., `RN-12345#PHL`) |
| Sort key | `PK` — the table partition key (`APP#{applicationId}`) |
| Projection | KEYS_ONLY |
| Populated on | METADATA items after extraction |

Used by `PopulationCheckLambda` for rule `POP_001`. A query on `GSI2PK` returns all
`APP#...` keys with the same license number and country, identifying duplicate submissions
without a table scan. Sort key returned directly is the colliding applicationId — no second
lookup needed.

### GSI3-InstitutionCluster

| Attribute | Value |
|---|---|
| Partition key | `GSI3PK` — composite `institution#program#grad_year` |
| Sort key | `PK` — the table partition key (`APP#{applicationId}`) |
| Projection | KEYS_ONLY |
| Populated on | METADATA items after extraction |

Used by `PopulationCheckLambda` for rules `POP_002` and `POP_003`. A query on `GSI3PK`
returns all applications from the same school, program, and graduation year, which
`PopulationCheckLambda` uses to detect anomalous curriculum clusters. Rules activate once
a cluster reaches ≥ 3 applications; single-application clusters produce no flags.

---

## Access patterns

| Pattern | Index | Query |
|---|---|---|
| Fetch all items for one application | Table (PK query) | `PK = APP#{id}` |
| Fetch METADATA for one application | Table (PK + SK) | `PK = APP#{id}`, `SK = METADATA` |
| Fetch all flags for one application | Table (PK + SK prefix) | `PK = APP#{id}`, `SK begins_with FLAG#` |
| Fetch audit trail for one application | Table (PK + SK prefix) | `PK = APP#{id}`, `SK begins_with AUDIT#` |
| List all applications pending review | GSI1 | `status = READY_FOR_REVIEW`, sorted by `submission_ts` |
| Detect duplicate license numbers | GSI2 | `GSI2PK = {license}#{country}` |
| Cluster applications by school | GSI3 | `GSI3PK = {institution}#{program}#{year}` |

---

*Owned by Shushil Pant (Database). Questions about GSI design → Saurav or Sujal.*  
*Provisional decision Q11 (single-table vs. multi-table) accepted at standup 2026-04-13.*

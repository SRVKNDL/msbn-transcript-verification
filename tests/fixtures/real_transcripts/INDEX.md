# Real Transcript Fixtures

Anonymized Mississippi-domestic nursing transcripts extracted from
`docs/MSBON anonymized transcripts.pdf` (source PDF retained unmodified).

These are test fixtures only. No real applicant data or PII is present.
All six source transcripts were provided by MSBN with identifying information
removed prior to our team receiving them.

**Usable fixtures: 4** (pages 6–10 skipped — UMMC graduate-level MSN/BSN,
incomplete transcripts not representative of POC target population).

---

## transcript-01-northwest-ms-cc.pdf

| Attribute       | Value |
|-----------------|-------|
| Institution     | Northwest Mississippi Community College |
| Program         | Practical Nursing |
| Degree/Award    | Certificate of Practical Nursing |
| Pages           | 2 |
| Source pages    | 2, 1 (reordered — source PDF has pages reversed) |
| Page dimensions | 613×797 pt, 613×799 pt (portrait) |
| File size       | ~820 KB |

**Key attributes:**
- Grading scale: Standard letter grades (A–F) with quality-point GPA
- Seal/stamp: Embossed institutional seal visible
- Credits: Semester credit hours
- Course codes: Mississippi community college format (NUR prefix)
- Anomaly notes: None — clean baseline transcript for rule-engine testing

---

## transcript-02-northeast-ms-cc.pdf

| Attribute       | Value |
|-----------------|-------|
| Institution     | Northeast Mississippi Community College |
| Program         | Associate Degree Nursing (ADN) |
| Degree/Award    | Associate of Applied Science — Nursing |
| Pages           | 2 |
| Source pages    | 3–4 (in order) |
| Page dimensions | 797×612 pt, 797×612 pt (landscape) |
| File size       | ~925 KB |

**Key attributes:**
- Grading scale: Letter grades with numeric GPA on 4.0 scale
- Seal/stamp: Registrar signature and date stamp
- Credits: Semester credit hours; two-year program course sequence
- Course codes: NUR prefix with ACEN-accredited curriculum markers
- Anomaly notes: Landscape orientation (rotated pages in source)

---

## transcript-03-copiah-lincoln-cc.pdf

| Attribute       | Value |
|-----------------|-------|
| Institution     | Copiah-Lincoln Community College |
| Program         | Practical Nursing Level III Certificate |
| Degree/Award    | Practical Nursing Certificate |
| Pages           | 1 |
| Source pages    | 5 |
| Page dimensions | 797×612 pt (landscape) |
| File size       | ~313 KB |

**Key attributes:**
- Grading scale: Percentage-based grades alongside letter grades
- Seal/stamp: Institutional seal present
- Credits: Contact hours / clock hours (not semester credits) — notable
  difference from credit-hour peers; rule engine must handle both formats
- Course codes: PN prefix
- Anomaly notes: Single-page; clock-hour credit format is a key test
  case for the credit-unit normalization rule (VAL-CREDITS-FORMAT)

---

## transcript-06-itawamba-cc.pdf

| Attribute       | Value |
|-----------------|-------|
| Institution     | Itawamba Community College |
| Program         | Technical Nursing |
| Degree/Award    | Technical Certificate — Nursing |
| Pages           | 1 |
| Source pages    | 11 |
| Page dimensions | 611×797 pt (portrait) |
| File size       | ~525 KB |

**Key attributes:**
- Grading scale: Letter grades; GPA listed
- Seal/stamp: Registrar stamp with raised seal
- Credits: Semester credit hours
- Course codes: NUR/NTE prefix
- Anomaly notes: "Technical Nursing" title may need mapping to
  recognized MSBN program type; good test for program-name normalization

---

## Skipped pages

| Source pages | Institution | Reason skipped |
|---|---|---|
| 6–10 | University of Mississippi Medical Center (UMMC) | Graduate-level MSN and BSN programs; incomplete transcripts; outside POC scope (MS-domestic community college / PN/ADN focus) |

---

## Usage notes

- These fixtures are used by `tests/` for Extract Lambda and Validate Lambda
  integration tests.
- Naming follows `transcript-{NN}-{institution-slug}.pdf`. Numbers 04 and 05
  are intentionally absent (reserved for the two UMMC transcripts if they are
  ever completed and brought into scope).
- Do not add real applicant transcripts to this directory under any
  circumstances.

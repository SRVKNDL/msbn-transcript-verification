# Open Questions — Architecture Plan Triage

> Extracted from `design/architecture-plan.md` Section 8. Each question is annotated with
> decision ownership: (a) developer call, (b) MSBN input required, (c) Hub team input required.

---

## Action Items

### Developer Standup Agenda

Decide these internally before external meetings. No outside input required.

- **Q1** — Container image vs. Lambda layer for PDF rendering (Sudeep + Saurav)
- **Q2** — Defer Textract to Phase 3? (team consensus)
- **Q5** — Single-page vs. multi-page Bedrock invocations (Sujal + Sudeep)
- **Q6** — Controlled vocabulary for PHYS rule visual descriptions (Sujal + Saurav)
- **Q11** — Single-table vs. multi-table DynamoDB (Shushil)
- **Q12** — Synthetic test corpus ownership and timeline (Bishal + Saurav)

### Hub Team Message (Shelley / Benjamin)

One question, can be a short email or Slack message:

- **Q1** — Confirm that ECR (Elastic Container Registry) is enabled in the sandbox account.
  We need it to deploy a Lambda container image for the PDF extraction function. If ECR is
  restricted, we will fall back to a pre-compiled Lambda layer.

### MSBN Meeting Agenda (priority order)

These block architecture or workflow decisions. Schedule a single call if possible.

1. **Q3** — How do applications arrive today? All documents in one batch, or piecemeal over
   days? (Blocks: Step Functions trigger design, frontend upload flow)
2. **Q8** — Does MSBN have programmatic Nursys API access, or is verification done manually
   through the Nursys.org website? (Blocks: SP-2, SP-3, SP-6 dashboard design)
3. **Q9** — For the POC demo, is email/password login acceptable for 3–5 test reviewer
   accounts, or does MSBN require SSO through an existing identity provider?
   (Blocks: Cognito setup scope)
4. **Q4** — Who on the MSBN side will supply official reference data (approved accreditation
   bodies, CEA agencies, grading scales, institution seal types)? Placeholder data is fine
   for development; official values are needed before Phase 4. (Blocks: rule accuracy)
5. **Q10** — What is the maximum acceptable age for a Credentials Evaluation Agency report?
   (e.g., 2 years, 5 years) Needed to enforce NRB Policy 11. (Blocks: CEA expiration rule)

### Deferred

These cannot be answered until later phases produce data to calibrate against.

- **Q7** — POP_002/003 cluster thresholds. Ship as advisory-only Low severity; calibrate
  during Phase 5 testing against synthetic corpus. Needs MSBN review of flagged test results.
- **Q10** (production threshold) — Listed in MSBN agenda above for initial answer, but final
  production-grade threshold requires MSBN policy confirmation before go-live.

---

## Full Question Detail

### Phase 2 Blockers (environment setup, data ingestion)

---

**Q1. PDF rendering in Lambda — container image or layer?**

ExtractLambda needs poppler + pdf2image for PDF-to-PNG conversion. Lambda zip deployments
cap at 250MB unzipped; poppler binaries alone are ~80MB. Options: (a) Lambda container
image (up to 10GB, simplest), (b) custom Lambda layer with pre-compiled ARM64 poppler
binaries. Recommendation: container image for ExtractLambda only; standard zip for
everything else.

- **(a) Developer call** — Sudeep (backend) and Saurav (CV) decide. This is a packaging
  question with no business implications.
- **(b) MSBN input** — None.
- **(c) Hub team** — Confirm ECR is enabled in the sandbox. If restricted, fall back to
  Lambda layer approach.

> **Decision (2026-04-13):** Container image for ExtractLambda only; standard zip for
> everything else. Status: Provisional — pending MSBN review in Phase 5.

---

**Q2. Textract now or Phase 3?**

Nova text spans are sufficient for "which page, what text" traceability. Precise pixel-level
bounding boxes (tight highlight overlays on page images) require Textract. Deferring
simplifies Phase 2. Cost is negligible (~$1.50/month at POC volume).

- **(a) Developer call** — Yes. Recommend defer to Phase 3. The team can build the pipeline
  with Nova-only first and add Textract when the dashboard rendering proves it's needed.
- **(b) MSBN input** — Needed in Phase 3, not now. The question is whether MSBN reviewers
  find text-span highlighting adequate or need pixel-precise boxes. Answer comes from a
  Phase 4 demo.
- **(c) Hub team** — None.

> **Decision (2026-04-13):** Defer Textract to Phase 3; build Phase 2 pipeline with
> Nova-only extraction. Status: Provisional — pending MSBN review in Phase 5.

---

**Q3. Multi-document upload UX.**

Does MSBN upload all documents for one application in a single batch, or one document at a
time? This determines whether the Intake Lambda triggers Step Functions immediately on each
upload or waits for a "submit" signal indicating all documents are ready.

- **(a) Developer call** — Partially. Sabin (frontend) designs the upload flow, but the
  decision depends on MSBN's current process.
- **(b) MSBN input** — **Yes, required.** Ask MSBN: "How do applications arrive today? All
  documents at once, or piecemeal over days?" This shapes both the frontend UX and the
  Step Functions trigger logic.
- **(c) Hub team** — None.

> **Status:** Open — scheduled for the next MSBN meeting.

---

**Q4. Reference table ownership and seeding.**

Who populates and maintains the S3 reference lookup tables (accreditation list, grading
scales, institution seal types, diploma mill phrases, nursing course names, CEA agencies)?

- **(a) Developer call** — Team seeds Phase 2 tables from the requirements-draft.md
  placeholders. Bishal (data engineer) is the logical owner of the seeding scripts.
- **(b) MSBN input** — **Yes, required before Phase 4.** Placeholder data is fine for
  development, but every HIGH-severity rule depends on reference data accuracy. MSBN must
  supply official values for: approved accreditation bodies, accepted CEA agencies, grading
  scales per country, and known institution seal types. Without these, the rule engine flags
  can't be defended.
- **(c) Hub team** — None.

> **Status:** Open — scheduled for the next MSBN meeting.

---

### Phase 3 Blockers (rule engine + extraction)

---

**Q5. Bedrock multimodal page sending strategy.**

Send each page as a separate Bedrock invocation (simple, parallelizable, easy to attribute
source page) vs. batch multiple pages into one invocation using Nova's 300K context window
(fewer calls, potentially better cross-page reasoning, harder to attribute individual page
locations)?

- **(a) Developer call** — Yes. Sujal (ML) and Sudeep (backend) decide. Recommendation:
  single-page invocations for traceability. Revisit only if cost becomes a real concern
  (the cost estimate shows it won't).
- **(b) MSBN input** — None.
- **(c) Hub team** — None.

> **Decision (2026-04-13):** Single-page Bedrock invocations for traceability; revisit only
> if cost becomes a real concern. Status: Provisional — pending MSBN review in Phase 5.

---

**Q6. PHYS rule visual confidence thresholds.**

Nova describes seal quality and print technology in natural language ("pixelated," "clear
edges," "laser printed"). Python rules must map these descriptions to flag/no-flag. This
requires a controlled vocabulary: the extraction prompt constrains Nova to emit values from
an enum (e.g., `seal_quality: "clear" | "degraded" | "pixelated" | "absent"`), and the
rule checks against that enum.

- **(a) Developer call** — Yes. Sujal (ML) designs the extraction prompt vocabulary; Saurav
  (CV) validates that Nova's visual descriptions are reliable for the enum values chosen.
  This is iterative — expect prompt tuning during Phase 3.
- **(b) MSBN input** — None directly, but the threshold for "how degraded is too degraded"
  may need MSBN calibration during Phase 5 testing.
- **(c) Hub team** — None.

> **Decision (2026-04-13):** Controlled enum vocabulary for extraction prompts; Sujal owns
> vocabulary design, Saurav validates Nova reliability. Status: Provisional — pending MSBN
> review in Phase 5.

---

**Q7. POP_002/003 cluster thresholds.**

POP_002 flags curricula with < X% overlap from the same school/program/year. POP_003 flags
> 3x the 6-month baseline application rate from an institution. Both thresholds are
provisional and can't be validated until a synthetic test corpus exists.

- **(a) Developer call** — Yes. Ship both rules as advisory-only (Low severity). Tune
  thresholds during Phase 5 testing against the synthetic corpus. Bishal (data) and Sujal
  (ML) own the threshold calibration.
- **(b) MSBN input** — Deferred to Phase 5. MSBN reviews the flagged test results and tells
  the team whether the thresholds are too sensitive or too loose.
- **(c) Hub team** — None.

---

### Phase 4 Blockers (reviewer dashboard)

---

**Q8. Nursys integration scope.**

Does MSBN have programmatic Nursys API access, or do staff verify via the Nursys.org browser
interface manually? If manual, the dashboard provides a deep-link pre-filled with the
applicant's license number. If API access exists, the system could automate the lookup and
cache results.

- **(a) Developer call** — No. The team can build either path, but only MSBN knows which
  one is real.
- **(b) MSBN input** — **Yes, required.** Ask MSBN: "Do you have Nursys API credentials, or
  is verification done through the website?" The answer determines whether SP-2, SP-3, and
  SP-6 are deep-links or automated lookups.
- **(c) Hub team** — Possibly. If MSBN has API credentials, Shelley/Benjamin should confirm
  whether the sandbox account's networking/IAM allows outbound calls to the Nursys API
  endpoint.

> **Status:** Open — scheduled for the next MSBN meeting.

---

**Q9. Cognito user management.**

Who creates reviewer accounts in the Cognito User Pool? For the POC, the team can seed 5–10
accounts manually. If MSBN has an existing identity provider (Active Directory, Okta),
Cognito supports SAML/OIDC federation but that adds Phase 4 scope.

- **(a) Developer call** — For the POC, yes. Sudeep or Shushil manually creates test
  accounts. Federation is out of scope for the POC unless MSBN requires it.
- **(b) MSBN input** — Light touch. Ask MSBN: "For the demo, are you okay with us creating
  3–5 test accounts with email/password login, or do you require SSO through your existing
  identity provider?" If the answer is test accounts, this is settled.
- **(c) Hub team** — Only if federation is required. Shelley/Benjamin would need to confirm
  whether the sandbox account supports Cognito identity provider federation with MSBN's IdP.

> **Status:** Open — scheduled for the next MSBN meeting.

---

**Q10. CEA report expiration threshold.**

NRB Policy 11 says CEA reports should have an expiration date. The system extracts the CEA
report date, but without a threshold it can't auto-flag expired reports. Until MSBN specifies
the maximum acceptable age (2 years? 5 years?), the system surfaces the date in the
dashboard without flagging.

- **(a) Developer call** — No. The extraction and display can be built, but the threshold is
  a policy decision.
- **(b) MSBN input** — **Yes, required before production.** Not a blocker for the POC demo —
  surface the date, let the reviewer judge. But before production, MSBN must specify the
  threshold or the system cannot enforce Policy 11.
- **(c) Hub team** — None.

> **Status:** Open — scheduled for the next MSBN meeting.

---

### Cross-Phase

---

**Q11. Single-table vs. multi-table DynamoDB.**

The architecture plan specifies a single-table design (`msbn-applications`) with SK-prefix
discrimination. This is optimal for the access patterns but requires the team to be
comfortable with DynamoDB single-table patterns. Alternative: three separate tables
(Applications, Flags, AuditTrail) that are simpler to reason about at the cost of
cross-table queries.

- **(a) Developer call** — Yes. **Shushil (database)** decides, ideally after reading the
  access patterns in Section 4 of `design/architecture-plan.md` and assessing the team's
  DynamoDB experience. If anyone on the team is uncertain about composite keys and GSI
  projections, go multi-table — the cost difference at POC volume is zero and correctness
  matters more than elegance.
- **(b) MSBN input** — None.
- **(c) Hub team** — None.

> **Decision (2026-04-13):** Single-table DynamoDB (`msbn-applications`) with SK-prefix
> discrimination; Shushil owns the table design. Status: Provisional — pending MSBN review
> in Phase 5.

---

**Q12. Synthetic test corpus ownership.**

Requirements Section 7 defines five MSBN-validated test cases (Cases A–E) as synthetic data
targets. Someone needs to build the actual fake PDFs — transcripts with manipulated GPAs,
non-nursing course names, wrong seal types, diploma mill language, missing contact info — so
the rule engine can be tested.

- **(a) Developer call** — Yes. **Bishal (data engineer)** is the logical owner. **Saurav
  (CV)** should collaborate on the visual fraud signals (seal type, text alignment,
  pixelation). Recommend starting in parallel with Phase 3 so test data is ready when the
  rule engine is.
- **(b) MSBN input** — None for generation. MSBN reviews the synthetic data during Phase 5
  to confirm the test cases are realistic.
- **(c) Hub team** — None.

> **Decision (2026-04-13):** Synthetic corpus based on Cases A–E; Bishal owns generation,
> Saurav collaborates on visual fraud signals; start in parallel with Phase 3. Status:
> Provisional — pending MSBN review in Phase 5.

---

## Summary Grid

| Q | Decision maker | MSBN needed? | Hub team needed? |
|---|---|---|---|
| Q1 | Sudeep + Saurav | No | Confirm ECR enabled |
| Q2 | Team (defer to Phase 3) | Phase 3 demo feedback | No |
| Q3 | Sabin (frontend) | **Yes — current upload process** | No |
| Q4 | Bishal (seeding); MSBN (official values) | **Yes — before Phase 4** | No |
| Q5 | Sujal + Sudeep | No | No |
| Q6 | Sujal + Saurav | Phase 5 calibration | No |
| Q7 | Bishal + Sujal | Phase 5 calibration | No |
| Q8 | MSBN decides | **Yes — Nursys API vs. manual** | Maybe (networking) |
| Q9 | Sudeep / Shushil (POC accounts) | Light touch | Only if federation |
| Q10 | MSBN decides | **Yes — threshold value** | No |
| Q11 | Shushil | No | No |
| Q12 | Bishal + Saurav | Phase 5 review | No |

**Four questions require MSBN input before confident implementation:** Q3, Q4, Q8, Q10.
Of those, Q3 and Q8 are the most urgent — they affect Step Functions workflow structure
and dashboard Nursys integration pattern respectively. Q4 and Q10 can proceed with
placeholder data until Phase 4.

---

*Last updated: 2026-04-13. Companion document to `design/architecture-plan.md`.*

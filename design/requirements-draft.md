# MSBN Transcript Verification — Draft Requirements

> **DRAFT — NOT OFFICIAL MSBN POLICY**
> Derived from: NCSBN *Licensure of Internationally Educated Nurses: A Resource Manual* (2023),
> NCSBN Uniform Licensure Requirements (2011), and the MSBN/NCSBN IT/Ops Conference 2022
> presentation "Fraud Detection: Red Flags in Application Documents" (Shan Montgomery, CFO/COO
> MSBN; Kathleen Russell, Associate Director Nursing Regulation, NCSBN).
> This document must be reviewed and replaced with official MSBN Standard Operating
> Procedures before any production use. All thresholds and rule logic are provisional
> and require MSBN validation.

---

## 1. Minimum Education Requirements (RN Licensure by Endorsement — IEN Pathway)

Source: NCSBN Uniform Licensure Requirements table.

| Requirement | Detail |
|---|---|
| Nursing program graduation | Must be comparable to a U.S. member-board-approved RN prelicensure program, verified by an approved credentials evaluation agency |
| Program accreditation | Program must be approved by an accrediting body recognized in its country of origin |
| Program length | At minimum comparable to a U.S. two-year RN program |
| Credentials evaluation | Must be conducted by an agency performing course-by-course analysis (not document-by-document) |
| NCLEX-RN exam | Successful completion required |
| Home-country licensure | Self-disclosure required; board independently verifies licensure status and any disciplinary history in country of origin |
| Criminal background | Self-disclosure of all misdemeanors, felonies, and plea agreements (even if adjudication was withheld); state and federal fingerprint checks |
| Substance use | Self-disclosure of any substance use disorder within the last five years |
| Other licensure actions | Self-disclosure of any actions against any professional or occupational license, registration, or certification |

---

## 2. Required Coursework Domains and Minimum Hours

Source: NCSBN manual sample evaluation report (page 8 of manual). These figures reflect a
sample comparable program; they are a reference baseline only, not confirmed MSBN minimums.
**MSBN must supply official hour thresholds before these values are used in production rules.**

### Clinical Nursing Domains

| Domain | Min Theory Hours (ref) | Min Clinical Hours (ref) | Notes |
|---|---|---|---|
| Adult Medical/Surgical | 150 | 1,200 | Combined in some programs |
| Adult Medical | 100 | 700 | If reported separately |
| Adult Surgical | 50 | 500 | If reported separately |
| Obstetrics / Maternal Health | 20 | 250 | |
| Pediatrics | 25 | 700 | |
| Psychiatric / Mental Health | 20 | 250 | |
| Gerontology | TBD | TBD | Noted as commonly deficient in IEN transcripts |
| Community Health | TBD | 250 | Theory hours vary widely |

### Foundational Sciences

| Domain | Min Theory Hours (ref) | Min Clinical Hours (ref) |
|---|---|---|
| Anatomy / Physiology | 50 | — |
| Pharmacology | 12 | — |
| Nutrition | 40 | — |
| Microbiology | 4 | — |
| Psychology | 12 | — |

> Deficiencies in Gerontology and Community Health theory are specifically called out in the
> NCSBN manual as common gaps in IEN credentials. Flag any transcript with zero hours in
> either domain for human review.

---

## 3. Acceptable Accreditations

U.S. nursing programs must hold accreditation from one of:

| Body | Full Name |
|---|---|
| ACEN | Accreditation Commission for Education in Nursing |
| CCNE | Commission on Collegiate Nursing Education |

For international programs, accreditation must be from the recognized governing body for nursing
education in the country of origin. The credentials evaluation agency is responsible for
confirming this.

> **MSBN confirmation required:** MSBN must supply its approved list of credentials evaluation
> agencies (e.g., CGFNS, NACES members) and any country-specific accreditation bodies it
> accepts. The system will maintain this as a lookup table; entries below are placeholders.

Placeholder accepted evaluators (to be replaced with official MSBN list):
- Commission on Graduates of Foreign Nursing Schools (CGFNS)
- Any NACES member agency that performs nursing-specific, course-by-course evaluations

---

## 4. English Proficiency Requirements

Source: NCSBN manual; CFR exemption criteria.

**Exam required** unless applicant meets the exemption criteria below. Exam must assess all
four components: reading, speaking, writing, and listening.

Commonly accepted exams (MSBN must confirm its accepted list):
- TOEFL (Test of English as a Foreign Language)
- IELTS (International English Language Testing System)
- OET (Occupational English Test — nursing stream)
- TOEIC (where accepted by the jurisdiction)

**Exemption criteria** (both conditions must be met):
1. English is the official/native language of the applicant's country of origin, AND
2. The nursing program was taught in English using English-language textbooks.

Countries typically exempt under CFR: Australia, Canada (except Quebec), Ireland,
New Zealand, United Kingdom, and U.S. territories where instruction is in English.

> Flag for human review: applicants claiming exemption from countries with mixed-language
> instruction (e.g., Quebec, Puerto Rico) or where the program language of instruction
> does not match the country's primary language.

---

## 5. Recommended NRB Policies

Source: MSBN/NCSBN IT/Ops Conference 2022 presentation (Shan Montgomery, Kathleen Russell).
These 11 policies were recommended for all Nurse Regulatory Bodies. Several directly
constrain system design and reviewer workflow; they are included here as context for
implementation decisions, not as detection rules.

| # | Policy | System Design Impact |
|---|---|---|
| 1 | Require initial and ongoing staff fraud detection training for all licensure staff | Training materials and onboarding flows are out of scope for this system but should be documented for MSBN |
| 2 | Plain language in application questions | Affects applicant-facing portal; flag for UI/UX team |
| 3 | Clear description and definition of attestation in licensure application | Attestation fields in the application must be unambiguous; affects data model |
| 4 | Clear description of acceptable verification of licensure in application | Documents acceptable as licensure verification must be enumerated in a lookup table |
| 5 | No withdrawal of licensure applications to avoid denial or discipline | Application state machine must prevent withdrawal once a flag or review is in progress; affects Step Functions workflow |
| 6 | Verification of identity, licensure, denial or discipline via Nursys.org | System must support (or hand off to) Nursys lookup; see CROSS_001, POP_001 |
| 7 | Denial of initial/renewal licensure and imposters entered to Nursys.org/NPDB | Confirmed denials must trigger a Nursys/NPDB reporting step; add to audit trail design |
| 8 | Executive officer or lead staff to approve method and type of electronic materials | Permission model must enforce role-based approval for accepting electronic documents |
| 9 | Staff separation of duties throughout the licensure application review process | No single staff member should be able to approve their own review; enforce in IAM + dashboard |
| 10 | Reduce effective time period or eliminate temporary permits | Out of scope for transcript verification but affects downstream licensure workflow |
| 11 | Establish an expiration date for Credentials Evaluation Agency Reports | CEA report date must be extracted and compared against an MSBN-configured expiration threshold |

> **Policies with immediate system design implications:** 5 (state machine), 6 (Nursys
> integration), 8 (role-based approval), 9 (separation of duties), 11 (CEA expiration).
> Confirm MSBN's current Nursys integration status before Phase 2 design.

---

## 6. Fraud Red Flag Rules

Source: NCSBN IEN manual (fraud patterns) and MSBN/NCSBN 2022 presentation (Safe Practices
framework). Rules are organized under the **10 Safe Practices for Fraud Prevention, Detection
and Communication** defined by MSBN/NCSBN. Each rule maps to exactly one Safe Practice
category. Safe Practice categories with no automated detection rule are noted as
workflow-only.

Each rule includes: rule code, description, detection logic (plain Python target), severity,
and Safe Practice category. Severity reflects risk to public safety if undetected.

---

### SP-1 — Verification of Applicant Identity

**CROSS_001 — CROSS_DOC_NAME_MISMATCH**
- **Description:** Applicant name (or aliases) differs across transcript, diploma, application,
  and licensure documents beyond expected transliteration variation.
- **Detection logic:** Extract name fields from all submitted documents. Apply fuzzy matching;
  flag pairs where similarity falls below threshold and no alias explanation is provided.
- **Severity:** High

---

### SP-2 — Verification that Applicant Record Does Not Include a Previous Denial of Licensure

**POP_001 — DUPLICATE_LICENSE_NUMBER**
- **Description:** The same home-country license number appears on applications from two or
  more different individuals, which may indicate impersonation or a previously denied
  applicant re-applying under a false identity.
- **Detection logic:** On each submission, query existing records for the same license number
  from the same country. Flag any collision.
- **Severity:** High

> *Workflow note:* Automated detection via POP_001 captures the license number collision
> signal. Full previous-denial verification requires a Nursys.org lookup (NRB Policy 6);
> this lookup is outside the automated pipeline and must be completed by licensure staff.

---

### SP-3 — Verification that Applicant Record Does Not Include Disciplinary Action or BON Alert

> *Workflow only — no automated extraction rule.* This check requires a Nursys.org query
> against the applicant's name, date of birth, and home-country license number. The system
> flags the record for staff to initiate this lookup as part of the standard review queue.
> Design: add a mandatory "Nursys check completed" field to the DynamoDB audit record before
> any approval action is available.

---

### SP-4 — Analysis of Authenticity of Documents

**PHYS_001 — PIXELATED_SEAL_OR_LOGO**
- **Description:** Institution seal, logo, or stamp appears pixelated or of low resolution.
- **Detection logic:** Computer vision check on extracted seal/logo regions; flag if pixel
  density or edge sharpness falls below threshold, or if image artifacts consistent with
  copy-of-copy degradation are present.
- **Severity:** High

**PHYS_002 — MISSING_OR_INCORRECT_SECURITY_FEATURES**
- **Description:** Transcript lacks expected security features for its claimed country/institution
  (e.g., no watermark, no micro-printing, no hologram, no serial number in expected position),
  OR security features are of the wrong type for the institution (e.g., stamped seal presented
  where institution is known to use embossed seals — see Case C, Section 7).
- **Detection logic:** Compare against known security feature templates per country. Flag if
  expected features are absent, positionally inconsistent, or of the wrong physical type
  (embossed vs. stamped). Seal type classification requires computer vision or human review.
- **Severity:** High

**PHYS_003 — PRINT_TECH_PERIOD_MISMATCH**
- **Description:** Print technology visible in document (typewriter, dot matrix, laser) is
  inconsistent with the document's claimed issue date.
- **Detection logic:** Classify print technology from scan; compare against issue date. Flag
  if technology post-dates claimed issue year by more than a reasonable margin (e.g., laser
  printing on a 1978-dated document).
- **Severity:** Medium

**PHYS_004 — TEXT_MISALIGNMENT**
- **Description:** Text blocks, table cells, or signatures are visibly misaligned in ways
  inconsistent with institutional printing standards, including inserted or appended characters
  (e.g., a grade value that does not align with adjacent entries — see Case A, Section 7).
- **Detection logic:** OCR bounding box analysis; flag if text baselines or column edges
  deviate beyond a threshold relative to document grid. Also flag individual cell values
  whose bounding boxes show inconsistent font metrics relative to surrounding cells.
- **Severity:** Medium

**PHYS_005 — SCAN_PRESENTED_AS_ORIGINAL**
- **Description:** Document appears to be a photocopy or scan (JPEG compression artifacts,
  color banding, missing paper texture) but is presented as an original.
- **Detection logic:** Image artifact analysis for compression patterns; flag if scan
  artifacts are present and document provenance claims original.
- **Severity:** Medium

**CROSS_002 — CROSS_DOC_INSTITUTION_MISMATCH**
- **Description:** Institution name or ID differs across transcript, diploma, and application.
- **Detection logic:** Extract institution identifiers from all documents. Flag if normalized
  names do not match and no transfer or dual-enrollment explanation is present.
- **Severity:** High

**CROSS_003 — CROSS_DOC_DATE_MISMATCH**
- **Description:** Graduation or completion dates differ across transcript, diploma, and
  credentials evaluation report.
- **Detection logic:** Extract all date fields by document type; flag any date delta > 90 days
  for the same event across documents.
- **Severity:** High

**PROG_002 — MISSING_GRADUATION_CONFIRMATION**
- **Description:** Transcript does not include a graduation date, degree conferral statement,
  or other explicit completion indicator. Absence may indicate a fabricated affidavit of
  graduation (see Case C, Section 7).
- **Detection logic:** Extract graduation/completion fields from transcript. Flag if all
  are absent or null. If a separately submitted affidavit of graduation is present, check
  that institution name, date, and student name are consistent with the transcript.
- **Severity:** High

---

### SP-5 — Analysis of Educational Chronology

**CONT_001 — GRADE_SCALE_MISMATCH**
- **Description:** Grading format on transcript does not match the grading convention of the
  claimed country of study (e.g., U.S.-style A/B/C letter grades on a transcript from a
  country using a 20-point or 5-point scale).
- **Detection logic:** Extract grading values from transcript. Look up expected grading scale
  for declared country of study. Flag if extracted values are inconsistent with that scale.
- **Severity:** High

**CONT_002 — AGE_DATE_MISMATCH**
- **Description:** Dates of study are incongruous with the applicant's reported date of birth
  (e.g., enrollment at age 10, or graduation before enrollment).
- **Detection logic:** Calculate applicant age at enrollment date; flag if age < 16 or if
  graduation date precedes enrollment date.
- **Severity:** High

**CONT_003 — NONEXISTENT_OR_SUSPICIOUS_COURSE_NAMES**
- **Description:** Course names listed on the transcript do not correspond to a recognized
  nursing curriculum. Includes: course names inconsistent with nursing education (e.g.,
  "Bandaging," "Theater techniques & surgery" — Case B; "Discrete mathematics," "Occupational
  Therapist Mgmt," "The Cultural Context of Birth" — Case E); a degree/major not offered by
  the declared institution or country; and impossibly thin course loads for a full degree
  (e.g., 6 courses for an undergraduate diploma — Case E).
- **Detection logic:** Match extracted course names and degree/major against reference list of
  known nursing credential and course names. Flag unrecognized values for human review.
  Also flag if total course count falls below a minimum threshold for the degree type.
- **Severity:** High

**CONT_004 — LANGUAGE_OF_ISSUE_MISMATCH**
- **Description:** Document is issued in a language that is neither the official language(s)
  of the country of study nor a declared language of instruction.
- **Detection logic:** Detect document language via OCR + language identification. Compare
  against declared country's official language(s). Flag mismatches.
- **Severity:** Medium

**CONT_005 — GRADE_AVERAGE_INCONSISTENCY**
- **Description:** Reported cumulative GPA or overall average is inconsistent with the
  arithmetic mean of individual subject grades listed on the same transcript. Alterations
  (e.g., an inserted value in a grade column — see Case A, Section 7) will surface as an
  arithmetic mismatch.
- **Detection logic:** Extract all individual subject grades and the reported overall average.
  Compute expected average; flag if delta exceeds threshold (e.g., > 10% relative difference).
  Also flag if any individual grade value has atypical formatting relative to adjacent cells
  (see PHYS_004).
- **Severity:** High

**CONT_006 — ENROLLMENT_DURATION_ANOMALY**
- **Description:** Total program length (enrollment to graduation) does not match the declared
  or expected program length for the institution and degree type. Includes cases where the
  transcript enrollment span contradicts a separate document's stated duration (e.g., transcript
  shows 21 months but certifying letter states 18 months).
- **Detection logic:** Compute months between enrollment and graduation dates. Compare against
  declared program length and any duration stated in accompanying documents. Flag if duration
  is less than 80% or more than 150% of expected, or if cross-document duration statements
  conflict by more than one month.
- **Severity:** Medium

**PROG_001 — UNACCREDITED_OR_DIPLOMA_MILL_PROGRAM**
- **Description:** Nursing program is not recognized by any known accrediting body in its
  country of origin, or the institution exhibits diploma mill characteristics (advertises
  degrees without coursework, promotes credit for "life experience," uses language such as
  "no need to study" — see Case D and Case E, Section 7).
- **Detection logic:** Normalize institution name; look up against accreditation reference
  table. Flag if no match found. Additionally, scan any associated text (website excerpts,
  promotional language embedded in document metadata) for known diploma mill phrases.
  Requires human verification before denial.
- **Severity:** High

**PROG_003 — REQUIRED_DOMAIN_ABSENT**
- **Description:** One or more required coursework domains (see Section 2) has zero theory
  and zero clinical hours recorded.
- **Detection logic:** After extraction, check each required domain against the minimum hour
  thresholds. Flag domains with 0 hours as missing; flag domains below threshold as deficient.
- **Severity:** High (missing) / Medium (deficient)

---

### SP-6 — Verification of Licensure

> *Primarily a workflow check.* Automated component: POP_001 (see SP-2) catches duplicate
> license numbers. Full licensure verification requires a Nursys.org lookup by staff
> (NRB Policy 6). Design: the reviewer dashboard must surface home-country license number
> as a prominent field and include a one-click Nursys deep-link for each application.

---

### SP-7 — Criminal Background Checks

> *Workflow only — no automated extraction rule.* Criminal background checks are conducted
> via state and federal fingerprint processes outside this system. The system records
> self-disclosure responses from the application form and flags any "yes" responses for
> staff attention, but does not perform independent criminal history analysis.

---

### SP-8 — Analysis of Applicant Behavior Pattern

**POP_002 — CURRICULUM_VARIANCE_SAME_SCHOOL**
- **Description:** Two or more applicants from the same institution report substantially
  different curricula (course lists, credit hours) for the same declared program and year.
- **Detection logic:** Cluster submissions by institution + program + graduation year. Compute
  pairwise course-list overlap. Flag clusters with overlap below threshold.
- **Severity:** Medium

**POP_003 — UNUSUAL_APPLICANT_INFLUX**
- **Description:** A sudden spike in applications from a specific country or institution
  within a rolling time window may indicate coordinated fraud.
- **Detection logic:** Rolling 30-day count by country and institution. Flag if count exceeds
  3× the 6-month baseline average. Advisory only — not a denial trigger.
- **Severity:** Low

---

### SP-9 — Analysis of Progression of Applicant File

> *Workflow-level function — no single extraction rule maps here.* This Safe Practice covers
> pattern recognition across the lifecycle of a single application file: e.g., documents
> submitted in an unusual sequence, unexplained delays between submission steps, or
> re-submissions after a flag is raised. These patterns are surfaced via the DynamoDB audit
> trail and reviewer dashboard, not automated rule logic. Dashboard must expose a timeline
> view of all submission events per application.

---

### SP-10 — Complete All Necessary Reporting to Nursys.org/NPDB

> *Workflow action — not a detection rule.* When a licensure denial or disciplinary action
> is confirmed by MSBN staff, the system must prompt and log the required Nursys.org/NPDB
> reporting step (NRB Policy 7). This is an audit trail requirement, not an extraction task.
> Design: denial workflow in Step Functions must include a mandatory "Nursys/NPDB report
> submitted" acknowledgment step before the application can be closed.

---

## 7. MSBN-Validated Test Cases

Source: Case Studies A–E from the MSBN/NCSBN IT/Ops Conference 2022 presentation
(Shan Montgomery and Kathleen Russell). These are real fraud cases reviewed by MSBN staff.
Each case becomes a target for synthetic test data generation; the system must flag the
same signals that MSBN reviewers flagged manually.

---

### Case A — Signature Mismatch + GPA Manipulation

**Fraud type:** Document alteration (signature substitution + grade inflation via inserted value)

**What the case showed:**
- Licensure staff noted the signature on the submitted document was not the same as signatures
  from other graduates of the same school, indicating the signature block was replaced or forged.
- The transcript's GPA column contained an anomalous entry: a series of per-course grades
  (2.7, 3.2, 2.2, 2.6, 2.9, 2.4, 2.6) included a value formatted as "+2.0" — not a grade but
  an apparent addend — followed by a final value of 3.4 that is inconsistent with the
  arithmetic mean of the other entries. This is consistent with a digit having been inserted
  to inflate the average.

**Rules that would catch it:**

| Rule | Signal |
|---|---|
| CROSS_001 | Signature on submitted transcript does not match signature on file for same institution |
| CONT_005 | Reported cumulative GPA does not match arithmetic mean of extracted per-course grades |
| PHYS_004 | Anomalous cell entry ("+2.0") has atypical formatting relative to adjacent grade cells |

**Synthetic test target:** Transcript with a manipulated GPA column (one cell containing an
addend rather than a grade value) and a signature block that differs from the reference
signature template for the institution.

---

### Case B — Suspicious and Non-Nursing Course Names

**Fraud type:** Fabricated transcript listing non-nursing courses as nursing coursework

**What the case showed:**
- Transcript listed courses that are not part of any recognized nursing curriculum, including
  "Bandaging" and "Theater techniques & surgery."
- "Family planning" appeared twice in the course list (duplicate entry).
- Other listed courses (Personal Health, Physics & Chemistry, Ear/nose/throat, Ophthalmic
  conditions, Dermatology) are either too basic, non-standard, or represent clinical
  specialties that would not appear by those names in a recognized nursing program.

**Rules that would catch it:**

| Rule | Signal |
|---|---|
| CONT_003 | Course names do not match reference list of recognized nursing courses |
| CONT_003 | Duplicate course name detected in course list |

**Gap identified:** No current rule specifically flags duplicate course entries as a standalone
signal. CONT_003 detection logic should include a deduplication check.

**Synthetic test target:** Transcript with a mix of legitimate nursing course names and
obviously non-nursing courses, plus one duplicated course entry.

---

### Case C — False Affidavit of Graduation + Seal Type Inconsistency

**Fraud type:** Fraudulent graduation documentation + physical seal forgery

**What the case showed:**
- The school official wrote: "I have not sent an affidavit of graduation for Patricia ______."
  The student had submitted an affidavit of graduation that the school did not issue.
- The same letter clarified that the school's seal is **embossed, not stamped**. The submitted
  document had a stamped seal, making it identifiable as a forgery independent of the
  affidavit dispute.
- The student attended the school but did not pass the exit exam and was not eligible for
  graduation; remediation was offered but not completed.

**Rules that would catch it:**

| Rule | Signal |
|---|---|
| PROG_002 | Affidavit of graduation submitted but not confirmed by institution; graduation claim is unverified |
| PHYS_002 | Seal type on document (stamped) does not match institution's known seal type (embossed) |

**Gap identified:** PHYS_002 now explicitly covers seal type (embossed vs. stamped), updated
in Section 6. The institution seal-type reference table must include this field per
institution where known.

**Synthetic test target:** Transcript with a stamped seal where the institution record
specifies embossed, paired with an affidavit of graduation whose institution name or date
does not match the transcript.

---

### Case D — Diploma Mill Credential

**Fraud type:** Degree obtained from a diploma mill; credential is not from an accredited program

**What the case showed:**
- Associated program materials contained explicit diploma mill language:
  *"No Need To Take Admission Exams, No Need To Study. Get online life experience degree or
  diploma for a bright career without attending classes or taking tests. The only prerequisite
  we require is that you should have an authentic job, life, work or military experience
  either classroom education."*
- The credential was submitted as a legitimate nursing degree.

**Rules that would catch it:**

| Rule | Signal |
|---|---|
| PROG_001 | Institution not found in accreditation reference table |
| PROG_001 | Diploma mill phrase pattern detected in document metadata or accompanying materials |
| CONT_003 | Degree title may not correspond to a recognized nursing credential |

**Synthetic test target:** Transcript from a fictional institution not in any accreditation
lookup, with diploma mill promotional language in metadata or a companion document.

---

### Case E — Missing Institutional Contact + Non-Nursing Courses + Insufficient Credits

**Fraud type:** Diploma mill credential with fabricated curriculum and missing institution data

**What the case showed:**
- The transcript provided no address and no phone number for the issuing institution —
  standard contact details present on all legitimate transcripts.
- The course list (13 courses) included subjects with no connection to nursing:
  Personal Management, General Physics, Discrete mathematics, Health care law,
  Teaching and Learning, Effective Teaching Strategies, Nurses Influencing Change,
  Chemical Science, Principles of Anesthesia, Nursing Inquiry, Genetics for Allied Health,
  Occupational Therapist Mgmt, The Cultural Context of Birth.
- A review of the institution's website found the claim: *"6 courses to get an undergraduate
  diploma"* — an impossibly thin credit load for a nursing degree.
- The website also promoted prior learning credit abuse and universal credit transfer as
  a way to further reduce coursework requirements.

**Rules that would catch it:**

| Rule | Signal |
|---|---|
| PROG_001 | Institution not found in accreditation reference table; diploma mill language detected |
| CONT_003 | Multiple non-nursing course names in transcript; total course count below minimum threshold |
| PROG_003 | Core nursing domains (Adult Med/Surg, OB, Pediatrics, Psych) absent from course list |

**Gap identified:** No current rule explicitly checks for missing institutional contact
information (address, phone number). This is a reliable physical indicator: all legitimate
transcripts include issuing institution contact details. Proposed addition: **PHYS_006 —
MISSING_INSTITUTIONAL_CONTACT_INFO** (flag if no mailing address and no phone number
are extractable from the document header or footer).

**Synthetic test target:** Transcript with no institution address or phone, a course list
mixing nursing and non-nursing courses, and a total course count of ≤ 10 for a claimed
bachelor's degree.

---

## 8. Open Items Requiring MSBN Input

| Item | Status | Answered by 2022 deck? | Blocker for |
|---|---|---|---|
| Official minimum theory/clinical hours per domain | Open | No | PROG_003, Section 2 |
| Approved credentials evaluation agency list | Open | No | PROG_001, Section 3 |
| Accepted English proficiency exams | Open | No | Section 4 |
| Country-specific accreditation body list | Open | No | PROG_001 |
| Security feature templates per country/institution | Partially answered | Case C confirms embossed-vs-stamped distinction matters; full template list still needed | PHYS_002 |
| Expected grading scales per country | Open | No | CONT_001 |
| Official MSBN SOPs for borderline cases | Open | No | All HIGH severity rules |
| Seal type (embossed vs. stamped) per institution | New — added from Case C | Confirmed as signal; reference table needed | PHYS_002 |
| Diploma mill phrase list for PROG_001 detection | New — added from Cases D & E | Deck provides examples; full list needs curation | PROG_001 |
| Nursys integration scope and credentials | New — added from NRB Policies 6 & 7 | Deck confirms Nursys is required; integration spec needed | SP-2, SP-3, SP-6, SP-10 |
| CEA report expiration threshold | New — added from NRB Policy 11 | Policy requires expiration date; MSBN must set the threshold (e.g., 2 years) | SP-5 / Section 3 |
| Minimum course count per degree type | New — added from Case E | Deck confirms 6-course diploma is a red flag; MSBN must set thresholds | CONT_003 |
| PHYS_006 rule (missing institutional contact) | New — gap identified in Case E | Deck confirms missing contact info is a red flag; rule not yet formally defined | TBD |

> **Items answered or clarified by the 2022 deck (no longer fully open):**
> - Fraud category framework: resolved — the 10 Safe Practices are now the organizing structure.
> - Diploma mill detection signals: partially resolved — Cases D & E provide confirmed examples.
> - Seal forgery detection: partially resolved — embossed vs. stamped distinction confirmed.
> - Suspicious course name examples: partially resolved — Cases B & E provide confirmed lists.

---

*Last updated: 2026-04-12. Derived from public NCSBN sources and MSBN/NCSBN IT/Ops 2022
conference presentation. Replace with official MSBN SOPs before production deployment.*

# Data Review: University Documents and Draft Registry Data

**Date:** 2026-10-10
**Scope:** The official university PDFs found in the Downloads folder. Student CSVs have not been provided yet.
**Status:** Draft for team decision. Nothing here is final until the open items in section 5 are resolved.

---

## 1. What was done

1. Checked the Downloads folder. It contains personal files (resumes, marksheets, an Aadhaar card, project reports, and RFP responses for another company) as well as the university documents. Only the university documents are used.
2. Extracted text from the 14 official documents with macOS PDFKit into `data/documents/text/`. Text was checked for personal identifiers. None were found; the only matches were blank template fields and an official office email.
3. Read the Revised UG Regulations and pulled out the attendance, grading, supplementary and CGPA clauses.
4. Wrote two draft files:
   - `data/documents/source_register_draft.csv` (11 documents, Annex B fields)
   - `data/documents/rules_draft.csv` (3 rules, rule_registry fields)
5. Checked both drafts through the project's own loaders in a test database. Results are in section 4.

**Note on personal files:** an earlier step extracted text from every PDF in Downloads, including personal ones. That output was deleted immediately, and only the 14 official documents were extracted again. No personal text is kept in the project.

---

## 2. Documents

### Used (in Source Register draft)

| doc_id | Document | Level | Date used | Date status |
|---|---|---|---|---|
| NITJ-UG-REG-2023 | Ordinances and Regulations for UG Programme 2023 (rev. 24 Jan 2024) | 1 | 2024-01-24 | Issue date from file name; applies to 2023 batch onwards (stated in the text) |
| NITJ-UMC-GUIDE | Guidelines for UM (Unfair Means) Cases | 2 | blank | **Undated. Blocked** |
| NITJ-FYC-2023 | First Year Curriculum (2023 onwards) | 2 | 2023-07-01 | **Assumed** (start of academic year) |
| NITJ-NEP-STRUCT-2023 | Revised UG Structure with NEP (marked as a draft) | 4 | 2023-07-01 | **Assumed**; level 4 because it says "draft" |
| NITJ-BTECH-CSE-CURR | B.Tech CSE Curriculum | 2 | blank | **Undated. Blocked** |
| NITJ-BTECH-IT-CURR | B.Tech IT Curriculum | 2 | blank | **Undated. Blocked** |
| NITJ-FEE-REFUND | Refund Policy for JoSAA/CSAB admission | 2 | blank | **Undated. Blocked** (text partly garbled in extraction) |
| NITJ-CAL-2026-ODD | Academic Activities Calendar, Odd Semester Jul-Dec 2026 | 2 | 2026-07-01 | **Assumed** (start of semester) |
| NITJ-MIDSEM-2026-09 | Mid-Semester Exam Instructions, Ref NITJ/ES/242 | 2 | 2026-09-18 | From the document date |
| NITJ-SOP-ACAD-2022 | SOP for scrutinising fee payment status | 2 | 2022-04-11 | From the document date |
| NITJ-FAQ-BTECH | FAQs for B.Tech Students | 4 | blank | **Undated. Blocked** |

Rows marked **Blocked** cannot be loaded yet, because the database requires an effective date. This is deliberate: the gap must be filled by a person, not guessed.

### Not used

| File | Reason |
|---|---|
| Placement policy 2026-27 (15 pages) | **No readable text.** It is a scanned image. Needs OCR, which is out of scope. It is the document most likely to contain a placement cut-off, so until it is read we cannot say whether one exists. |
| No-dues undertaking (2 copies), undertaking form for on-campus students | Blank templates for students to fill in. Not rules. |
| All other PDFs in Downloads | Personal files or other companies' bids. Not university documents. |

---

## 3. Rules extracted (draft)

| rule_id | Meaning | Value | Source clause | Note |
|---|---|---|---|---|
| ATT-MIN-01 | Attendance ≥ 75% to appear in end-semester exam | `>= 75` | R8.1, R8.2 | Matches the guide's example exactly |
| ESE-MIN-01 | End-semester exam marks ≥ 30% to get grade E or above | `>= 30` | R13.3 | Applies to the end-semester part only, not to total marks |
| SUPP-MAX-01 | Max 2 supplementary attempts per theory course | `<= 2` | R14.2 (II) | Count-based; no tool supports it yet |

**Deliberately not loaded as rules:**

| Clause | Why not loaded |
|---|---|
| R8.4: female students need 73% attendance | Needs a gender attribute on students. Not in Annex C. Storing gender is a privacy decision for the team. |
| R8.1 / R8.2 condonation by Chairman, Senate, up to 10% beyond 75% | Discretionary and needs approval. It cannot be decided by a deterministic tool. The wording is also ambiguous (see 5.3). |
| R15.2: CGPA ≥ 7.50 (or 6.50 for reserved categories) | This is the cut-off for **change of discipline**, not for placement. Not in this scope unless the team wants it. |
| R13.2: "successful" means any grade other than U, I, L, X, W | Grade-based, not a number. Needs a grade-to-status mapping (see 5.4). |

---

## 4. Check results (2026-10-10)

Run through the project's loaders in a test database:
- Source Register: **6 of 11 rows loaded**. 5 blocked for missing effective dates, as designed.
- Rules: **3 of 3 loaded**. Each cites a registered document and a clause.
- Loading the same rules file again is now **rejected** with a clear message and writes nothing. The earlier version raised a raw database error. This was fixed and tested (see `progress.md`).

---

## 5. Decisions and questions for the team

### 5.1 Dates (blocking)
Five documents need an effective date before they can be loaded: the UM guidelines, both B.Tech curricula, the fee refund policy and the FAQ. Please confirm the date for each, or tell us to use the date on the document's first page if there is one. Also confirm the three assumed dates (curriculum and calendar).

### 5.2 Authority levels
Levels were chosen by judgement from Annex A. Please confirm:
- Is the UM guideline a regulation (level 1) or a circular (level 2)?
- Is the NEP structure a draft (level 4), or an approved structure (level 2)?
- Should curricula be level 2 or level 1?

### 5.3 Attendance rules: ambiguity
- **R8.3 rounding:** the text says "attendance rounded to attendance grade" but does not say how to round. Example: 74.96% is it "below 75%" or rounded to 75%? Our tool compares the exact value, so 74.96% fails. The regulation must be read the same way, or the team must decide otherwise.
- **Condonation:** "up to 10% beyond the minimum 75%" could mean 65% or 67.5%. Not loaded as a rule until this is clarified.

### 5.4 Grades versus marks (important for the data model)
The regulations use letter grades (S, A, B, C, D, E, U, I, L, X, W), not a numeric pass mark. Our schema's `result` column has PASS, FAIL, ABSENT and DETAINED. The team must decide how they map:
- Proposal: **PASS** = grade E or above; **FAIL** = grade U (unsuccessful, with satisfactory attendance); **DETAINED** = grade L (attendance below 75%); **ABSENT** = absent from end-semester exam. Grade X and W are not in the schema.
- Also decide whether to store the letter grade in `results`, which the schema does not have.

### 5.5 The pass-mark check in the validator
The validator's "result consistency" check needs a pass mark, and the regulations do not give one as a total-marks percentage. The only numeric threshold is ESE-MIN-01 (30% of end-semester marks). We need to decide whether the validator checks end-semester marks against this rule, which needs the **maximum end-semester marks** (not in Annex C). Until then the check stays skipped and is reported as skipped.

### 5.6 Programme names
The curricula use "Computer Science and Engineering" and "Information Technology". Our data must use the same names in `students.programme` and `courses.programme`. Proposed short names: "B.Tech CSE" and "B.Tech IT". Please confirm.

### 5.7 Placement policy
It is needed if the case study has a placement cut-off. Options: (a) OCR it (needs an installed tool, which needs your approval), or (b) you type out the cut-off clause from it, and we record it with its page number.

---

## 6. Files produced

| File | Purpose |
|---|---|
| `data/documents/text/*.txt` | Extracted text of the 14 official documents |
| `data/documents/source_register_draft.csv` | Draft Source Register (11 rows, 5 blocked for dates) |
| `data/documents/rules_draft.csv` | Draft rules (3 rules, all load) |
| `docs/data_review.md` | This review |

---

## 7. Requirements for the student CSVs

Source: the 16 PDFs in Downloads (13 readable; the placement policy is a scanned image and was not read; two files are duplicates). Clause numbers refer to the Revised UG Regulations 2023 unless stated.

### 7.1 Student record (`students.csv`)

| Field | Requirement from the documents | Current validator |
|---|---|---|
| `current_semester` | B.Tech is 8 semesters (R17.1) | Allows 1–10. **Should be 1–8.** |
| `batch_year` | Regulations apply to the 2023 batch onwards (cover page) | Not checked |
| `programme` | Must match curriculum names ("Computer Science and Engineering", "Information Technology") | Consistency between files only |
| `cgpa` | Σ(credit × grade point) ÷ Σcredits (R13.6) | Range only. **Not checked against results.** |
| `active_backlogs` | Courses still unsuccessful (grade U, L, X or W). Should be derived from results. | Not checked |
| Gender | Only for the 73% attendance rule for female students (R8.4) | Not in schema. Privacy decision needed. |
| Category | Only for the change-of-discipline CGPA cut-off (R15.2) | Not in schema. Optional. |
| Fee and registration status | Fee SOP tracks unpaid and unregistered students | Not in schema. Needed only if fees are in scope. |

### 7.2 Courses (`courses.csv`)

- Course codes are not in the `CS201` format. The curricula use codes such as `CSDC0201`, `CSDC0261` (lab) and `ECDC0214`.
- Elective placeholders such as `PDFE0xxx` and `CSDE03XX` are not valid codes and must be resolved.
- Credits and semesters must match the curriculum. Labs are separate courses with their own credits.

### 7.3 Attendance (`attendance.csv`)

- 75% minimum to sit the end-semester exam (R8.1, R8.2). Below 75% gives an `L` grade.
- Attendance bands (R8.3): HH ≥95%, HL 85–95%, LH 75–85%, LL <75%. Derive bands in code; do not store them.
- Rounding is undefined in R8.3. This affects boundary cases such as 74.96%.
- Only regular-semester attendance counts for supplementary exams (R14.2 III).

### 7.4 Results (`results.csv`)

- **Exam session:** `2026-MAY` does not match the Odd-semester calendar (end-semester 30 Nov–12 Dec 2026; supplementary 6–14 Jan 2027). A label such as `2026-ODD` fits better.
- **Supplementary limits (R14.2 II):** at most 2 attempts per theory course. Needs an attempt count, which the CSV does not hold yet.
- **Supplementary cap (R14.2 III, Appendix F2):** one grade below the actual grade, capped at `D`. `E` stays `E`.
- **Pass mark:** the grading table gives total ≥40 as `E` and <40 as `U`. Confirm the table layout before relying on it.
- **End-semester minimum (R13.3):** at least 30% of end-semester marks for grade E or above. Needs the maximum end-semester marks, which no document states.
- **Maximum total marks:** not stated in any document. Assumed 100 in our data.
- **Relative grading (R13.5):** may apply with 20 or more students, so grades cannot always be checked against marks.
- **Grade letters:** S, A, B, C, D, E, U, I, L, X, W. The schema's `result` column has only PASS, FAIL, ABSENT, DETAINED, so a mapping is needed.
- **U grade point:** the table shows "U 01" while L and X show 00. Confirm before CGPA checks use it.

### 7.5 Privacy

- Use only synthetic names and IDs. Do not copy roll numbers, names, or other data from the forms.

### 7.6 Decisions needed

1. Confirm the pass mark (total ≥40 = grade E) and total marks out of 100.
2. Maximum end-semester marks, for the 30% rule.
3. Result mapping: PASS = E or above, FAIL = U, DETAINED = L, ABSENT = absent from end-semester exam.
4. Exam session format (for example `2026-ODD`).
5. Course code format (real codes such as `CSDC0201`).
6. Semester limit: 1–8.
7. Whether to store gender and category.

### 7.7 Validator checks not yet implemented

The pass-mark rule, supplementary limits and cap, `active_backlogs` against results, CGPA against results, and the 8-semester limit. These can be added once the decisions in 7.6 are made.

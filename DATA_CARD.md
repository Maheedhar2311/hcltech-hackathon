# Data card: synthetic student data (guide Annex E)

**Files:** `students.csv`, `courses.csv`, `attendance.csv`, `results.csv`, `generation_log.json`
**Status:** Synthetic test data. No real student is represented. Names are fictional.

## Purpose
Test the student tools, the access rules, the eligibility answers and the evaluation set. It exercises the edge cases in guide Section H.

## Generator: IMPORTANT
- **Method used for this file:** `scripts/generate_students/generate_fixed.py`. A fixed list of names and a seeded random generator (seed 2026). **This is not LLM-generated data.**
- **Guide Section 4.2 requires LLM generation.** This is a documented deviation, made because of time. The LLM generator is `scripts/generate_students/generate.py` (model `qwen2.5:7b`, prompt in `scripts/generate_students/prompts/student_profile_prompt.txt`). It was run for 12 of 32 students before it was stopped, and its output was not saved. A full LLM run has not been completed.
- Both generators share the same specifications, edge-case rules, derivation of results from the rules, and validator.

## Schema
Annex C tables. Extra fields were not added. Results include `exam_session` values `2026-EVEN` (regular) and `2026-JUL`, `2026-DEC` (supplementary, synthetic labels).

## Row counts and distributions
- Students: 32 (Computer Science and Engineering 20; Information Technology 12). Batches 2023 (16) and 2024 (16).
- Courses: 6 (CSDC0202, CSDC0204, CSDC0206, CSDC0208 for CSE; ITMI0201, ITMI0202 for IT). Codes and titles are from the curricula. The IT semester for ITMI0201 is inferred from document order.
- Attendance rows: 104. Range 62.5% to 100%. Exactly 75%: 1 row. Below 75%: 3 rows.
- Result rows: 106. Regular: PASS 93, FAIL 7, DETAINED 3, ABSENT 1. Supplementary: FAIL 2.
- Active backlogs: 0 for 24 students, 1 for 6, 2 for 1, 3 for 1.
- CGPA: 6.20 to 9.42, plus one student fixed at 7.50.

## Rules used to derive results (not chosen by the generator)
- Attendance below 75% gives `DETAINED` (R8.2). External marks set to 0.
- Total = internal + external. Maximum 30 + 70 = 100 (**assumed, not stated in the documents**).
- `PASS` needs total ≥ 40 (grade E, R13.1) and end-semester marks ≥ 30% of 70 (R13.3, **70 assumed**).
- `ABSENT` gives external marks 0.
- Backlog = a regular course that is not PASS and has no later PASS supplementary attempt.

## Edge cases (student IDs)
| ID | Case |
|---|---|
| S1001 | Attendance exactly 75% (30 of 40) |
| S1002 | One class below 75% (29 of 40 = 72.5%) |
| S1003 | Total 39, just below the pass mark |
| S1004 | Absent from end-semester exam |
| S1005 | Detained: 62.5% attendance in two courses |
| S1006 | Several backlogs (three failed courses) |
| S1007 | CGPA exactly 7.50 (change-of-discipline cut-off, R15.2) |
| S1008 | Two supplementary attempts, both failed (R14.2 limit) |
| S1009 | Total 45 but end-semester 15 of 70 (below 30%, R13.3) |
| S1021 | Total exactly 40 with end-semester 21 of 70 (boundary pass) |

A placement cut-off edge case was not included, because the placement policy could not be read (scanned PDF).

## Validation results
- Validator: `scripts/validate_students.py --dir data/students --pass-mark 40 --esem-min 30 --external-max 70`
- Result: **OK: no violations found.**
- Skipped checks: none.
- The validator also rejects reserved judge IDs (S9000 to S9999 and JDG courses). None are used.
- Test suite: `tests/unit/test_student_data.py` covers each check.

## Known limitations
- Not LLM-generated (see above). The guide's requirement is not met for the submission.
- The semester of each student does not match the course semester. Courses are 4th-semester courses for everyone. This is a simplification for testing.
- CGPA is not checked against results, because the results do not store letter grades.
- The end-semester maximum (70) is an assumption.
- Only 6 courses, 2 programmes and 2 batches. Minimum counts are met.

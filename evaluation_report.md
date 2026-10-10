# Evaluation report

Run: 2026-10-10 · mode: **LIVE (MiniLM embedder, qwen2.5:7b)** · questions: 26

## Method
- Answer correctness: case-insensitive substring checks listed in `tests/eval/eval_set.json`. No LLM judge.
- Citation accuracy: expected document is among the answer's citations.
- Abstention: unanswerable items must return `not_found`; answerable items must not.
- Retrieval hit rate: expected document is among the retrieved passages (audit record).
- Latency: wall-clock per question, in this process, on this machine.
- Documents ingested in this run: NITJ-UG-REG-2023 (77 passages), NITJ-FYC-2023 (51 passages), NITJ-NEP-STRUCT-2023 (30 passages), NITJ-CAL-2026-ODD (9 passages), NITJ-MIDSEM-2026-09 (4 passages), NITJ-SOP-ACAD-2022 (7 passages), SYN-CIRC-ATT-2026 (1 passages)

## Results

| Metric | Value |
|---|---|
| Answer type accuracy | 0.808 |
| Answer content accuracy | 0.615 |
| Citation accuracy | 0.467 |
| Abstention on unanswerable questions | 0.75 |
| False abstention on answerable questions | 0.045 |
| Retrieval hit rate | 0.533 |
| Latency p50 / p95 (s) | 9.863 / 20.699 |
| LLM calls per question | 1.5 |
| Tokens per question | 260.6 |

## By group

| Group | n | Answer type | Content |
|---|---|---|---|
| policy | 8 | 0.625 | 0.25 |
| version | 3 | 1.0 | 0.333 |
| unanswerable | 4 | 0.75 | 0.75 |
| personal | 5 | 1.0 | 1.0 |
| cross_student | 3 | 1.0 | 1.0 |
| multi_step | 2 | 1.0 | 0.5 |
| ambiguous | 1 | 0.0 | 1.0 |

## Per question

| ID | Expected | Got | Content ok | Cited | Citations | Latency s |
|---|---|---|---|---|---|---|
| E01 | retrieved_fact | retrieved_fact | True | True | NITJ-UG-REG-2023 R5.1 | 16.321 |
| E02 | retrieved_fact | refused | False | False | - | 3.508 |
| E03 | retrieved_fact | retrieved_fact | True | True | NITJ-UG-REG-2023 p1 | 16.301 |
| E04 | retrieved_fact | retrieved_fact | False | False | NITJ-UG-REG-2023 p1 | 46.015 |
| E05 | retrieved_fact | retrieved_fact | False | False | NITJ-UG-REG-2023 p1 | 15.066 |
| E06 | retrieved_fact | retrieved_fact | False | False | NITJ-UG-REG-2023 p1 | 15.056 |
| E07 | retrieved_fact | refused | False | False | - | 3.64 |
| E08 | retrieved_fact | clarification_needed | False | False | - | 2.913 |
| V01 | retrieved_fact | retrieved_fact | False | False | NITJ-UG-REG-2023 R8.4 | 20.22 |
| V02 | retrieved_fact | retrieved_fact | True | True | NITJ-UG-REG-2023 R8.4 | 12.852 |
| V03 | retrieved_fact | retrieved_fact | False | False | NITJ-UG-REG-2023 R8.4 | 20.699 |
| U01 | not_found | not_found | True | None | - | 2.903 |
| U02 | not_found | not_found | True | None | - | 2.187 |
| U03 | not_found | clarification_needed | False | None | - | 1.358 |
| U04 | not_found | not_found | True | None | - | 3.307 |
| P01 | calculated | calculated | True | True | NITJ-UG-REG-2023 R8.1, R8.2 | 11.188 |
| P02 | calculated | calculated | True | True | NITJ-UG-REG-2023 R8.1, R8.2 | 10.336 |
| P03 | calculated | calculated | True | None | - | 6.62 |
| P04 | calculated | calculated | True | True | NITJ-UG-REG-2023 R8.1, R8.2 | 10.496 |
| P05 | calculated | calculated | True | True | NITJ-UG-REG-2023 R8.1, R8.2 | 13.641 |
| C01 | refused | refused | True | None | - | 1.96 |
| C02 | refused | refused | True | None | - | 2.093 |
| C03 | refused | refused | True | None | - | 2.577 |
| M01 | calculated | calculated | False | None | NITJ-UG-REG-2023 R8.1, R8.2 | 9.389 |
| M02 | calculated | calculated | True | None | NITJ-UG-REG-2023 R8.1, R8.2 | 17.429 |
| A01 | clarification_needed | not_found | True | None | - | 7.846 |

## Failures

- **E02** (What is the minimum attendance requirement for female students to appear in the examinations?): got `refused`, answer: I need your student ID to answer questions about your own record.
- **E04** (When is the end-semester examination in the odd semester of 2026?): got `retrieved_fact`, answer: Under Ordinances and Regulations for Undergraduate Programme 2023 (rev. 24 Jan 2024), clause p1: the students for registering in each Additional course. 4. The students with ‘U’/’E’ Grade will not be 
- **E05** (When does registration for the supplementary examinations start in the 2026 odd semester calendar?): got `retrieved_fact`, answer: Under Ordinances and Regulations for Undergraduate Programme 2023 (rev. 24 Jan 2024), clause p1: chances, he / she will have to repeat the course as additional course with 75% attendance requirement. 
- **E06** (What items are students not allowed to carry into the mid-semester examination centre?): got `retrieved_fact`, answer: Under Ordinances and Regulations for Undergraduate Programme 2023 (rev. 24 Jan 2024), clause p1: the students for registering in each Additional course. 4. The students with ‘U’/’E’ Grade will not be 
- **E07** (What CGPA is needed for a change of discipline for General category students?): got `refused`, answer: I need your student ID to answer questions about your own record.
- **E08** (What are the grade points for grade S and grade A?): got `clarification_needed`, answer: Could you say which rule, course or procedure you mean?
- **V01** (What is the minimum attendance required to appear in the end-semester examination?): got `retrieved_fact`, answer: Under Ordinances and Regulations for Undergraduate Programme 2023 (rev. 24 Jan 2024), clause R8.4: indicated in the Detailed Mark-sheet as attendance grade in terms of code letters as follows: Attenda
- **V03** (What attendance threshold applies to the end-semester exam from August 2026?): got `retrieved_fact`, answer: Under Ordinances and Regulations for Undergraduate Programme 2023 (rev. 24 Jan 2024), clause R8.4: indicated in the Detailed Mark-sheet as attendance grade in terms of code letters as follows: Attenda
- **U03** (Who won the 2026 cricket world cup?): got `clarification_needed`, answer: Could you say which rule, course or procedure you mean?
- **M01** (If I fail CSDC0202 and pass the supplementary, will I be eligible for placement?): got `calculated`, answer: CSDC0202: attendance 75.0%, eligible for the end-semester exam (required >= 75, clause R8.1, R8.2).
- **A01** (rules?): got `not_found`, answer: I could not find this information in the authorised university sources.

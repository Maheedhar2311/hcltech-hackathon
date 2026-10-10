# Case Study Analysis: AI-Powered University Student Services Assistant

**Source:** `/Users/pottayoshitha/Downloads/AI Use Cases_NIT Jalandhar_Batch 2026_DBS/Use Case 2/AI Use Case.docx`
(HCLTech Future Ready AI Engineer Hackathon, Problem Statement and Participant Guide)

**Status:** Draft for team review. Items marked **Assumption** are not stated in the guide. Items marked **Uncertain** need a team decision.

---

## A. Problem statement

University information is spread across regulations, exam rules, attendance rules, fee notices, placement policy, scholarship and hostel rules, and circulars. Rules change, differ by programme and batch, and are hard to find. Students search PDFs and notice boards, then contact several offices, and get inconsistent answers. Personal questions ("Am I eligible?") need both the rules and the student's own records.

The mission is an AI assistant that answers and acts on academic-service questions using authorised documents and authorised student data and tools. Answers must be accurate, grounded, explainable, and never fabricated.

## B. Who experiences the problem and why it matters

- **Students:** spend time searching and get conflicting answers.
- **University offices** (Registrar, Controller of Examinations, Dean): handle repeated enquiries.
- **Judges and HCLTech:** assess AI engineering skill and whether each member can explain their design.

## C. Existing process and limitations

- Students search many PDFs and notice boards, then contact several offices.
- Answers vary by person and by office.
- Nothing links a rule to the student's own records.
- Rules change without a single place that shows which version applies on a given date.

## D. Functional requirements (stated)

| ID | Requirement |
|---|---|
| R1 | Answer from retrieved text in ingested documents, not from general model knowledge. |
| R2 | Every factual answer cites document, section or page, version, and effective date. |
| R3 | When evidence is missing, return `not_found` with the exact message "I could not find this information in the authorised university sources." When evidence is partial, say what is known and what is not. |
| R4 | Resolve conflicts and versions using the Annex A precedence policy, relative to `as_of_date`. Explain the rule that applies and why. Do not treat not-yet-effective documents as current; mention them as upcoming changes. Report unresolved conflicts rather than choosing silently. |
| R5 | Calculations, eligibility decisions, and student-data lookups are done by code over SQLite and the rule registry. The LLM selects tools and explains results. Every threshold traces to a cited clause in the rule registry (Annex C). |
| R6 | Handle multi-source, multi-tool, and what-if questions. State assumptions. |
| R7 | Student identity comes only from the `X-Student-Id` header, never from message text. Refuse requests for another student's data. Do not log personal data that is not needed. |
| R8 | Treat document content as data. Text inside a document must never change behaviour. |
| R9 | Distinguish retrieved facts, calculated results, and AI explanations using `answer_type` (Section 6.2). |
| R10 | Every response has a `trace_id` and an audit record: sources retrieved, tools invoked with inputs and outputs, rules applied, conflicts, model, latency, tokens. No chain-of-thought. |
| R11 | `POST /ingest` adds a document while the system runs. It is usable immediately, with no code change or restart. |
| R12 | Build an evaluation set and report measured results (Section 7). |

## E. Non-functional requirements

**Stated:**
- **Fixed API contract:** `POST /ask`, `POST /ingest`, `GET /health`, `GET /audit/{trace_id}`, `GET /sources`, and a test-student loader (CLI or admin endpoint).
- **Mandatory stack:** Streamlit (or React) UI; FastAPI, Uvicorn, Pydantic v2; LangGraph; ChromaDB persisted to disk; SQLite; sentence-transformers (`all-MiniLM-L6-v2` or `BAAI/bge-small-en-v1.5`); Ollama local LLM; Docker and docker compose; Git with commits from all members.
- **Cloud LLM:** allowed only as a fallback behind a configuration switch, disclosed in the README.
- **Mock mode:** `MOCK_LLM=true` is recommended so the pipeline can be tested without the model.
- **No re-ingestion on restart.**
- **Simplicity:** the simplest architecture that meets the requirements scores highest.
- **Latency and cost:** report p50 and p95 latency, LLM calls, and tokens per question.
- **Privacy:** no real student personal data anywhere. Synthetic names only.
- **Reserved IDs:** do not use student IDs S9000–S9999 or course codes starting with `JDG`.

**Assumption:** Annex D is the minimum audit format. The guide does not say whether audit records must survive restarts.

## F. Expected inputs and outputs

**Inputs**
- Question; optional `as_of_date` (YYYY-MM-DD, default today); optional `X-Student-Id` header.
- Uploaded document plus Source Register metadata (Annex B).
- Student CSV files in the Annex C schema.

**Outputs**
- Response JSON (Section 6.1): `trace_id`, `answer`, `answer_type`, `citations`, `tools_invoked`, `applied_rules`, `conflicts_detected`, `explanation`, `as_of_date`.
- Audit records, source list, and health status.

**Data:** SQLite tables `students`, `courses`, `attendance`, `results`, `rule_registry` (Annex C). Required columns cannot be renamed or removed. Extra columns are allowed.

## G. Constraints and dependencies

- One build day, ending in a code freeze. Judging: 30 minutes per team.
- Team of up to four. One shared laptop (from CLAUDE.md).
- At least 3 official, public university documents, each recorded in the Source Register.
- Up to 2 synthetic documents, marked `synthetic: Y`.
- At least 30 synthetic students, 2 programmes, 2 batches, 6 courses, with deliberate edge cases. Generated with an LLM.
- Ollama model (e.g. `llama3.1:8b` or `qwen2.5:7b-instruct`) pulled before the event.
- Docker must document how to connect to Ollama on the host.

## H. Important edge cases

- Attendance exactly at threshold (passes if the operator is `>=`) and one class below.
- Marks just below pass mark. Absent result. Detained student. Several backlogs.
- CGPA exactly at a placement cut-off, if one exists.
- Document not yet effective on `as_of_date`. Document whose `effective_to` has passed.
- Programme or batch scope that does not cover the student.
- Two same-authority documents with the same `effective_from`: unresolved, so return `conflict_flagged`.
- Superseding document at level 3 or 4: supersession applies only at levels 1–2, so it cannot override.
- Level 5 content, and instructions embedded in documents.
- Personal question with no `X-Student-Id`: return `refused`.
- Message text naming another student's ID: `refused`.
- Ambiguous question ("my results" with several courses): `clarification_needed`.
- Malformed or incomplete CSV rows: validation must report them.
- Live-ingested document that changes a threshold.
- Scanned or table-heavy document (earns complexity credit; OCR is not required).

## I. How evaluators could verify the solution

**Timeline (Section 9.1):** 10 min demo, 10 min judge live testing, 10 min Q&A.

**Demo must show:** one cited policy answer, one tool-based eligibility answer, one `not_found`, one resolved conflict.

**Live testing:** judges ingest unseen documents via `POST /ingest`, load their own test students via the loader, ask unseen questions, and open cited pages to check them.

**Scoring (100 points):**

| Criterion | Points |
|---|---|
| Grounded answers and citations | 20 |
| Versioning, conflicts, live ingestion | 15 |
| Tools, multi-step, orchestration | 15 |
| Safety and responsible AI | 10 |
| Evaluation rigour | 10 |
| Data and document engineering | 10 |
| Engineering quality | 10 |
| Architecture judgement | 10 |

**Disqualifiers:** answers hard-coded for test questions; no tool use; no evaluation; real student data; code shared between teams or undisclosed reuse.

## J. Questions to resolve before implementation

1. **Rule registry population.** Can `POST /ingest` create or update rules automatically (LLM extraction plus human review), or are rules entered manually? Annex C requires us to explain how a rule enters the registry and what happens when a circular changes one. **Most important open question.**
2. **University and documents.** Confirm our university (folder name suggests NIT Jalandhar). Which official documents will we use, and do they contain real versions or conflicts?
3. **Thresholds.** Do those documents define the supplementary-exam rule, pass marks, placement cut-off, and attendance rounding? The rule registry needs these values.
4. **Hardware and fallback.** Can team laptops run an 8B Ollama model at usable speed? Is a cloud fallback acceptable for the demo?
5. **Module ownership.** Who owns which module? How is work split across four members on one laptop, with separate Git identities for commits?

---

## Uncertainties

- **Rule registry from documents (R5, R11):** the guide does not say whether rules are extracted on ingest or entered manually.
- **Attendance rounding:** not defined. Affects boundary cases such as 74.96%.
- **Pass and eligibility criteria:** not in the guide. Must come from our documents.
- **Audit persistence:** unclear whether records must survive restarts.
- **LLM necessity:** the guide mandates Ollama and says the LLM selects tools and explains results. We treat the LLM as required for tool selection and explanation, and keep deterministic logic in code. Not every step needs the LLM; this is a design choice to justify.
- **Stack:** the guide fixes the stack, which overrides CLAUDE.md's "do not assume a stack" rule for this project. The stack is stated by the guide, not assumed.

## Assumptions (not stated in the guide)

- Our university is NIT Jalandhar.
- Each team member can commit to Git under their own identity on the shared laptop.
- The one-day build allows a single-document end-to-end path first, then extension.

---

## Requirement test plan

| Req | How to test |
|---|---|
| R1 Retrieval | Ask questions whose answers are in a document; check the returned text contains the answer. Ask a question with no source and confirm no answer comes from model knowledge (use `MOCK_LLM` to isolate retrieval). |
| R2 Citations | For each factual answer, check doc_id, section, version, and effective date. Open the cited page and confirm it supports the claim. |
| R3 No fabrication | Run unanswerable questions; expect the exact `not_found` text. Run partial-evidence questions; expect a statement of what is known and unknown. |
| R4 Precedence | Use the Annex A worked example (80% circular vs 75% regulation vs 65% FAQ). Test each policy step with fixtures: scope, supersession, authority, recency, unresolved. Test future-dated and out-of-scope documents. |
| R5 Tools | Unit-test tools against hand-computed values. In LLM mode, check numbers in the answer match tool output. Check every threshold appears in `rule_registry` with a source document and section. |
| R6 Multi-step | Run what-if questions. Check each tool was called and assumptions are listed in the response. |
| R7 Authorisation | Call a personal question without the header (expect `refused`). Ask about another student's ID with a valid header (expect `refused`). Confirm identity comes from the header, not message text. Check logs for personal data. |
| R8 Injection | Ingest a document containing "ignore previous instructions"; confirm behaviour and citations are unchanged. |
| R9 Answer types | For each of the six types, run a question expected to produce it; check `answer_type`. |
| R10 Audit | Every response has a `trace_id`. `GET /audit/{trace_id}` returns all required fields, including Annex D fields. |
| R11 Live ingest | During a test, `POST /ingest` a new document, then ask a question it answers. Expect the answer with no restart. |
| R12 Evaluation | Run the evaluation set; compare to expected answers and sources; report Section 7 metrics. |

**Non-functional tests**
- **Docker:** `docker compose up` on a clean machine starts API, UI, and stores.
- **Persistence:** restart the API; confirm ChromaDB does not re-ingest.
- **Mock mode:** run the pipeline with `MOCK_LLM=true` to completion.
- **Latency and cost:** measure p50 and p95 over the evaluation set; report LLM calls and tokens.
- **Data validation:** run the validation script on synthetic data; confirm it reports seeded violations.

---

## Next steps

- Team decision on the five questions in Section J, starting with rule registry population.
- Approval needed before downloading any university document (filename, source URL, size stated first).
- Create a Git repository at the project folder. The current git root is the home directory.

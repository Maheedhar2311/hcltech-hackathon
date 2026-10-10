# Progress Log

Test results here are only what was actually run (CLAUDE.md rule 8).

## Phase 0: shared contracts and project setup

| Task | Status | Evidence |
|---|---|---|
| T0.1 Shared Pydantic models (`src/app/contracts.py`) | Done | `tests/unit/test_contracts.py` |
| T0.2 SQLite schema, Annex C (`src/app/storage/schema.sql`) | Done | `tests/unit/test_schema.py` |
| T0.3 Project skeleton, `.gitignore`, `.env.example`, README stub | Done | Folder layout from `system_architecture.md` section 12 |

**Test run (2026-10-10):** `python3 -m pytest` in the project root, Python 3.12.7, pydantic 2.8.2, SQLite 3.45.3.
Result: **28 passed, 0 failed**.

**Not yet done in Phase 0:**
- No commit made. The repository exists (owned by Potta Yoshitha); Git identity is not set on this machine. Each member must set their own identity before committing.
- Owners (decision D5), rule-entry approach (D1), document choice and hardware check are still open. See `team_tasks.md` section 7.

## M2: rules and precedence (Member B's module, built in this session)

| Task | Status | Evidence |
|---|---|---|
| B1 Rule registry storage (`src/app/storage/rules.py`) | Done | `tests/unit/test_rules_registry.py` |
| B2 Registry loader from CSV (all-or-nothing) | Done | `tests/unit/test_rules_registry.py` |
| B3 Applicability and scope filter | Done | `tests/unit/test_precedence.py` |
| B4 Supersession and authority (levels 1–2 only; level 5 never overrides) | Done | `tests/unit/test_precedence.py` |
| B5 Recency and unresolved conflict | Done | `tests/unit/test_precedence.py` |
| B6 Annex A worked example (80% / 75% / 65%) | Done | `tests/unit/test_precedence.py` |
| B7 Upcoming changes listed, not applied | Done | `tests/unit/test_precedence.py` |

**Contract change (needs team agreement):** added `winner_value` to `PrecedenceDecision` in `contracts.py`. The answer needs the value (for example "80%"), and the contract had no field for it.

**Assumption recorded in code:** when no student is given, only documents with scope `ALL` are used, because the question's scope cannot be checked.

**Full test run after M2 (2026-10-10):** `python3 -m pytest` → **57 passed, 0 failed**.

Note: one test expectation was corrected during the run. It had assumed only the circular was upcoming, but the FAQ (effective 2026-09-15) is also not yet in force on 2026-07-15. The engine was right; the test was wrong.

## M3: student data and tools (built in this session; owner: Member C)

| Task | Status | Evidence |
|---|---|---|
| C1′ Student loader, all-or-nothing (`src/app/storage/students.py`, `scripts/load_students.py`) | Done | `tests/unit/test_student_data.py` |
| C2′ Validation: schema, logical rules, reserved IDs (`scripts/validate_students.py`) | Done | `tests/unit/test_student_data.py` |
| C3′ `get_attendance` (percentage computed in code) | Done | `tests/unit/test_student_tools.py` |
| C4′ `check_exam_eligibility` (threshold from `rule_registry`, exact comparison) | Done | `tests/unit/test_student_tools.py` |
| C5′ `get_results` | Done | `tests/unit/test_student_tools.py` |
| C6′ Access check (header identity; refuses other students' IDs) | Done | `tests/unit/test_student_tools.py` |

**Contract change (needs team agreement):** `ToolResult.tool` now has a default of `""`. The tool layer sets the name, and the model was rejecting results built before the name was known.

**Decisions recorded in code:**
- Attendance comparisons use exact fractions. For example 1874/2500 = 74.96% fails a 75% threshold, although it displays as 74.96.
- The pass-mark check needs a `pass_mark_pct` rule in the registry. Without it, the check is reported as **skipped**, not passed.
- `get_results` orders by session text, which is not chronological (`2026-DEC` sorts before `2026-MAY`). Nothing depends on that order.

**Not yet built:** a Source Register loader (needed before the rules CSV can load, because rules must cite a registered document). This belongs to M1 (task V1/A1).

**Test run after M3 (2026-10-10):** `python3 -m pytest` → **89 passed, 0 failed**.

## Data task: university documents (2026-10-10)

- Student CSVs had not been provided. The data work used the university PDFs in Downloads instead.
- 14 official documents extracted to `data/documents/text/`. Personal files were excluded; an over-broad extraction was deleted immediately.
- Draft Source Register: 11 rows, of which 6 load. 5 are blocked for missing effective dates (decision needed).
- Draft rules: 3 rules (ATT-MIN-01 ≥ 75, ESE-MIN-01 ≥ 30, SUPP-MAX-01 ≤ 2), all load and cite the regulation clause.
- Rules loader fix: a duplicate `rule_id` now raises a clear error and writes nothing (previously a raw database error). Covered by a new test.
- Review and open decisions: `docs/data_review.md`.
- **Test run (2026-10-10):** `python3 -m pytest` → **90 passed, 0 failed**.

## Ingestion, orchestrator and API (M1, M4, M5 partial), 2026-10-10

Dependencies installed in a project venv (`.venv`, git-ignored) from `requirements.txt`.
Run tests with: `.venv/bin/python -m pytest`

| Task | Status | Evidence |
|---|---|---|
| A2 Text extraction (PDF via pypdf, TXT) | Done | `tests/unit/test_ingestion_text.py` |
| A3 Clause-aware chunker (≤150 words, 20-word overlap) | Done | `tests/unit/test_ingestion_text.py` |
| A4 Embedders (MiniLM from guide; deterministic hash embedder for tests and MOCK) and ChromaDB store | Done | `tests/integration/test_pipeline.py` |
| A5 Atomic ingest (undo chunks if register write fails) | Partly: undo path written, no fault-injection test yet | — |
| A6 Retrieval with score gate | Done | integration tests |
| A7 `POST /ingest` | Done | `test_pipeline.py` |
| D1–D4 LLM gateway, classifier, number check, audit store | Done (MOCK mode tested; live Ollama path not yet exercised) | `test_pipeline.py` |
| D5–D6 LangGraph orchestrator and response assembly | Done | `test_pipeline.py` |
| E1–E3 FastAPI routes, error mapping, health | Done | `test_pipeline.py` |

**Changes made while testing (recorded because they change earlier decisions):**
1. **Scope without a student (M2):** earlier, documents with a scope other than ALL were excluded when no student was given. That excluded the 2023+ regulations from every general question, which is wrong. Now they are considered, and the reason states the scope. Test updated.
2. **Stopwords in the hash embedder:** common words such as "the" and "for" made every question match every chunk. They are now ignored in the test/MOCK embedder only. The MiniLM model used in live mode does not need this.
3. **Duplicate check on ingest:** a document is "already ingested" only when its text is in the vector store. A register row from the reference file is completed, not rejected.
4. **LangGraph:** a state key cannot share a name with a node (`tools`), and every node must write at least one key.

**Test run (2026-10-10):** `.venv/bin/python -m pytest` → **126 passed, 0 failed**.

**Live Ollama test (2026-10-10, model qwen2.5:7b):** `tests/integration/test_live_llm.py`, 8 tests passed in about 18 s.
- Classifier: 4 of 5 labels matched the expected category. The what-if question "If I fail CSDC0202 and pass the supplementary, will I be eligible for placement?" was labelled `personal_eligibility` (expected `multi_step`). The rule-based fallback labels it `multi_step`. Open: prefer the rule-based label for what-if patterns, or tighten the prompt. Not changed yet.
- Explanation: returned a sentence using only the facts supplied. The number check passed.
- Number check: an explanation with an invented figure (91.7%) is replaced by the template. Tested.
- End-to-end eligibility question: answered as `calculated`, with 2 LLM calls and 301 tokens recorded in the audit.
- The classifier test checks only that the output is a valid category; it does not fail on a wrong label. This is deliberate for now, and the mismatch above is recorded here instead.

**Not yet done in this area:** the MiniLM embedder (not yet exercised, model download needed); a fault-injection test for atomic ingest; the Streamlit UI (E4); Docker (E5); README (E6); evaluation (V2, V3, I5).

## Strict classifier test, UI, Docker and README (2026-10-10)

- **Classifier test is strict.** A wrong label fails the test. The what-if pattern ("If I fail … and pass …") is now decided by a fixed rule, not the model. Live result: 5 of 5 labels correct, 8 of 8 live tests pass.
- **Streamlit UI** (`src/app/ui/app.py`, `src/app/ui/client.py`): Ask, Add document, Sources tabs, with a health indicator. It calls the API over HTTP only. Tests run the real API on a local port and load the page in Streamlit's test runner: 6 of 6 pass.
- **Dockerfile, docker-compose.yml, .dockerignore:** written. **Not built or run**, because Docker is not installed on this machine. The CPU PyTorch wheel version (2.4.1) is unverified.
- **README:** architecture diagram, setup, run, sample `curl` commands (run against the live API), assumptions, limitations.
- **setup_db.py** is safe to run more than once.

**Bugs found by running the real API and fixed:**
1. A personal question for a student with no record was answered as `calculated` with an empty result. It is now `not_found`, with a regression test.
2. The README's first example asked a question before the regulations were indexed. The README now indexes first.
3. `googleapis-common-protos` was upgraded by the Streamlit install and broke ChromaDB's import. Pinned to 1.65.0.
4. `python-multipart` was missing, so file uploads failed. Added.

**Retrieval quality (important):**
- With the MOCK hash embedder, the question "minimum attendance for the end-semester exam" returned clause R11.2 (assessment weightage). Wrong. The MOCK path is for tests only.
- With the MiniLM embedder (downloaded and run here), the top results were R8.4 and R8.1 (score 0.71). That is right.
- An unrelated question ("scholarship in Antarctica") scored 0.38 with MiniLM. The gate at 0.25 would not reject it, so live MIN_SCORE is set provisionally to 0.5. The evaluation set has to confirm this value; two examples are not enough.

**Test run (2026-10-10):** `.venv/bin/python -m pytest` → **141 passed, 0 failed**.

**Still open:** Docker build and run; the student data (generator stopped earlier); the evaluation set and harness; the team decisions (owners, rule entry, cloud fallback); the five undated documents; atomic-ingest fault test.

## Student data, atomic ingest, evaluation (2026-10-10)

- **Student data:** 32 students, 6 courses, 104 attendance rows, 106 result rows. Generated by `scripts/generate_students/generate_fixed.py`, **not LLM-generated** (guide Section 4.2 deviation, chosen for time; see `data/students/DATA_CARD.md`). The LLM generator was run for 12 students and stopped; its output was not saved.
- **Validation:** `validate_students.py` passes on the data. The validator now also checks the end-semester 30% rule (R13.3), which needed the end-semester maximum (70, assumed). A bug was found and fixed: a skip-note branch had replaced the pass-mark check.
- **Loaded** into `data/app.sqlite3` with `setup_db.py --students`.
- **Atomic ingest:** three fault tests pass (vector store failure, register failure with chunk rollback, success).
- **Synthetic circular** `SYN-CIRC-ATT-2026` (80% attendance from 1 Aug 2026, supersedes R8.1) added to the register, marked synthetic, for conflict questions.
- **Evaluation:** `scripts/evaluate.py` with 26 questions in `tests/eval/eval_set.json` (policy 8, version 3, unanswerable 4, personal 5, cross-student 3, multi-step 2, ambiguous 1). Report written to `docs/evaluation_report.md`.
- **Embedder on CPU:** the MiniLM embedder ran out of GPU memory on this Mac while the 7B model was loaded, so it is pinned to CPU.

**Test run:** `.venv/bin/python -m pytest` → **144 passed, 0 failed**.

**Still open:** Docker (not built); team decisions (owners, rule entry, cloud fallback); the five undated documents; placement policy (scanned); the LLM-generated student data (submission requirement); team submission items (Git identities and commits, AI-usage disclosure, contribution statement, signed declarations).

## Open issues

- `docs/interface_contracts.md` is empty. Its content is now covered by `src/app/contracts.py`; decide whether to delete it or fill it.
- `docs/Untitled-1` is an empty tracked file with no clear purpose. Confirm before removing.

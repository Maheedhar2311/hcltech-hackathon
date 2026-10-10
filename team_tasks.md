# Team Tasks: Module Breakdown

**Based on:** [system_architecture.md](system_architecture.md) (components C1–C14)
**Status:** Proposed. Owners are provisional until decision D5 is agreed by the team.
**Rule (CLAUDE.md):** every task has one owner and clear acceptance criteria. Do not change another member's module without agreeing it first.

---

## 1. Modules and proposed owners

| Module | Components | Proposed owner | Folder |
|---|---|---|---|
| M1 Ingestion and retrieval | C2, C5, C6 | Member A | `src/app/ingestion/`, `src/app/retrieval/` |
| M2 Rules and precedence | C8, C9 | Member B | `src/app/precedence/`, `src/app/storage/rules.py` |
| M3 Student data and tools | C10, C11, student loader | Member C | `src/app/tools/`, `scripts/load_students.py` |
| M4 Orchestration and LLM | C4, C7, C13 | Member D | `src/app/orchestrator/`, `src/app/llm/`, `src/app/storage/audit.py` |
| M5 API, UI and packaging | C1, C3, C12, Docker | Member D (shared with M4) | `src/app/api/`, `src/app/ui/`, `docker-compose.yml` |
| M6 Data and evaluation | Synthetic data, validator, C14 | Member C (data), Member B (eval) | `scripts/generate_students/`, `tests/eval/` |

**Load note:** Member D carries two modules. If that is too heavy, move the UI (C1) to whoever finishes first.

---

## 2. Phase 0: shared contracts (everyone, first)

Modules cannot start coding against each other until the contracts exist. CLAUDE.md rule 5 requires this.

| Task | Owner | Output | Acceptance criteria |
|---|---|---|---|
| T0.1 Shared Pydantic models | Member D | `src/app/contracts.py` with `AskRequest`, `Chunk`, `Citation`, `ToolResult`, `PrecedenceDecision`, `AskResponse`, `AuditRecord`, `SourceMetadata` | Every field in `system_architecture.md` section 6.2 and guide section 6.1 is present; module imports cleanly; all four members review it |
| T0.2 SQLite schema (Annex C) | Member C | `src/app/storage/schema.sql` with `students`, `courses`, `attendance`, `results`, `rule_registry`, `source_register`, `audit` | Column names and types match Annex C exactly; required columns not renamed; schema creates an empty database |
| T0.3 Project skeleton and Git | Member D | Folders from `system_architecture.md` section 12, `.gitignore`, `.env.example`, empty `README.md` | Git repo exists at project root; each member has committed under own identity; no secrets committed |

**Exit criterion for Phase 0:** all three tasks merged, and everyone has read `contracts.py` and `schema.sql`. Only then start Phase 1.

---

## 3. Phase 1: module tasks (run in parallel after Phase 0)

### M1 Ingestion and retrieval (Member A)

| Task | Acceptance criteria | Depends on | How to test |
|---|---|---|---|
| A1 Metadata validation (Annex B) | Rejects missing `doc_id`, bad `authority_level` (not 1–5), bad dates, duplicate `doc_id` | T0.1 | Unit tests with good and bad fixtures |
| A2 Text extraction from PDF and text files | Extracts text per page with page numbers; rejects file with no text layer (returns error) | A1 | Unit tests on one text PDF and one scanned PDF (expect error) |
| A3 Chunker | Each chunk keeps section and page; each chunk is under the embedding limit (256 tokens) | A2 | Unit test: long page splits; no chunk over limit |
| A4 Embedding and Chroma write | Chunks written with full metadata; persisted to disk; reloads after restart | A3, T0.2 | Integration: write, restart process, query returns the same chunk |
| A5 Atomic ingest | If write fails midway, no partial chunks remain for that `doc_id` | A4 | Fault-injection test |
| A6 Retrieval with score gate | Returns top-k chunks with metadata and score; returns empty result when best score is below threshold | A4 | Unit test with fixed corpus; threshold is configurable, not hard-coded |
| A7 `POST /ingest` service function | Returns `doc_id`, `chunks_indexed`, `status`; document searchable on next query with no restart | A5, A6 | End-to-end test: ingest, then query |

**Interfaces M1 provides:** `ingest(file, metadata) -> IngestResult`; `retrieve(question, as_of, top_k) -> list[Chunk]`.

### M2 Rules and precedence (Member B)

| Task | Acceptance criteria | Depends on | How to test |
|---|---|---|---|
| B1 Rule registry storage | Read and write `rule_registry` rows; every row requires `source_doc_id` and `source_section` | T0.2 | Unit: reject row missing source |
| B2 Registry loader from CSV | Loads rules from CSV; rejects rows with unknown `source_doc_id` | B1 | Unit tests |
| B3 Applicability filter | Excludes documents whose `effective_from` is after `as_of_date` or `effective_to` is before it; excludes out-of-scope programme or batch | T0.1 | Fixture tests for each case |
| B4 Supersession and authority | Supersession only at authority level 1 or 2; higher authority wins; level 5 never overrides | B3 | Fixture tests |
| B5 Recency and unresolved | Same authority: later `effective_from` wins; equal date or otherwise unresolved returns `conflict = true` with both citations | B4 | Fixture tests |
| B6 Annex A worked example | Question at `as_of_date` 2026-10-06 returns 80% (circular supersedes regulation), FAQ does not override | B4, B5 | Automated test using the guide's example |
| B7 Upcoming changes | Documents not yet effective are returned as `upcoming`, not as the answer | B3 | Fixture test |

**Interfaces M2 provides:** `resolve(chunks, student, as_of, registry) -> PrecedenceDecision`.

### M3 Student data and tools (Member C)

| Task | Acceptance criteria | Depends on | How to test |
|---|---|---|---|
| C1' Student loader | Loads CSVs in Annex C schema; rejects the whole file on any violation and prints violations; single transaction | T0.2 | Unit: one good file; one bad file (no rows inserted) |
| C2' Validation script | Checks attended ≤ held; marks within range; total = internal + external; result matches marks; reports violations | T0.2 | Test with seeded violations; output matches expected list |
| C3' Tool: `get_attendance` | Returns held, attended and percentage computed in code; percentage not stored | T0.1, C1' | Hand-computed values; boundary: exactly 75%, one class below |
| C4' Tool: `check_exam_eligibility` | Reads threshold from `rule_registry` (not from code); returns `rule_id`; ELIGIBLE, NOT_ELIGIBLE or unclear | C3', M2 B1 | Tests at exact threshold, one below, absent result, detained |
| C5' Tool: `get_results` | Returns result, marks and pass or fail for one course | C1' | Tests: pass, fail just below pass mark, absent |
| C6' Ownership check | Each tool takes `student_id` as a parameter; a request for another student's ID returns refusal | C3' | Test: student A cannot read student B's rows |

**Interfaces M3 provides:** the tool functions listed in `system_architecture.md` section 6.2, each returning `ToolResult`.

### M4 Orchestration, LLM and audit (Member D)

| Task | Acceptance criteria | Depends on | How to test |
|---|---|---|---|
| D1 LLM gateway | Single client for Ollama; `MOCK_LLM=true` returns rule-based output; config switch for model name | T0.1 | Unit with mock server |
| D2 Classifier | Returns one category from the allowed list; retries once on invalid JSON; falls back to rule-based classifier | D1 | Unit: valid, invalid, unavailable |
| D3 Explanation with number check | Explanation prompt wraps retrieved text as data; any number not in tool output or citations triggers template fallback | D1 | Unit: extra number replaced |
| D4 Audit store | One row per request (Annex D fields); readable by `trace_id`; written even for refused requests | T0.2 | Integration: refused and normal requests both produce a row |
| D5' LangGraph graph | Fixed nodes from architecture section 3; branches for refused, clarification, not_found, conflict, normal | D2, D3, D4, M1 A6, M2 B1, M3 C3' | Integration with `MOCK_LLM=true`: one test per branch |
| D6 Response assembly | Output matches guide section 6.1 exactly; `answer_type` set by rules, not by the LLM | D5', T0.1 | Contract test |

**Interfaces M4 provides:** `ask(question, as_of, student_id) -> AskResponse`.

### M5 API, UI and packaging (Member D, shared)

| Task | Acceptance criteria | Depends on | How to test |
|---|---|---|---|
| E1 FastAPI routes | `/ask`, `/ingest`, `/health`, `/audit/{trace_id}`, `/sources` exist with the guide's request and response shapes | T0.1, M4 D6, M1 A7 | Contract tests with FastAPI test client |
| E2 Error mapping | 422 for bad input; 404 for unknown trace; 409 for duplicate `doc_id`; 503 when a store is down | E1 | Tests for each code |
| E3 Health check | Reports API, Chroma, SQLite and LLM status separately | E1 | Test with each store stopped in turn |
| E4 Streamlit UI | Question box, student ID field sent as header, answer with citations, trace link; no business logic | E1 | Manual run plus screenshot |
| E5 Docker compose | `docker compose up` starts API and UI; documents how to reach Ollama on the host | E1, E4 | Smoke test on a clean run |
| E6 README | Architecture diagram, setup, run steps, sample `curl` commands, assumptions, limitations | All modules | Each `curl` in README runs as written |

### M6 Data and evaluation

| Task | Owner | Acceptance criteria | Depends on |
|---|---|---|---|
| S1 Synthetic student prompts | Member C | Prompts saved verbatim in repo; cover 30+ students, 2 programmes, 2 batches, 6 courses, and the Section H edge cases | T0.2 |
| S2 Generator script | Member C | Calls the LLM; output validated against schema; retries on failure | S1 |
| S3 Data card | Member C | Annex E fields completed | S2, C2' |
| V1 Source Register CSV | Member A | One row per document with Annex B fields and `synthetic` flag | A1 |
| V2 Evaluation set | Member B | At least 20 questions with expected answer and source; includes the required counts (3 unanswerable, 3 version/conflict, 4 personal, 2 cross-student attempts, 2 multi-step) | Documents chosen (open item) |
| V3 Eval harness | Member B | Computes answer correctness, citation accuracy, abstention accuracy, tool correctness, retrieval hit rate, p50/p95 latency, LLM calls and tokens | V2, E1 |

---

## 4. Phase 2: integration and demo (everyone)

| Task | Owner | Acceptance criteria |
|---|---|---|
| I1 First end-to-end path | Member D | One document, one policy question, one cited answer, through `/ask` |
| I2 Add personal eligibility path | Member C with D | One eligibility answer with tool output and `rule_id` |
| I3 Add conflict path | Member B with A | One conflict resolved by the Annex A policy |
| I4 Live ingest rehearsal | Member A | New document ingested and used with no restart |
| I5 Evaluation run | Member B | Report written with measured numbers only |
| I6 Demo script and Q&A prep | Everyone | Each member can explain their module (CLAUDE.md) |

**Order matters:** I1 must work before anything else in Phase 2 starts. If I1 slips, cut features, not integration.

---

## 5. Dependency map

```
Phase 0:  T0.1 contracts ──┬── T0.2 schema ──┬── T0.3 skeleton
                           │                 │
Phase 1:  M1 ingest/retr. ─┤  M2 rules ──────┤  M3 students/tools
                           │                 │
          M4 LLM/graph ────┴──── M5 API/UI ──┘
Phase 2:  I1 first path → I2 eligibility → I3 conflict → I4 live ingest → I5 eval → I6 demo
```

---

## 6. Rules for working in parallel

1. **Contracts first.** Phase 0 is not optional. Change `contracts.py` only by team agreement, since every module depends on it.
2. **Mock what you need.** Each module can test against mocks of others until the real module is merged.
3. **Commit under your own identity** with clear messages, at least hourly (guide rule).
4. **Do not edit another owner's folder** without agreement in the team channel.
5. **Report only measured results.** Test output goes in `docs/progress.md`. Do not claim tests passed unless they were run (CLAUDE.md rule 8).
6. **Each owner explains their module** in simple language (CLAUDE.md rule 10) before the first integration merge.

---

## 7. Open items for the team

- **D5:** confirm owners above, or swap them.
- **D1:** confirm rules are entered by hand for the demo (affects B1, B2 and I3).
- **Documents:** choose the three university documents (affects V1, V2 and I3).
- **Hardware:** confirm the laptop runs the chosen Ollama model (affects D1 and I1).

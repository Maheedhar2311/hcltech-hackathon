# Solution Research: AI-Powered University Student Services Assistant

**Based on:** [docs/case_study_analysis.md](case_study_analysis.md)
**Scope:** Research only. No implementation.
**Date of research:** 2026-10-10

**How to read this file**
- **Verified** means the claim was checked against a primary source fetched during this research. The source and its date are given.
- **Search-only** means the claim came from search snippets, not a fetched page. Treat it as unconfirmed.
- **Hypothesis** means our own reasoning. It needs testing.

---

## 1. Primary sources used

| Ref | Source | Date | Status |
|---|---|---|---|
| S1 | Anthropic, "Building effective agents" — https://www.anthropic.com/research/building-effective-agents | Published Dec 19, 2024 | Verified (fetched) |
| S2 | LangGraph docs, "Workflows and agents" — https://docs.langchain.com/oss/python/langgraph/workflows-agents | Undated | Verified (fetched) |
| S3 | Ollama blog, "Structured outputs" — https://ollama.com/blog/structured-outputs | Published Dec 6, 2024 | Verified (fetched) |
| S4 | Ollama API docs (`format`, `tools`) — https://github.com/ollama/ollama/blob/main/docs/api.md | Undated (live file) | Verified (fetched) |
| S5 | Sentence-transformers model card, all-MiniLM-L6-v2 — https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 | Undated | Verified (fetched) |
| S6 | Lewis et al., "Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks" — https://arxiv.org/abs/2005.11401 (NeurIPS 2020) | Submitted 22 May 2020; revised 12 Apr 2021 | Verified (search result showing dates) |
| S7 | Yan et al., "Corrective Retrieval Augmented Generation" (CRAG) — https://arxiv.org/abs/2401.15884 | v1 29 Jan 2024; v3 7 Oct 2024 | Verified (search result showing dates); method details from abstract only |
| S8 | Es et al., "RAGAS: Automated Evaluation of Retrieval Augmented Generation" — https://arxiv.org/abs/2309.15217 | 2023 (exact date not checked) | Verified (search result); metric names from paper |
| S9 | Berkeley Function Calling Leaderboard (BFCL) — https://gorilla.cs.berkeley.edu/leaderboard.html | Last updated 2026-04-12 (per page) | Verified (fetched); page lacked Llama 3.1 8B scores |
| S10 | BIRD benchmark, text-to-SQL — arXiv, May 2023 | May 2023 (per search summaries) | Search-only; not fetched |
| S11 | ChromaDB persistent client docs — https://docs.trychroma.com/docs/run-chroma/persistent-client | — | **Unverified.** Fetch returned HTTP 404. Only search snippets were read. |

---

## 2. Approaches and their evidence

### Approach A — Fixed workflow (deterministic pipeline with LLM at the edges)

**1. Approach and intended use.** Code defines the steps in a fixed order: classify the question, retrieve from documents, resolve precedence in code, query tools, then have the LLM explain the results. Anthropic calls this a *workflow*: "systems where LLMs and tools are orchestrated through predefined code paths" (S1). LangGraph describes workflows as having "predetermined code paths" and suits "well-defined tasks that can be broken into known steps, such as prompt chaining" (S2).

**2. Main advantages.**
- Verified: S1 recommends "finding the simplest solution possible, and only increasing complexity when needed."
- Verified: S2 says workflows fit well-defined tasks with known steps.
- Hypothesis: a fixed order makes each step testable on its own, which matches the case study's testing rules (Section H and I of the analysis).

**3. Limitations.**
- Verified: S1 defines workflows as code-path orchestration, so the system cannot choose new steps for unforeseen questions.
- Hypothesis: new question types need code changes, which fits poorly with "live ingestion without code change" (R11) only if the new document changes data, not steps. Document ingestion changes data, so this is manageable.

**4. Suitability.** High. The case study has defined question types (Section 2.1 of the guide): policy fact, procedure, personal data, eligibility, multi-step, and not-answerable. Each maps to a known path. This fits the guide's statement that "the simplest architecture that meets the requirements scores highest."

**5. Evidence.** S1, S2 (verified). The guide itself (Section 1).

**6. Improvements.** Add a fallback path for unclassified questions that returns `clarification_needed`, and keep the path set small.

---

### Approach B — Autonomous tool-calling agent (LLM chooses its own tools in a loop)

**1. Approach and intended use.** The LLM decides which tools to call, in what order, and when to stop. S1 calls this an *agent*: "systems where LLMs dynamically direct their own processes and tool usage" (S1). S2 says agents suit "situations where problems and solutions are unpredictable."

**2. Advantages.**
- Verified: S2 notes agents handle open-ended problems where the model must choose its own steps.
- Verified: S4 says the Ollama `tools` parameter lets a model return `tool_calls`, which the app executes and returns to the model.

**3. Limitations.**
- Verified: S1 notes agentic systems "often trade latency and cost for better task performance."
- Verified: S4 states tool calling depends on the model: "Tool calling is explicitly limited to models with tool support."
- Verified: S3 notes that structured output from Ollama depends on the model and that outputs must be validated.
- Verified (indirect): BFCL (S9) measures function-calling accuracy across models, and results vary widely by model and evaluation mode. The page we fetched lacked Llama 3.1 8B scores, so we cannot quote a number for it.
- **Relevance to the case study:** the guide says "No tool use at all" is a disqualifier, and also that authoritative results must come from code, not LLM judgement (R5). An agent that picks tools is acceptable only if the tools themselves compute the results.

**4. Suitability.** Medium. It meets R5 and R6 in principle, but its tool selection is non-deterministic. Judges asking unseen questions could see different paths for the same question, which is hard to explain. The guide also says agents must be justified ("be ready to explain why").

**5. Evidence.** S1, S2, S3, S4, S9.

**6. Improvements.** Keep the agent loop but restrict it to a fixed tool list, with a step limit and a logged trace.

---

### Approach C — Text-to-SQL over the student database

**1. Approach and intended use.** The LLM writes a SQL query over the SQLite student tables, the query runs, and the result is explained.

**2. Advantages.**
- Hypothesis: flexible for unforeseen personal questions without writing a tool for each one.

**3. Limitations.**
- Search-only (S10): BIRD reports execution accuracy of about 54.89% for GPT-4 with curated evidence and 34.88% without. These are benchmark figures on large, unseen schemas, not our schema. Treat as indicative only.
- Search-only (S10): commentary reports label errors in gold queries, so benchmark scores are imperfect.
- Hypothesis: free-form SQL from an 8B local model risks wrong joins and wrong thresholds. The guide forbids "LLM arithmetic or LLM judgement" for authoritative results (R5). Generated SQL would also need a whitelist and read-only access to protect student data (R7).

**4. Suitability.** Low to medium. Our schema is small and fixed (Annex C), so a set of named tools is simpler, easier to test, and easier to explain than free-form SQL. The guide's own text favours "tools over SQLite."

**5. Evidence.** S10 is search-only. The rest is hypothesis.

**6. Improvements.** Not recommended as the main path. Could be a later extension if time allows.

---

### Approach D — Plain RAG (retrieve chunks, LLM answers from them)

**1. Approach and intended use.** Retrieve document chunks by embedding similarity, pass them to the LLM, and generate an answer with citations. S6 introduced the RAG pattern: a retriever over a dense index combined with a seq2seq generator.

**2. Advantages.**
- Verified: S6 shows retrieval-augmented generation can ground answers in an external index.
- Hypothesis: quickest to build. Covers R1, R2, and part of R3.

**3. Limitations.**
- Hypothesis: plain RAG cannot do R5 (personal data, eligibility calculation) or R4 (precedence beyond what the LLM infers from text). Relying on the LLM for precedence conflicts with the guide's policy.
- Verified (indirect): S8 defines faithfulness and context relevance as metrics, which suggests plain RAG needs evaluation of exactly these properties.
- Search-only: CRAG (S7) argues that retrieval quality varies, and proposes checking retrieval confidence before using it. The paper's abstract says a retrieval evaluator classifies results as Correct, Incorrect, or Ambiguous. Full method details were not checked.

**4. Suitability.** Insufficient on its own. Covers only the document half of the guide.

**5. Evidence.** S6, S7 (search-only for method details), S8.

**6. Improvements.** Add a retrieval-confidence gate before answering, to support R3 (`not_found`). This is a candidate for the improvement we evaluate (see Section 5).

---

### Approach E — Multi-agent supervisor (specialist agents plus a supervisor)

**1. Approach and intended use.** A supervisor LLM routes sub-tasks to specialist agents (RAG agent, tool agent, rule agent), then merges results.

**2. Advantages.**
- Verified (indirect): S1 describes orchestrator-worker patterns for subtasks that cannot be predefined (S2 mentions the same pattern).
- Hypothesis: parallel work across team members maps onto specialist agents.

**3. Limitations.**
- Verified: S1 says start with the simplest solution and add complexity only when needed.
- The guide says explicitly that "seven agents it cannot explain" lose to "a clean, well-tested system" (guide, Section 1). The split into RAG, tool, and rule agents is "illustrative only" (guide, Section 5).
- Hypothesis: more agents add more LLM calls, latency, and failure points, and the 8B local model may not coordinate reliably.

**4. Suitability.** Low for this case study. It fits capability level 6 (guide, Section 9.3), but the scoring favours simplicity.

**5. Evidence.** S1, S2, and the guide.

**6. Improvements.** Not recommended now.

---

## 3. Comparison

Scores: 1 = weak, 5 = strong. These scores are our judgement, not measured values.

| Criterion | A. Fixed workflow | B. Autonomous agent | C. Text-to-SQL | D. Plain RAG | E. Multi-agent |
|---|---|---|---|---|---|
| Fit to requirements (R1–R12) | 5 | 4 | 3 | 2 | 4 |
| Development time (one day) | 4 | 3 | 3 | 4 | 1 |
| Implementation complexity | 4 | 3 | 2 | 4 | 1 |
| Cost and resources (local 8B LLM) | 5 | 3 | 3 | 5 | 2 |
| Accuracy and reliability | 4 | 3 | 2 | 2 | 2 |
| Ease of testing | 5 | 2 | 3 | 3 | 2 |
| Explainability at evaluation | 5 | 3 | 3 | 3 | 2 |
| **Total** | **32** | **21** | **19** | **23** | **14** |

**Reasons for key scores (hypotheses unless stated):**
- **A** scores highest on testability and explainability because each step can be unit-tested and shown to judges. S1 and S2 support simplicity and predictability for defined tasks.
- **B** loses on testability because the tool path varies per run. S4 and S3 show that tool calling and JSON outputs depend on the model, which is a reliability risk with a local 8B model.
- **C** loses because the guide's data is small and fixed, so SQL flexibility adds risk without benefit. S10 shows text-to-SQL accuracy is low on realistic benchmarks.
- **D** covers documents but not R5 or eligibility, so it cannot meet the case study alone.
- **E** is the most complex, which the guide explicitly penalises.

---

## 4. Recommendation

**Adopt Approach A (fixed workflow), using LangGraph for the step graph, with these rules:**

1. **Deterministic core.** Precedence (Annex A), eligibility, arithmetic, and student lookups are plain Python functions over SQLite and the rule registry (R4, R5). The LLM never computes these.
2. **LLM at the edges only.** The LLM may (a) label the question category and extract tool arguments, and (b) write the explanation of tool results. Both outputs are validated against a Pydantic schema, with a retry and a deterministic fallback. This follows S3 (validate outputs; test the specific model) and S4 (tool calling depends on the model).
3. **Mock mode.** `MOCK_LLM=true` runs the same pipeline with rule-based classification and template explanations. This makes most tests independent of the model.
4. **Retrieval with a gate.** Retrieve chunks from Chroma, then check the top score against a threshold before answering. Below threshold, return `not_found` (R3). The threshold is a tunable value we can measure.
5. **Keep it small.** No multi-agent layer. Add an agent loop only if a requirement cannot be met otherwise.

**Why this is the best trade-off for this case study:**
- It satisfies R4 and R5 directly, which the guide treats as scoring criteria.
- It keeps tests reliable, which the guide says matters for "meaningful testing" (Section 9.2).
- It keeps each module explainable by its owner (Section 9.4).
- It runs on a local 8B model without depending on tool-calling accuracy.

**Hypothesis to test:** a deterministic core with an LLM only for classification and explanation will match or beat an autonomous agent on the evaluation set, with lower latency and fewer LLM calls. We should measure this rather than assume it.

**Caveats:**
- Vector store: ChromaDB is required by the guide, so we use it. The persistence claim (S11) could not be verified from the official page, so we should check it in the Chroma docs or by a test before relying on it.
- Embeddings: S5 gives 384 dimensions and truncation at 256 word pieces. Longer chunks lose text, so chunk size must stay below that limit. This is a constraint on chunking, not a reason to reject the model.

---

## 5. Two improvements to implement and evaluate

Each improvement has a measurable outcome and an evaluation method (following the guide's Section 7).

### Improvement 1 — Model comparison for structured output and classification

- **What:** Compare two local models (`llama3.1:8b` and `qwen2.5:7b-instruct`, both suggested in the guide) on question classification and tool-argument extraction. Use the same prompts and the same evaluation set.
- **Why:** S3 and S4 say structured output and tool calling depend on the model. The guide asks for a comparison of at least two configurations (Section 7).
- **Measure:** classification accuracy, valid-JSON rate on the first attempt, retries needed, and p50/p95 latency.
- **Pass criterion (proposed):** choose the model with higher classification accuracy and at least 95% valid JSON after one retry. These thresholds are our proposal, not from the guide.
- **Effort:** low. Needs both models pulled and one test script.

### Improvement 2 — Retrieval gate versus LLM-only abstention

- **What:** Compare two ways to decide `not_found`: (a) an LLM instruction to abstain when the context is insufficient, and (b) a retrieval-score threshold gate that abstains before the LLM is called. This relates to the retrieval-confidence idea in CRAG (S7).
- **Why:** R3 and the guide's "Abstention accuracy" metric (Section 7) depend directly on this choice. Hallucinated answers are the main safety risk.
- **Measure:** abstention accuracy on unanswerable questions, false abstentions on answerable questions, and retrieval hit rate in top-k (Section 7 metrics).
- **Pass criterion (proposed):** the gate reduces fabricated answers on the unanswerable set without losing more than a small share of answerable questions. The exact limits are ours to set after measuring.
- **Effort:** medium. Needs a labelled evaluation set (at least 20 questions, per the guide) and a threshold sweep.

**Why these two:** both are cheap to run in a one-day build, both produce numbers the judges can check, and both target the highest-weighted criteria (grounded answers, 20 points; evaluation rigour, 10 points).

---

## 6. Open items and gaps

- **S11 unverified.** The ChromaDB persistence claim must be checked against the official page before we rely on it. Our fetch returned 404.
- **S10 search-only.** BIRD figures are indicative. Confirm against the paper before quoting them.
- **BFCL Llama 3.1 8B score not found.** The leaderboard page we fetched did not list it. We cannot cite a number. The earlier third-party aggregator figure (76.1%) was not verified and should not be used.
- **S8 date not checked.** Confirm the arXiv submission date before citing it.
- **Ollama model support.** S4 says tool calling depends on the model, but the page gives no complete list. Confirm `llama3.1:8b` and `qwen2.5:7b-instruct` support on the team's own machine.
- **Hardware not measured.** Latency claims for an 8B model on the team laptops are not yet tested.

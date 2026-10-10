"""Orchestrator: one fixed LangGraph graph per question (task D5, architecture section 3).

Nodes run in this order. Branches are decided by code, never by the model:

  classify -> authorise --refused------------------------------> audit
                       \\--ambiguous--> respond ------------------> audit
                        \\--personal--> tools --------------------> audit
                         \\--policy---> retrieve --not found-----> audit
                                              \\--> precedence ---> audit

`audit` writes the Annex D record for every request, including refusals.
"""

from __future__ import annotations

import re
import secrets
import sqlite3
import time
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Optional, TypedDict

from langgraph.graph import END, StateGraph

from app.contracts import (
    AnswerType,
    AppliedRule,
    AskResponse,
    AuditRecord,
    Category,
    Chunk,
    Citation,
    PrecedenceDecision,
    SourceMetadata,
    ToolResult,
    ToolStatus,
)
from app.llm.gateway import LLMGateway
from app.precedence.engine import Candidate, StudentScope, resolve
from app.retrieval.embedder import Embedder
from app.retrieval.service import retrieve
from app.retrieval.store import VectorStore
from app.storage.audit import write_audit
from app.tools.access import refusal_message
from app.tools.student_tools import check_exam_eligibility, get_attendance

NOT_FOUND = "I could not find this information in the authorised university sources."
ATTENDANCE_RULE = "ATT-MIN-01"
COURSE_CODE = re.compile(r"\b[A-Z]{4}\d{4}\b")
PERSONAL = {Category.PERSONAL_DATA, Category.PERSONAL_ELIGIBILITY, Category.MULTI_STEP}


@dataclass
class Services:
    conn: sqlite3.Connection
    store: VectorStore
    embedder: Embedder
    gateway: LLMGateway
    top_k: int
    min_score: float
    model_name: str


class State(TypedDict, total=False):
    question: str
    as_of: date
    header_id: Optional[str]
    trace_id: str
    started: float
    category: Category
    personal: bool
    answer_type: AnswerType
    answer: str
    explanation: str
    citations: list
    applied_rules: list
    conflicts: list
    chunks: list
    tool_results: list
    decision: str
    sources: list
    facts: list
    response: AskResponse


# ---------- helpers ----------

def _source(conn: sqlite3.Connection, doc_id: str) -> Optional[SourceMetadata]:
    row = conn.execute(
        "SELECT doc_id, title, issuer, authority_level, doc_type, version, effective_from, effective_to, "
        "supersedes, scope_programmes, scope_batches, provenance, retrieved_on, synthetic "
        "FROM source_register WHERE doc_id = ?", (doc_id,),
    ).fetchone()
    if row is None:
        return None
    return SourceMetadata(
        doc_id=row[0], title=row[1], issuer=row[2], authority_level=row[3], doc_type=row[4],
        version=row[5], effective_from=row[6], effective_to=row[7], supersedes=row[8],
        scope_programmes=row[9], scope_batches=row[10], provenance=row[11],
        retrieved_on=row[12], synthetic=bool(row[13]),
    )


def _student_scope(conn: sqlite3.Connection, student_id: Optional[str]) -> Optional[StudentScope]:
    if not student_id:
        return None
    row = conn.execute("SELECT programme, batch_year FROM students WHERE student_id = ?", (student_id,)).fetchone()
    return StudentScope(programme=row[0], batch_year=row[1]) if row else None


def _rule_value(conn: sqlite3.Connection, doc_id: str, section: str) -> Optional[str]:
    row = conn.execute(
        "SELECT value FROM rule_registry WHERE source_doc_id = ? AND source_section LIKE ? LIMIT 1",
        (doc_id, f"%{section}%"),
    ).fetchone()
    return row[0] if row else None


def _citation(src: SourceMetadata, section: str, page: Optional[int]) -> Citation:
    return Citation(doc_id=src.doc_id, title=src.title, section=section, page=page,
                    version=src.version, effective_from=src.effective_from)


def _respond(state: State, answer_type: AnswerType, answer: str, explanation: str = "") -> dict:
    return {"answer_type": answer_type, "answer": answer, "explanation": explanation or answer}


# ---------- nodes ----------

def make_nodes(svc: Services):
    def classify(state: State) -> dict:
        category = svc.gateway.classify(state["question"])
        return {"category": category, "personal": category in PERSONAL}

    def authorise(state: State) -> dict:
        msg = refusal_message(state.get("header_id"), state["question"], state["personal"])
        if msg:
            return _respond(state, AnswerType.REFUSED, msg)
        if state["category"] == Category.AMBIGUOUS:
            return _respond(state, AnswerType.CLARIFICATION_NEEDED,
                            "Could you say which rule, course or procedure you mean?")
        return {"category": state["category"]}  # LangGraph needs every node to write something

    def tools(state: State) -> dict:
        sid = state["header_id"]
        codes = sorted(set(COURSE_CODE.findall(state["question"])))
        if not codes:
            return _respond(state, AnswerType.CLARIFICATION_NEEDED,
                            "Which course do you mean? Please include the course code, for example CSDC0202.")
        rule_src = None
        missing: list[str] = []
        results: list[ToolResult] = []
        facts: list[str] = []
        lines: list[str] = []
        applied: list[AppliedRule] = []
        citations: list[Citation] = []
        for code in codes:
            att = get_attendance(svc.conn, sid, code)
            results.append(att)
            if att.status == ToolStatus.ERROR:
                lines.append(f"{code}: no attendance record was found for you.")
                missing.append(code)
                continue
            facts.append(f"Your attendance in {code} is {att.output['attendance_pct']}%.")
            if state["category"] == Category.PERSONAL_ELIGIBILITY or state["category"] == Category.MULTI_STEP:
                elig = check_exam_eligibility(svc.conn, sid, code, ATTENDANCE_RULE)
                results.append(elig)
                if elig.status == ToolStatus.ERROR:
                    return _respond(state, AnswerType.NOT_FOUND, NOT_FOUND)
                out = elig.output
                threshold = out["threshold"]
                rule_src = _source(svc.conn, out["source_doc_id"])
                applied.append(AppliedRule(rule_id=ATTENDANCE_RULE, value=threshold,
                                           source_doc_id=out["source_doc_id"]))
                if rule_src:
                    citations.append(_citation(rule_src, out["source_section"], None))
                verdict = "eligible" if out["result"] == "ELIGIBLE" else "not eligible"
                lines.append(f"{code}: attendance {out['attendance_pct']}%, {verdict} for the end-semester "
                             f"exam (required {threshold}, clause {out['source_section']}).")
                facts.append(f"Required attendance is {threshold}. Result: {verdict}.")
            else:
                lines.append(f"{code}: attendance {att.output['classes_attended']} of "
                             f"{att.output['classes_held']} classes = {att.output['attendance_pct']}%.")
        if len(missing) == len(codes):
            # Nothing to calculate from: say so, rather than present an empty calculation.
            return {"tool_results": results,
                    **_respond(state, AnswerType.NOT_FOUND,
                               "I could not find an attendance record for you in " + ", ".join(missing) + ".")}
        answer = " ".join(lines)
        note = ""
        if state["category"] == Category.MULTI_STEP:
            note = " This answer uses your current record only; it does not model a future exam result."
        return {
            "answer_type": AnswerType.CALCULATED,
            "answer": answer,
            "explanation": answer + note,
            "tool_results": results,
            "applied_rules": applied,
            "citations": citations,
            "facts": facts,
        }

    def retrieve_node(state: State) -> dict:
        chunks = retrieve(svc.store, svc.embedder, state["question"], svc.top_k, svc.min_score)
        if not chunks:
            return _respond(state, AnswerType.NOT_FOUND, NOT_FOUND)
        return {"chunks": chunks}

    def precedence_node(state: State) -> dict:
        chunks: list[Chunk] = state["chunks"]
        top = chunks[0]
        # candidates: the best chunk per (document, clause) that shares the top clause
        best: dict[tuple[str, str], Chunk] = {}
        for c in chunks:
            if c.section != top.section:
                continue
            key = (c.doc_id, c.section)
            if key not in best or c.score > best[key].score:
                best[key] = c
        candidates: list[Candidate] = []
        for (doc_id, section), c in best.items():
            src = _source(svc.conn, doc_id)
            if src is None:
                continue
            value = _rule_value(svc.conn, doc_id, section) or c.text
            candidates.append(Candidate(source=src, section=section, value=value, page=c.page))
        scope = _student_scope(svc.conn, state.get("header_id"))
        decision: PrecedenceDecision = resolve(candidates, state["as_of"], scope)
        conflicts = []
        if decision.superseded:
            conflicts.append(f"Superseded: {', '.join(decision.superseded)}")
        if decision.upcoming:
            conflicts.append("Upcoming, not yet in force: " +
                             ", ".join(f"{u.doc_id} from {u.effective_from}" for u in decision.upcoming))
        if decision.conflict:
            cites = [_citation(_source(svc.conn, s.doc_id), s.section, s.page) for s in decision.conflicting_sources]
            return {
                "answer_type": AnswerType.CONFLICT_FLAGGED,
                "answer": decision.reason,
                "explanation": decision.reason,
                "citations": cites,
                "conflicts": conflicts + [decision.reason],
                "decision": decision.reason,
            }
        if decision.winner is None:
            return {"answer_type": AnswerType.NOT_FOUND, "answer": NOT_FOUND,
                    "explanation": decision.reason, "conflicts": conflicts, "decision": decision.reason}
        winner_chunk = best[(decision.winner.doc_id, decision.winner.section)]
        value = decision.winner_value
        excerpt = winner_chunk.text[:300]
        answer = (f"Under {decision.winner.title}, clause {decision.winner.section}: "
                  f"{value if value and value != winner_chunk.text else excerpt}")
        facts = [f"Clause {decision.winner.section} of {decision.winner.title} (version {decision.winner.version}): "
                 f"{winner_chunk.text[:600]}"]
        return {
            "answer_type": AnswerType.RETRIEVED_FACT,
            "answer": answer,
            "explanation": decision.reason,
            "citations": [decision.winner],
            "conflicts": conflicts,
            "decision": decision.reason,
            "facts": facts,
            "applied_rules": [AppliedRule(rule_id=r[0], value=r[1], source_doc_id=decision.winner.doc_id)
                              for r in svc.conn.execute(
                                  "SELECT rule_id, value FROM rule_registry WHERE source_doc_id = ? "
                                  "AND source_section LIKE ?", (decision.winner.doc_id, f"%{top.section}%"))],
        }

    def audit(state: State) -> dict:
        answer_type = state.get("answer_type", AnswerType.NOT_FOUND)
        answer = state.get("answer", NOT_FOUND)
        explanation = state.get("explanation", answer)
        if state.get("facts") and answer_type in (AnswerType.CALCULATED, AnswerType.RETRIEVED_FACT):
            explanation = svc.gateway.explain(state["question"], state["facts"], explanation)
        latency = int((time.perf_counter() - state["started"]) * 1000)
        trace = state["trace_id"]
        sources = [{"doc_id": c.doc_id, "section": c.section, "score": round(c.score, 3)}
                   for c in state.get("chunks", [])]
        record = AuditRecord(
            trace_id=trace,
            timestamp=datetime.now(timezone.utc),
            student_id=state.get("header_id"),
            question_category=state.get("category"),
            sources_retrieved=sources,
            precedence_decision=state.get("decision", ""),
            tools_invoked=state.get("tool_results", []),
            answer_type=answer_type,
            model=svc.model_name,
            llm_calls=svc.gateway.stats.llm_calls,
            tokens=svc.gateway.stats.tokens,
            latency_ms=latency,
            fallbacks=list(svc.gateway.stats.fallbacks),
        )
        write_audit(svc.conn, record)
        response = AskResponse(
            trace_id=trace,
            answer=answer,
            answer_type=answer_type,
            citations=state.get("citations", []),
            tools_invoked=state.get("tool_results", []),
            applied_rules=state.get("applied_rules", []),
            conflicts_detected=state.get("conflicts", []),
            explanation=explanation,
            as_of_date=state["as_of"],
        )
        return {"response": response}

    return classify, authorise, tools, retrieve_node, precedence_node, audit


def build_graph(svc: Services):
    classify, authorise, tools, retrieve_node, precedence_node, audit = make_nodes(svc)
    g = StateGraph(State)
    g.add_node("classify", classify)
    g.add_node("authorise", authorise)
    g.add_node("tools", tools)
    g.add_node("retrieve", retrieve_node)
    g.add_node("precedence", precedence_node)
    g.add_node("audit", audit)

    g.set_entry_point("classify")
    g.add_edge("classify", "authorise")

    def after_authorise(state: State) -> str:
        if state.get("answer_type") is not None:  # refused or clarification
            return "audit"
        return "tools" if state["personal"] else "retrieve"

    g.add_conditional_edges("authorise", after_authorise,
                            {"audit": "audit", "tools": "tools", "retrieve": "retrieve"})

    def after_retrieve(state: State) -> str:
        return "audit" if state.get("answer_type") is not None else "precedence"

    g.add_conditional_edges("retrieve", after_retrieve, {"audit": "audit", "precedence": "precedence"})
    g.add_edge("tools", "audit")
    g.add_edge("precedence", "audit")
    g.add_edge("audit", END)
    return g.compile()


def ask(svc: Services, question: str, as_of: Optional[date], header_id: Optional[str]) -> AskResponse:
    graph = build_graph(svc)
    svc.gateway.stats = type(svc.gateway.stats)()  # reset per-request counters
    state: State = {
        "question": question,
        "as_of": as_of or date.today(),
        "header_id": header_id,
        "trace_id": secrets.token_hex(4),
        "started": time.perf_counter(),
    }
    final = graph.invoke(state)
    return final["response"]

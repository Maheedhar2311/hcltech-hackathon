"""Shared data contracts for every module (task T0.1).

Every module passes these models between itself and the others. Changing a
field here affects all members, so change it only by team agreement.

Sources:
- Guide section 6.1 (response format) and 6.2 (answer types)
- Guide Annex B (Source Register) and Annex D (audit record)
- docs/system_architecture.md section 6.2 (internal interfaces)
"""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Category(str, Enum):
    """Question category chosen by the classifier (guide section 2.1)."""

    POLICY = "policy"
    PROCEDURE = "procedure"
    PERSONAL_DATA = "personal_data"
    PERSONAL_ELIGIBILITY = "personal_eligibility"
    MULTI_STEP = "multi_step"
    OUT_OF_SCOPE = "out_of_scope"
    AMBIGUOUS = "ambiguous"


class AnswerType(str, Enum):
    """The six answer types (guide section 6.2)."""

    RETRIEVED_FACT = "retrieved_fact"
    CALCULATED = "calculated"
    NOT_FOUND = "not_found"
    CLARIFICATION_NEEDED = "clarification_needed"
    REFUSED = "refused"
    CONFLICT_FLAGGED = "conflict_flagged"


class ToolStatus(str, Enum):
    OK = "ok"
    ERROR = "error"


class EligibilityResult(str, Enum):
    ELIGIBLE = "ELIGIBLE"
    NOT_ELIGIBLE = "NOT_ELIGIBLE"
    UNCLEAR = "UNCLEAR"


class SourceMetadata(BaseModel):
    """One row of the Source Register (guide Annex B). Also the /ingest metadata."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    issuer: str = Field(min_length=1)
    authority_level: int = Field(ge=1, le=5)
    doc_type: str = Field(min_length=1)
    version: str = Field(min_length=1)
    effective_from: date
    effective_to: Optional[date] = None
    supersedes: Optional[str] = None
    scope_programmes: str = "ALL"
    scope_batches: str = "ALL"
    provenance: str = ""
    retrieved_on: Optional[date] = None
    synthetic: bool = False

    @field_validator("effective_to")
    @classmethod
    def _to_after_from(cls, value: Optional[date], info: Any) -> Optional[date]:
        start = info.data.get("effective_from")
        if value is not None and start is not None and value < start:
            raise ValueError("effective_to must not be before effective_from")
        return value


class AskRequest(BaseModel):
    """Body of POST /ask. The student ID is NOT in the body (it comes from the header)."""

    question: str = Field(min_length=1, max_length=2000)
    as_of_date: Optional[date] = None


class Chunk(BaseModel):
    """A retrieved passage with the metadata needed for precedence and citation."""

    doc_id: str
    section: str
    page: Optional[int] = None
    version: str
    effective_from: date
    effective_to: Optional[date] = None
    authority_level: int = Field(ge=1, le=5)
    scope_programmes: str = "ALL"
    scope_batches: str = "ALL"
    text: str
    score: float = 0.0


class Citation(BaseModel):
    """Where a fact came from (guide section 6.1)."""

    doc_id: str
    title: str
    section: str
    page: Optional[int] = None
    version: str
    effective_from: date


class ToolResult(BaseModel):
    """Output of one deterministic tool call (guide section 6.1, tools_invoked)."""

    tool: str = ""  # set by the tool layer (M3), which knows the tool's name
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    rule_id: Optional[str] = None
    status: ToolStatus = ToolStatus.OK
    error: Optional[str] = None
    ms: int = 0


class AppliedRule(BaseModel):
    """A rule the tools or precedence used (guide section 6.1, applied_rules)."""

    rule_id: str
    value: str
    source_doc_id: str


class PrecedenceDecision(BaseModel):
    """Output of the Annex A precedence engine."""

    winner: Optional[Citation] = None
    winner_value: Optional[str] = None  # added for M2: the value the winning clause states, e.g. "80%"
    superseded: list[str] = Field(default_factory=list)
    upcoming: list[Citation] = Field(default_factory=list)
    conflict: bool = False
    conflicting_sources: list[Citation] = Field(default_factory=list)
    reason: str = ""


class StudentContext(BaseModel):
    """The logged-in student, taken only from the X-Student-Id header."""

    student_id: str = Field(pattern=r"^S\d{4}$")


class AskResponse(BaseModel):
    """Response of POST /ask (guide section 6.1)."""

    trace_id: str
    answer: str
    answer_type: AnswerType
    citations: list[Citation] = Field(default_factory=list)
    tools_invoked: list[ToolResult] = Field(default_factory=list)
    applied_rules: list[AppliedRule] = Field(default_factory=list)
    conflicts_detected: list[str] = Field(default_factory=list)
    explanation: str = ""
    as_of_date: date


class AuditRecord(BaseModel):
    """Audit record for one request (guide Annex D)."""

    trace_id: str
    timestamp: datetime
    student_id: Optional[str] = None
    question_category: Optional[Category] = None
    sources_retrieved: list[dict[str, Any]] = Field(default_factory=list)
    precedence_decision: str = ""
    tools_invoked: list[ToolResult] = Field(default_factory=list)
    answer_type: AnswerType
    model: str = ""
    llm_calls: int = 0
    tokens: int = 0
    latency_ms: int = 0
    fallbacks: list[str] = Field(default_factory=list)


class IngestResult(BaseModel):
    """Response of POST /ingest."""

    doc_id: str
    chunks_indexed: int = Field(ge=0)
    status: str

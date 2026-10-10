"""Annex A precedence engine (tasks B3-B7).

Given the candidate clauses that bear on one question topic, decide which one
applies on `as_of`. The function is pure: the same inputs always give the
same decision, so it can be tested with fixtures and no model.

Resolution order (guide Annex A.2):
  1. Applicability: in force on as_of, and scope covers the student.
  2. Explicit supersession: a level 1 or 2 document that names a clause replaces it.
  3. Authority: the lowest level number wins. Level 5 never overrides.
  4. Recency: among the best authority, the latest effective_from wins.
  5. Unresolved: same authority, same effective date, different values -> conflict.

Assumption (not in the guide): when no student is given, the scope of each
document cannot be checked against a student. Such documents are considered,
and the reason notes which scope applies, so the reader can check it.
"""

from __future__ import annotations

import re
from datetime import date
from typing import Optional

from pydantic import BaseModel, Field

from app.contracts import Citation, PrecedenceDecision, SourceMetadata

SUPERSEDING_LEVELS = {1, 2}  # Annex A.2 step 2: only levels 1 and 2 can supersede
UNTRUSTED_LEVEL = 5  # Annex A.1: unofficial content, informational only


class StudentScope(BaseModel):
    """The student facts needed to check programme and batch scope."""

    programme: str = Field(min_length=1)
    batch_year: int


class Candidate(BaseModel):
    """One clause from one document that bears on the question's topic."""

    source: SourceMetadata
    section: str = Field(min_length=1)
    value: str
    page: Optional[int] = None


# ---------- scope (task B3) ----------

def _programme_in_scope(scope: str, programme: str) -> bool:
    scope = scope.strip()
    if scope == "ALL":
        return True
    return programme in [p.strip() for p in scope.split(",")]


def _batch_in_scope(scope: str, batch_year: int) -> bool:
    """Scope forms: ALL, 2023, 2023+, or a comma list such as 2022,2023+."""
    scope = scope.strip()
    if scope == "ALL":
        return True
    for part in (p.strip() for p in scope.split(",")):
        if part.endswith("+"):
            if not part[:-1].isdigit():
                raise ValueError(f"malformed batch scope: {scope!r}")
            if batch_year >= int(part[:-1]):
                return True
        elif part.isdigit():
            if batch_year == int(part):
                return True
        else:
            raise ValueError(f"malformed batch scope: {scope!r}")
    return False


def _scope_covers(source: SourceMetadata, student: Optional[StudentScope]) -> bool:
    if student is None:
        return True  # general question: scope cannot be checked, so the document is considered (noted in the reason)
    return _programme_in_scope(source.scope_programmes, student.programme) and _batch_in_scope(
        source.scope_batches, student.batch_year
    )


# ---------- supersession (task B4) ----------

def _names_clause(reference: str, target: Candidate) -> bool:
    """True if one entry of a `supersedes` value names this candidate.

    Entries look like "ACAD-REG-2024#7.2" (one clause) or "ACAD-REG-2024"
    (whole document). Several entries are separated by semicolons.
    """
    for entry in (e.strip() for e in reference.split(";")):
        if not entry:
            continue
        doc_id, _, section = entry.partition("#")
        if doc_id.strip() != target.source.doc_id:
            continue
        if section.strip() == "" or section.strip() == target.section:
            return True
    return False


def _superseded_by(target: Candidate, pool: list[Candidate]) -> bool:
    return any(
        other.source.authority_level in SUPERSEDING_LEVELS
        and other.source.supersedes
        and _names_clause(other.source.supersedes, target)
        for other in pool
    )


# ---------- helpers ----------

def _citation(c: Candidate) -> Citation:
    return Citation(
        doc_id=c.source.doc_id,
        title=c.source.title,
        section=c.section,
        page=c.page,
        version=c.source.version,
        effective_from=c.source.effective_from,
    )


def _label(c: Candidate) -> str:
    return f"{c.source.doc_id}#{c.section}"


# ---------- the engine ----------

def resolve(
    candidates: list[Candidate],
    as_of: date,
    student: Optional[StudentScope] = None,
) -> PrecedenceDecision:
    """Apply Annex A to the candidates for one topic and return the decision."""

    # Step 1: applicability (B3 and B7)
    in_scope: list[Candidate] = []
    upcoming: list[Citation] = []
    for c in candidates:
        if not _scope_covers(c.source, student):
            continue
        if c.source.effective_to is not None and c.source.effective_to < as_of:
            continue  # expired before as_of
        if c.source.effective_from > as_of:
            upcoming.append(_citation(c))  # not yet in force: mention, do not use
            continue
        in_scope.append(c)

    # Step 2: explicit supersession (B4)
    superseded: list[str] = []
    active: list[Candidate] = []
    for c in in_scope:
        if _superseded_by(c, in_scope):
            superseded.append(_label(c))
        else:
            active.append(c)

    if not active:
        return PrecedenceDecision(
            superseded=superseded,
            upcoming=upcoming,
            reason="No applicable source for this topic on the as-of date.",
        )

    # Step 3: unofficial content never overrides and is never the answer (B4)
    official = [c for c in active if c.source.authority_level < UNTRUSTED_LEVEL]
    if not official:
        return PrecedenceDecision(
            superseded=superseded,
            upcoming=upcoming,
            reason="Only unofficial (level 5) content applies. It is informational and cannot be the answer.",
        )

    best_level = min(c.source.authority_level for c in official)
    top = [c for c in official if c.source.authority_level == best_level]
    lower = [c for c in official if c.source.authority_level > best_level]

    # Step 4: recency among the best authority (B5)
    latest = max(c.source.effective_from for c in top)
    newest = sorted(
        (c for c in top if c.source.effective_from == latest),
        key=lambda c: c.source.doc_id,
    )

    distinct_values = {c.value for c in newest}
    if len(distinct_values) > 1:
        # Step 5: unresolved conflict. Report both sides; never pick silently.
        return PrecedenceDecision(
            winner=None,
            conflict=True,
            conflicting_sources=[_citation(c) for c in newest],
            superseded=superseded,
            upcoming=upcoming,
            reason=(
                f"Unresolved: {', '.join(_label(c) for c in newest)} have the same authority "
                f"(level {best_level}) and effective date {latest}, but state different values. "
                "Contact the issuing office."
            ),
        )

    winner = newest[0]
    notes = [f"{_label(winner)} applies (level {best_level}, effective {latest})."]
    if student is None and (
        winner.source.scope_programmes.strip() != "ALL" or winner.source.scope_batches.strip() != "ALL"
    ):
        notes.append(
            f"Scope: programmes {winner.source.scope_programmes}, batches {winner.source.scope_batches}. "
            "No student was given, so this was not checked against a student."
        )
    if len(top) > len(newest):
        notes.append("Older documents of the same authority were overruled by recency.")
    disagreeing = sorted({_label(c) for c in lower if c.value != winner.value})
    if disagreeing:
        notes.append(
            f"Lower-authority sources state a different value and cannot override: {', '.join(disagreeing)}."
        )

    return PrecedenceDecision(
        winner=_citation(winner),
        winner_value=winner.value,
        superseded=superseded,
        upcoming=upcoming,
        conflict=False,
        reason=" ".join(notes),
    )

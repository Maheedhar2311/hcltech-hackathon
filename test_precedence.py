"""Tests for the Annex A precedence engine (tasks B3-B7)."""

from datetime import date

import pytest

from app.contracts import SourceMetadata
from app.precedence.engine import Candidate, StudentScope, resolve


def src(doc_id, level, eff_from, eff_to=None, supersedes=None,
        programmes="ALL", batches="ALL"):
    return SourceMetadata(
        doc_id=doc_id,
        title=f"Title {doc_id}",
        issuer="Issuer",
        authority_level=level,
        doc_type="test",
        version="1.0",
        effective_from=eff_from,
        effective_to=eff_to,
        supersedes=supersedes,
        scope_programmes=programmes,
        scope_batches=batches,
    )


def cand(source, value, section="7.2"):
    return Candidate(source=source, section=section, value=value)


AS_OF = date(2026, 10, 6)
REG = src("ACAD-REG-2024", 1, date(2024, 7, 1))


# ---------- B6: the guide's worked example (Annex A.3) ----------

def worked_example():
    regulation = cand(REG, "75%", section="7.2")
    circular = cand(
        src("ACAD-2026-08", 2, date(2026, 8, 1), supersedes="ACAD-REG-2024#7.2"),
        "80%", section="1",
    )
    faq = cand(src("DEPT-FAQ-2026", 4, date(2026, 9, 15)), "65%", section="3")
    return [regulation, circular, faq]


def test_worked_example_circular_supersedes_regulation_clause():
    decision = resolve(worked_example(), as_of=AS_OF)
    assert decision.winner_value == "80%"
    assert decision.winner.doc_id == "ACAD-2026-08"
    assert "ACAD-REG-2024#7.2" in decision.superseded
    assert decision.conflict is False


def test_worked_example_faq_cannot_override_and_is_noted():
    decision = resolve(worked_example(), as_of=AS_OF)
    assert "DEPT-FAQ-2026" in decision.reason  # lower authority conflict is reported
    assert decision.winner.doc_id != "DEPT-FAQ-2026"


# ---------- B3 and B7: applicability and upcoming changes ----------

def test_before_circular_takes_effect_regulation_applies_and_circular_is_upcoming():
    decision = resolve(worked_example(), as_of=date(2026, 7, 15))
    # circular not yet effective: regulation applies, circular is mentioned as upcoming
    assert decision.winner_value == "75%"
    assert decision.winner.doc_id == "ACAD-REG-2024"
    # both the circular (Aug 2026) and the FAQ (Sep 2026) are not yet in force on this date
    assert {c.doc_id for c in decision.upcoming} == {"ACAD-2026-08", "DEPT-FAQ-2026"}


def test_expired_document_is_ignored():
    old = cand(src("OLD-REG", 1, date(2020, 1, 1), eff_to=date(2023, 12, 31)), "60%")
    decision = resolve([old], as_of=AS_OF)
    assert decision.winner is None
    assert decision.upcoming == []
    assert "No applicable source" in decision.reason


def test_effective_to_is_inclusive_on_as_of_date():
    doc = cand(src("LIMITED", 1, date(2024, 1, 1), eff_to=AS_OF), "70%")
    assert resolve([doc], as_of=AS_OF).winner_value == "70%"


# ---------- scope (B3) ----------

def test_programme_scope_excludes_other_programmes():
    mba_only = cand(src("MBA-RULE", 1, date(2024, 1, 1), programmes="MBA"), "70%")
    decision = resolve([mba_only], as_of=AS_OF, student=StudentScope(programme="B.Tech CSE", batch_year=2023))
    assert decision.winner is None


def test_batch_scope_with_plus_applies_from_that_year():
    rule = cand(src("NEW-BATCH", 1, date(2024, 1, 1), batches="2023+"), "75%")
    assert resolve([rule], as_of=AS_OF, student=StudentScope(programme="B.Tech CSE", batch_year=2023)).winner_value == "75%"
    assert resolve([rule], as_of=AS_OF, student=StudentScope(programme="B.Tech CSE", batch_year=2021)).winner is None


def test_no_student_considers_scoped_document_and_states_its_scope():
    # Without a student the scope cannot be checked, so the document still applies,
    # and the reason says which scope it has (so the reader can check it).
    scoped = cand(src("CSE-ONLY", 1, date(2024, 1, 1), programmes="B.Tech CSE", batches="2023+"), "70%")
    decision = resolve([scoped], as_of=AS_OF, student=None)
    assert decision.winner_value == "70%"
    assert "programmes B.Tech CSE" in decision.reason and "not checked" in decision.reason


def test_malformed_batch_scope_is_an_error():
    rule = cand(src("BAD-SCOPE", 1, date(2024, 1, 1), batches="twenty-three"), "75%")
    with pytest.raises(ValueError):
        resolve([rule], as_of=AS_OF, student=StudentScope(programme="B.Tech CSE", batch_year=2023))


# ---------- B4: supersession and authority ----------

def test_supersession_by_level_3_notice_is_not_allowed():
    notice = cand(
        src("DEPT-NOTICE", 3, date(2026, 8, 1), supersedes="ACAD-REG-2024#7.2"),
        "80%", section="1",
    )
    decision = resolve([cand(REG, "75%"), notice], as_of=AS_OF)
    assert decision.winner_value == "75%"  # regulation (level 1) prevails
    assert decision.superseded == []


def test_supersession_is_limited_to_the_named_clause():
    circular = cand(
        src("ACAD-2026-08", 2, date(2026, 8, 1), supersedes="ACAD-REG-2024#7.3"),
        "80%", section="1",
    )
    decision = resolve([cand(REG, "75%", section="7.2"), circular], as_of=AS_OF)
    assert decision.winner_value == "75%"  # 7.2 was not the clause superseded


def test_whole_document_supersession_removes_all_its_clauses():
    circular = cand(
        src("ACAD-2026-08", 2, date(2026, 8, 1), supersedes="ACAD-REG-2024"),
        "80%", section="1",
    )
    decision = resolve([cand(REG, "75%", section="7.2"), cand(REG, "72%", section="8.1"), circular], as_of=AS_OF)
    assert decision.winner_value == "80%"
    assert set(decision.superseded) == {"ACAD-REG-2024#7.2", "ACAD-REG-2024#8.1"}


def test_level_5_content_never_overrides_official_source():
    unofficial = cand(src("FORUM-POST", 5, date(2026, 9, 1)), "50%")
    decision = resolve([cand(REG, "75%"), unofficial], as_of=AS_OF)
    assert decision.winner_value == "75%"


def test_only_level_5_content_is_not_an_answer():
    decision = resolve([cand(src("FORUM-POST", 5, date(2026, 9, 1)), "50%")], as_of=AS_OF)
    assert decision.winner is None
    assert "informational" in decision.reason


# ---------- B5: recency and unresolved conflicts ----------

def test_same_authority_later_effective_date_wins():
    newer = cand(src("ACAD-REG-2025", 1, date(2025, 7, 1)), "80%")
    decision = resolve([cand(REG, "75%"), newer], as_of=AS_OF)
    assert decision.winner_value == "80%"
    assert decision.conflict is False


def test_same_authority_same_date_different_values_is_unresolved():
    a = cand(src("CIRC-A", 2, date(2026, 8, 1)), "80%")
    b = cand(src("CIRC-B", 2, date(2026, 8, 1)), "70%")
    decision = resolve([a, b], as_of=AS_OF)
    assert decision.conflict is True
    assert decision.winner is None
    assert {c.doc_id for c in decision.conflicting_sources} == {"CIRC-A", "CIRC-B"}


def test_same_authority_same_date_same_value_is_not_a_conflict():
    a = cand(src("CIRC-A", 2, date(2026, 8, 1)), "80%")
    b = cand(src("CIRC-B", 2, date(2026, 8, 1)), "80%")
    decision = resolve([a, b], as_of=AS_OF)
    assert decision.conflict is False
    assert decision.winner_value == "80%"


def test_no_candidates_gives_no_answer():
    decision = resolve([], as_of=AS_OF)
    assert decision.winner is None
    assert decision.conflict is False


def test_engine_is_deterministic_for_same_inputs():
    first = resolve(worked_example(), as_of=AS_OF).model_dump()
    second = resolve(worked_example(), as_of=AS_OF).model_dump()
    assert first == second

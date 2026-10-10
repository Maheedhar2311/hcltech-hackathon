"""Tests for the shared contracts (task T0.1)."""

from datetime import date

import pytest
from pydantic import ValidationError

from app.contracts import (
    AnswerType,
    AskRequest,
    AskResponse,
    Category,
    SourceMetadata,
    StudentContext,
)


def valid_metadata(**overrides):
    data = dict(
        doc_id="ACAD-REG-2024",
        title="Academic Regulations",
        issuer="Office of the Dean (Academics)",
        authority_level=1,
        doc_type="regulation",
        version="3.1",
        effective_from=date(2024, 7, 1),
        scope_programmes="ALL",
        scope_batches="ALL",
    )
    data.update(overrides)
    return data


def test_source_metadata_accepts_valid_row():
    meta = SourceMetadata(**valid_metadata())
    assert meta.authority_level == 1
    assert meta.synthetic is False


@pytest.mark.parametrize("level", [0, 6])
def test_authority_level_must_be_1_to_5(level):
    with pytest.raises(ValidationError):
        SourceMetadata(**valid_metadata(authority_level=level))


def test_effective_to_before_effective_from_is_rejected():
    with pytest.raises(ValidationError):
        SourceMetadata(**valid_metadata(effective_to=date(2024, 1, 1)))


def test_source_metadata_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        SourceMetadata(**valid_metadata(unexpected="x"))


def test_ask_request_has_no_student_id_field():
    # The student ID comes from the X-Student-Id header, never from the body.
    assert "student_id" not in AskRequest.model_fields


def test_ask_request_rejects_empty_question():
    with pytest.raises(ValidationError):
        AskRequest(question="")


def test_student_context_requires_guide_id_format():
    assert StudentContext(student_id="S1001").student_id == "S1001"
    with pytest.raises(ValidationError):
        StudentContext(student_id="1001")


def test_answer_types_match_guide_section_6_2():
    assert {t.value for t in AnswerType} == {
        "retrieved_fact",
        "calculated",
        "not_found",
        "clarification_needed",
        "refused",
        "conflict_flagged",
    }


def test_categories_cover_guide_question_types():
    assert {c.value for c in Category} >= {
        "policy",
        "procedure",
        "personal_data",
        "personal_eligibility",
        "multi_step",
    }


def test_ask_response_serialises_with_guide_field_names():
    response = AskResponse(
        trace_id="7f3c2a9e",
        answer="I could not find this information in the authorised university sources.",
        answer_type=AnswerType.NOT_FOUND,
        as_of_date=date(2026, 10, 6),
    )
    body = response.model_dump(mode="json")
    for field in (
        "trace_id",
        "answer",
        "answer_type",
        "citations",
        "tools_invoked",
        "applied_rules",
        "conflicts_detected",
        "explanation",
        "as_of_date",
    ):
        assert field in body
    assert body["answer_type"] == "not_found"

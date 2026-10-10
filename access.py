"""Access check for student data (task C6', guide R7).

Decides whether a request may use student data at all. The student's identity
is the X-Student-Id header only. This function never takes an identity from the
question text, but it does refuse a question that names another student's ID.
"""

from __future__ import annotations

import re
from typing import Optional

from app.contracts import AnswerType

STUDENT_ID_IN_TEXT = re.compile(r"\bS\d{4}\b")
VALID_HEADER = re.compile(r"^S\d{4}$")

REFUSAL_NO_IDENTITY = "I need your student ID to answer questions about your own record."
REFUSAL_OTHER_STUDENT = "I can only share information about the student who is logged in."


def check_access(
    header_student_id: Optional[str], question: str, personal: bool
) -> Optional[AnswerType]:
    """Return REFUSED if the request must not proceed, or None if it may.

    `personal` is True when the question needs student records. General policy
    questions can be answered without an identity.
    """
    return AnswerType.REFUSED if refusal_message(header_student_id, question, personal) else None


def refusal_message(header_student_id: Optional[str], question: str, personal: bool) -> Optional[str]:
    """Return the user-facing refusal text for the same cases, or None if allowed."""
    if header_student_id is None and personal:
        return REFUSAL_NO_IDENTITY
    if header_student_id is not None and not VALID_HEADER.match(header_student_id):
        return REFUSAL_NO_IDENTITY
    if header_student_id is not None and set(STUDENT_ID_IN_TEXT.findall(question)) - {header_student_id}:
        return REFUSAL_OTHER_STUDENT
    return None

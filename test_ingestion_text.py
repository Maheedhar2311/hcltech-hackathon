"""Tests for text parsing, chunking and the hash embedder (tasks A2, A3, A4 plumbing)."""

import pytest

from app.ingestion.chunk import MAX_WORDS, chunk_pages
from app.ingestion.parse import ParseError, Page, parse_bytes
from app.retrieval.embedder import HashEmbedder


def test_plain_text_becomes_one_page():
    pages = parse_bytes(b"Minimum attendance is 75 percent for the end-semester exam.", "rules.txt")
    assert len(pages) == 1 and pages[0].number == 1


def test_empty_file_is_rejected_as_no_text():
    with pytest.raises(ParseError, match="no extractable text"):
        parse_bytes(b"   ", "empty.txt")


def test_unsupported_type_is_rejected():
    with pytest.raises(ParseError, match="unsupported file type"):
        parse_bytes(b"x", "notes.docx")


def test_bad_pdf_bytes_are_rejected_with_message():
    with pytest.raises(ParseError, match="cannot read PDF"):
        parse_bytes(b"%PDF-not-really", "broken.pdf")


def test_chunks_respect_word_limit_and_keep_page_numbers():
    words = " ".join(f"w{i}" for i in range(400))
    chunks = chunk_pages([Page(1, words), Page(2, "short page text here")])
    assert all(len(c.text.split()) <= MAX_WORDS for c in chunks)
    assert {c.page for c in chunks} == {1, 2}
    # a 400-word page with 130-word steps needs more than one chunk
    assert sum(1 for c in chunks if c.page == 1) >= 3


def test_chunks_overlap_so_text_is_not_lost_at_boundaries():
    words = [f"w{i}" for i in range(300)]
    chunks = chunk_pages([Page(1, " ".join(words))])
    first, second = chunks[0].text.split(), chunks[1].text.split()
    assert first[-20:] == second[:20]


def test_section_comes_from_first_clause_number():
    text = "Preamble text. R8.2 A student with less than 75% attendance will be awarded L grade."
    chunks = chunk_pages([Page(7, text)])
    assert chunks[0].section == "R8.2"


def test_section_falls_back_to_page_when_no_clause():
    chunks = chunk_pages([Page(3, "This page has no numbered clause at all in it.")])
    assert chunks[0].section == "p3"


def test_hash_embedder_is_deterministic_and_normalised():
    emb = HashEmbedder(dim=64)
    a = emb.embed(["minimum attendance 75"])[0]
    b = emb.embed(["minimum attendance 75"])[0]
    assert a == b
    assert abs(sum(v * v for v in a) - 1.0) < 1e-9


def test_hash_embedder_scores_overlapping_text_higher():
    emb = HashEmbedder(dim=256)
    q, near, far = emb.embed([
        "minimum attendance for exam",
        "attendance required for the exam",
        "hostel mess food timings",
    ])
    dot = lambda x, y: sum(i * j for i, j in zip(x, y))  # noqa: E731
    assert dot(q, near) > dot(q, far)

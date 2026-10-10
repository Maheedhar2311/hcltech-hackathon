"""Chunking (task A3).

Splits each page into passages of at most MAX_WORDS words, with a small overlap,
so every chunk stays under the embedding model's 256-token limit (research S5).
Each chunk keeps:
- page: the page it came from
- section: the first clause number on the chunk (for example "R8.2" or "O.3"),
  or "p<page>" when the text has no clause number

Clause numbers are what citations and precedence refer to (guide R2, Annex A).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.ingestion.parse import Page

MAX_WORDS = 150
OVERLAP_WORDS = 20

# Clause numbers used in the university documents: R8.1, R13.3, O.3, 7.2 ...
CLAUSE = re.compile(r"\b(?:R\d{1,2}\.\d{1,2}|O\.\d{1,2}|\d{1,2}\.\d{1,2})\b")


@dataclass
class TextChunk:
    page: int
    section: str
    index: int  # position within the document, 0-based
    text: str


def _section_for(text: str, page: int) -> str:
    match = CLAUSE.search(text)
    return match.group(0) if match else f"p{page}"


def chunk_pages(pages: list[Page], max_words: int = MAX_WORDS, overlap: int = OVERLAP_WORDS) -> list[TextChunk]:
    if max_words <= overlap:
        raise ValueError("max_words must be larger than overlap")
    chunks: list[TextChunk] = []
    for page in pages:
        words = page.text.split()
        if not words:
            continue
        step = max_words - overlap
        for start in range(0, len(words), step):
            piece = " ".join(words[start:start + max_words])
            chunks.append(TextChunk(page=page.number, section=_section_for(piece, page.number),
                                    index=len(chunks), text=piece))
            if start + max_words >= len(words):
                break
    return chunks

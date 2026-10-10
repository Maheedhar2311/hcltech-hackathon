"""Text extraction for ingestion (task A2).

Returns a list of pages, each with its page number and text. Supports text PDFs
(via pypdf) and plain text files. A document with no extractable text (for
example a scanned PDF) is rejected with an error, not indexed as empty.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path


class ParseError(ValueError):
    """The file cannot be turned into text that the system can use."""


@dataclass
class Page:
    number: int  # 1-based
    text: str


MIN_TEXT_CHARS = 20  # below this a document is treated as having no text layer


def parse_bytes(data: bytes, filename: str) -> list[Page]:
    suffix = Path(filename).suffix.lower()
    if suffix == ".pdf":
        pages = _parse_pdf(data)
    elif suffix in {".txt", ".md"}:
        pages = [Page(1, data.decode("utf-8", errors="replace"))]
    else:
        raise ParseError(f"unsupported file type {suffix!r}; use PDF or TXT")

    total = sum(len(p.text.strip()) for p in pages)
    if total < MIN_TEXT_CHARS:
        raise ParseError("no extractable text (scanned or empty file); OCR is out of scope")
    return pages


def _parse_pdf(data: bytes) -> list[Page]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - only if the venv is incomplete
        raise ParseError("pypdf is not installed") from exc
    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:  # corrupt or encrypted file
        raise ParseError(f"cannot read PDF: {exc}") from exc
    return [Page(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]

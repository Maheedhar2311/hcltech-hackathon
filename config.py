"""Settings, read from environment variables (see .env.example). No secrets are stored here."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _bool(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class Settings:
    sqlite_path: Path
    chroma_path: Path
    mock_llm: bool
    ollama_base_url: str
    ollama_model: str
    embed_model: str
    top_k: int
    min_score: float


def load_settings() -> Settings:
    return Settings(
        sqlite_path=Path(os.environ.get("SQLITE_PATH", ROOT / "data" / "app.sqlite3")),
        chroma_path=Path(os.environ.get("CHROMA_PATH", ROOT / "data" / "chroma")),
        mock_llm=_bool("MOCK_LLM", True),
        ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434"),
        ollama_model=os.environ.get("OLLAMA_MODEL", "qwen2.5:7b"),
        embed_model=os.environ.get("EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2"),
        top_k=int(os.environ.get("TOP_K", "5")),
        # 0.25 suits the MOCK hash embedder. For MiniLM, two checks gave 0.71 for a relevant question and
        # 0.38 for an unrelated one, so 0.5 is a provisional live default until the evaluation sets it.
        min_score=float(os.environ.get("MIN_SCORE", "0.25" if _bool("MOCK_LLM", True) else "0.5")),
    )

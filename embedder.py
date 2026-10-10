"""Embedders (task A4).

Two implementations behind one interface:
- SentenceTransformerEmbedder: the model from the guide (default all-MiniLM-L6-v2,
  384 dimensions, research S5). Loaded only when first used.
- HashEmbedder: deterministic bag-of-words hashing. No model, no download.
  Used by tests and by MOCK mode. It finds word overlap, not meaning, so it is
  for plumbing checks, not for the evaluation.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

_WORD = re.compile(r"[a-z0-9]+")
# Common function words carry no topic. Without removing them, every question matches every chunk.
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "do", "does", "for", "from", "has", "have",
    "how", "i", "if", "in", "is", "it", "me", "my", "of", "on", "or", "that", "the", "their", "there",
    "this", "to", "was", "what", "when", "where", "which", "who", "will", "with", "would", "you", "your",
    "am", "should", "about", "any", "under", "than", "then", "also", "not", "no", "yes",
}


class Embedder(Protocol):
    name: str
    dim: int

    def embed(self, texts: list[str]) -> list[list[float]]: ...


class HashEmbedder:
    """Deterministic embeddings from word hashes. Same text always gives the same vector."""

    def __init__(self, dim: int = 256):
        self.dim = dim
        self.name = f"hash-{dim}"

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for word in _WORD.findall(text.lower()):
            if word in STOPWORDS:
                continue
            bucket = int(hashlib.sha256(word.encode("utf-8")).hexdigest(), 16) % self.dim
            vec[bucket] += 1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]


class SentenceTransformerEmbedder:
    """The model named in the guide. Import and model load happen on first use."""

    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        self.model_name = model_name
        self.name = model_name
        self._model = None
        self.dim = 384

    def _load(self):
        if self._model is None:
            from sentence_transformers import SentenceTransformer  # heavy import, kept lazy

            # CPU on purpose: the 7B language model already uses the GPU memory on Apple machines,
            # and the embedder ran out of GPU memory during evaluation.
            self._model = SentenceTransformer(self.model_name, device="cpu")
        return self._model

    def embed(self, texts: list[str]) -> list[list[float]]:
        vectors = self._load().encode(texts, normalize_embeddings=True)
        return [list(map(float, v)) for v in vectors]

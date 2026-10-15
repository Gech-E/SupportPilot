"""Text embedding service.

Provides a unified interface for generating vector embeddings of documents and search queries,
with deterministic mock embeddings for offline testing/evals and external provider support.
"""

from __future__ import annotations

import hashlib
import math
import re
from typing import Protocol

from app.core.config import get_settings
from app.models.chunk import VECTOR_DIMENSIONS

_WORD_SPLIT_RE = re.compile(r"\w+", re.UNICODE)


class Embedder(Protocol):
    """Protocol for embedding generation."""

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for a list of document chunks."""
        ...

    async def embed_query(self, text: str) -> list[float]:
        """Generate embedding for a single search query."""
        ...


class MockEmbedder:
    """Deterministic, high-quality mock embedder for tests, local dev, and evaluations.

    Uses hashed n-gram projections into a unit sphere of dimension `VECTOR_DIMENSIONS`.
    Produces reproducible embeddings where texts sharing tokens have high cosine similarity.
    """

    def __init__(self, dimensions: int = VECTOR_DIMENSIONS) -> None:
        self.dimensions = dimensions

    def _embed_single(self, text: str) -> list[float]:
        tokens = [token.lower() for token in _WORD_SPLIT_RE.findall(text)]
        if not tokens:
            # Deterministic fallback unit vector for empty input
            vec = [0.0] * self.dimensions
            vec[0] = 1.0
            return vec

        # Accumulator for feature hashing
        vector = [0.0] * self.dimensions

        # Unigrams and bigrams
        features: list[str] = list(tokens)
        for i in range(len(tokens) - 1):
            features.append(f"{tokens[i]}_{tokens[i + 1]}")

        for feature in features:
            h = int(hashlib.sha256(feature.encode("utf-8")).hexdigest(), 16)
            dim = h % self.dimensions
            sign = 1.0 if ((h >> 16) & 1) == 1 else -1.0
            vector[dim] += sign

        # Compute Euclidean (L2) norm
        norm = math.sqrt(sum(v * v for v in vector))
        if norm < 1e-9:
            vector[0] = 1.0
            return vector

        return [round(v / norm, 6) for v in vector]

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._embed_single(text) for text in texts]

    async def embed_query(self, text: str) -> list[float]:
        return self._embed_single(text)


def get_embedder(provider: str | None = None) -> Embedder:
    """Return configured embedder instance."""
    if provider is not None:
        chosen_provider = provider
    else:
        try:
            settings = get_settings()
            chosen_provider = settings.embedding_provider
        except Exception:
            chosen_provider = "mock"

    if chosen_provider == "mock":
        return MockEmbedder()

    # Fallback to MockEmbedder for unsupported or test environments
    return MockEmbedder()

import math

import pytest

from app.models.chunk import VECTOR_DIMENSIONS
from app.services.embeddings import MockEmbedder, get_embedder


def _cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    dot = sum(a * b for a, b in zip(vec_a, vec_b, strict=True))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


@pytest.mark.asyncio
async def test_mock_embedder_dimensions_and_norm() -> None:
    embedder = MockEmbedder()
    vec = await embedder.embed_query("SupportPilot multi-tenant AI support")
    assert len(vec) == VECTOR_DIMENSIONS

    norm = math.sqrt(sum(x * x for x in vec))
    assert abs(norm - 1.0) < 1e-4


@pytest.mark.asyncio
async def test_mock_embedder_empty_input() -> None:
    embedder = MockEmbedder()
    vec = await embedder.embed_query("")
    assert len(vec) == VECTOR_DIMENSIONS
    assert vec[0] == 1.0
    assert sum(abs(x) for x in vec[1:]) == 0.0


@pytest.mark.asyncio
async def test_mock_embedder_determinism() -> None:
    embedder = MockEmbedder()
    text = "Resetting your password requires your email address."
    vec1 = await embedder.embed_query(text)
    vec2 = await embedder.embed_query(text)
    assert vec1 == vec2


@pytest.mark.asyncio
async def test_mock_embedder_semantic_similarity() -> None:
    embedder = MockEmbedder()
    q = "How do I reset my password?"
    doc_similar = "Instructions for how to reset your account password."
    doc_unrelated = "Our datacenter uses solar and wind renewable energy."

    vec_q = await embedder.embed_query(q)
    vec_sim = await embedder.embed_query(doc_similar)
    vec_unrel = await embedder.embed_query(doc_unrelated)

    sim_high = _cosine_similarity(vec_q, vec_sim)
    sim_low = _cosine_similarity(vec_q, vec_unrel)

    assert sim_high > sim_low
    assert sim_high > 0.2


@pytest.mark.asyncio
async def test_mock_embedder_batch_embedding() -> None:
    embedder = MockEmbedder()
    texts = [
        "First chunk of documentation.",
        "Second chunk of documentation.",
        "Third chunk with completely different keywords.",
    ]
    vecs = await embedder.embed_texts(texts)
    assert len(vecs) == 3
    for v in vecs:
        assert len(v) == VECTOR_DIMENSIONS
        norm = math.sqrt(sum(x * x for x in v))
        assert abs(norm - 1.0) < 1e-4


def test_get_embedder_factory() -> None:
    embedder = get_embedder("mock")
    assert isinstance(embedder, MockEmbedder)

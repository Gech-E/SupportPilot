from app.services.chunker import chunk_text, estimate_tokens


def test_estimate_tokens_empty() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("   ") == 0


def test_estimate_tokens_sample_text() -> None:
    text = "SupportPilot is an AI customer support platform with multi-tenant isolation."
    tokens = estimate_tokens(text)
    assert 5 <= tokens <= 30


def test_chunk_text_empty() -> None:
    assert chunk_text("") == []
    assert chunk_text("   \n\n   ") == []


def test_chunk_text_single_short_document() -> None:
    short_text = "SupportPilot answers customer queries using retrieval augmented generation."
    chunks = chunk_text(short_text, chunk_size_tokens=100)
    assert len(chunks) == 1
    assert chunks[0].chunk_index == 0
    assert chunks[0].content == short_text
    assert chunks[0].token_count > 0


def test_chunk_text_splits_on_paragraphs() -> None:
    p1 = "Paragraph 1: " + "Information about password resets. " * 30
    p2 = "Paragraph 2: " + "Details about billing and subscription upgrades. " * 30
    full_text = f"{p1}\n\n{p2}"

    chunks = chunk_text(full_text, chunk_size_tokens=100, overlap_tokens=20)
    assert len(chunks) >= 2
    for i, c in enumerate(chunks):
        assert c.chunk_index == i
        assert len(c.content.strip()) > 0
        assert c.token_count > 0


def test_chunk_text_overlap() -> None:
    sentences = [f"Sentence number {i} with factual content." for i in range(50)]
    full_text = " ".join(sentences)

    chunks = chunk_text(full_text, chunk_size_tokens=50, overlap_tokens=15)
    assert len(chunks) > 1
    # Check consecutive chunks for sequential indices
    for i in range(len(chunks) - 1):
        assert chunks[i].chunk_index == i
        assert chunks[i + 1].chunk_index == i + 1

"""Recursive character text chunker.

Splits text hierarchically across paragraph boundaries, sentences, and words to maintain
coherent semantic units while enforcing maximum chunk size and overlap constraints.
"""

from dataclasses import dataclass
from typing import Final

DEFAULT_CHUNK_SIZE_TOKENS: Final[int] = 400
DEFAULT_CHUNK_OVERLAP_TOKENS: Final[int] = 50
CHARS_PER_TOKEN: Final[float] = 4.0


@dataclass(frozen=True)
class Chunk:
    chunk_index: int
    content: str
    token_count: int


def estimate_tokens(text: str) -> int:
    """Estimate token count based on whitespace words and character length."""
    stripped = text.strip()
    if not stripped:
        return 0
    # Heuristic blend of word count and character length
    words = len(stripped.split())
    by_chars = max(1, int(len(stripped) / CHARS_PER_TOKEN))
    # Blend: standard English tokens are ~1.3 tokens per word or ~4 chars per token
    return max(1, int(0.7 * (words * 1.3) + 0.3 * by_chars))


def chunk_text(
    text: str,
    *,
    chunk_size_tokens: int = DEFAULT_CHUNK_SIZE_TOKENS,
    overlap_tokens: int = DEFAULT_CHUNK_OVERLAP_TOKENS,
) -> list[Chunk]:
    """Split text recursively into overlapping chunks respecting natural boundaries.

    Separators tried in order:
    1. Double newline (paragraphs)
    2. Single newline (lines / lists)
    3. Sentence terminators (. ! ?)
    4. Spaces (words)
    5. Characters (hard fallback)
    """
    clean_text = text.strip()
    if not clean_text:
        return []

    target_chars = int(chunk_size_tokens * CHARS_PER_TOKEN)
    overlap_chars = int(overlap_tokens * CHARS_PER_TOKEN)

    if len(clean_text) <= target_chars:
        return [Chunk(chunk_index=0, content=clean_text, token_count=estimate_tokens(clean_text))]

    raw_chunks = _split_recursive(clean_text, target_chars, overlap_chars)
    return [
        Chunk(chunk_index=i, content=content, token_count=estimate_tokens(content))
        for i, content in enumerate(raw_chunks)
        if content.strip()
    ]


def _split_recursive(text: str, target_chars: int, overlap_chars: int) -> list[str]:
    separators = ["\n\n", "\n", ". ", "? ", "! ", " ", ""]
    return _split_with_separators(text, target_chars, overlap_chars, separators)


def _split_with_separators(
    text: str, target_chars: int, overlap_chars: int, separators: list[str]
) -> list[str]:
    if len(text) <= target_chars or not separators:
        return [text.strip()] if text.strip() else []

    separator = separators[0]
    next_separators = separators[1:]

    if separator == "":
        # Hard character slice when no separator works
        splits = [text[i : i + target_chars] for i in range(0, len(text), target_chars)]
        return [s.strip() for s in splits if s.strip()]

    parts = text.split(separator)
    if len(parts) == 1:
        return _split_with_separators(text, target_chars, overlap_chars, next_separators)

    chunks: list[str] = []
    current_parts: list[str] = []
    current_len = 0

    for part in parts:
        part_len = len(part) + len(separator)
        if current_len + part_len > target_chars and current_parts:
            chunk_content = separator.join(current_parts).strip()
            if chunk_content:
                chunks.append(chunk_content)

            # Keep overlapping tail
            overlap_parts: list[str] = []
            overlap_accum = 0
            for p in reversed(current_parts):
                if overlap_accum + len(p) + len(separator) <= overlap_chars:
                    overlap_parts.insert(0, p)
                    overlap_accum += len(p) + len(separator)
                else:
                    break
            current_parts = overlap_parts
            current_len = overlap_accum

        # If a single part is itself larger than target_chars, recurse with next separator
        if len(part) > target_chars:
            if current_parts:
                chunk_content = separator.join(current_parts).strip()
                if chunk_content:
                    chunks.append(chunk_content)
                current_parts = []
                current_len = 0
            sub_chunks = _split_with_separators(part, target_chars, overlap_chars, next_separators)
            chunks.extend(sub_chunks)
        else:
            current_parts.append(part)
            current_len += part_len

    if current_parts:
        last_content = separator.join(current_parts).strip()
        if last_content and (not chunks or last_content != chunks[-1]):
            chunks.append(last_content)

    return chunks

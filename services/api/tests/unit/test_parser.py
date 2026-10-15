import io

import pytest
from pypdf import PdfWriter

from app.core.errors import BadRequestError
from app.services.parser import MAX_DOCUMENT_BYTES, parse_document, sanitize_text


def _create_minimal_pdf_bytes(text: str = "") -> bytes:
    buffer = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    # If text is provided, we can either leave blank or add annotations
    # pypdf PdfWriter can write a clean empty page or basic PDF structure
    writer.write(buffer)
    return buffer.getvalue()


def test_sanitize_text_strips_null_and_control_chars() -> None:
    raw = "Hello\x00 world!\x07 How are\x1b you?\n\n\n\nGood."
    cleaned = sanitize_text(raw)
    assert "\x00" not in cleaned
    assert "\x07" not in cleaned
    assert "\x1b" not in cleaned
    assert cleaned == "Hello  world!  How are  you?\n\nGood."


def test_parse_plain_text_success() -> None:
    content = b"This is a user guide.\nIt explains how to reset passwords."
    result = parse_document(content, "text/plain", "guide.txt")
    assert "user guide" in result
    assert "reset passwords" in result


def test_parse_markdown_success() -> None:
    content = b"# API Documentation\n\n## Overview\nThis is markdown text."
    result = parse_document(content, "text/markdown", "readme.md")
    assert "# API Documentation" in result
    assert "## Overview" in result


def test_parse_by_filename_fallback() -> None:
    content = b"Knowledge base article."
    result = parse_document(content, "application/octet-stream", "kb.md")
    assert result == "Knowledge base article."


def test_parse_rejects_empty_document() -> None:
    with pytest.raises(BadRequestError, match="Document is empty"):
        parse_document(b"", "text/plain", "empty.txt")


def test_parse_rejects_oversized_document() -> None:
    oversized = b"a" * (MAX_DOCUMENT_BYTES + 1)
    with pytest.raises(BadRequestError, match="exceeds maximum size"):
        parse_document(oversized, "text/plain", "huge.txt")


def test_parse_rejects_unsupported_format() -> None:
    with pytest.raises(BadRequestError, match="Unsupported content type"):
        parse_document(b"binary data", "application/zip", "archive.zip")


def test_parse_pdf_empty_text_raises_error() -> None:
    pdf_bytes = _create_minimal_pdf_bytes()
    with pytest.raises(BadRequestError, match="contains no extractable text"):
        parse_document(pdf_bytes, "application/pdf", "empty.pdf")


def test_parse_corrupt_pdf_raises_error() -> None:
    corrupt_bytes = b"%PDF-1.4 corrupt header and garbage data 12345"
    with pytest.raises(BadRequestError, match=r"Failed to parse PDF document|Malformed or corrupt"):
        parse_document(corrupt_bytes, "application/pdf", "corrupt.pdf")

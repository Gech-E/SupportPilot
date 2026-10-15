"""Document parsing service: extracts clean text from supported document types.

Supported formats:
- Plain text (text/plain)
- Markdown (text/markdown, text/x-markdown)
- PDF (application/pdf)

Security constraints:
- Max document size limit: 10MB
- Null byte and control character sanitization
- Robust decoding (UTF-8 with fallbacks)
"""

import io
import re
from typing import Final

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from app.core.errors import BadRequestError

MAX_DOCUMENT_BYTES: Final[int] = 10 * 1024 * 1024  # 10 MB

SUPPORTED_MIME_TYPES: Final[set[str]] = {
    "text/plain",
    "text/markdown",
    "text/x-markdown",
    "application/pdf",
}

_NULL_OR_CONTROL_RE = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]")


def sanitize_text(text: str) -> str:
    """Strip null bytes, non-printable control characters, and normalize whitespace."""
    cleaned = _NULL_OR_CONTROL_RE.sub(" ", text)
    # Normalize excessive blank lines to max 2
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def parse_document(content: bytes, content_type: str, filename: str) -> str:
    """Extract plain text from document content bytes.

    Raises BadRequestError on invalid formats, oversized content, or unextractable text.
    """
    if len(content) == 0:
        raise BadRequestError("Document is empty.")

    if len(content) > MAX_DOCUMENT_BYTES:
        raise BadRequestError("Document exceeds maximum size of 10MB.")

    normalized_type = content_type.lower().split(";")[0].strip()
    if normalized_type not in SUPPORTED_MIME_TYPES:
        # Fallback check by filename extension
        lower_name = filename.lower()
        if lower_name.endswith((".txt", ".text")):
            normalized_type = "text/plain"
        elif lower_name.endswith((".md", ".markdown")):
            normalized_type = "text/markdown"
        elif lower_name.endswith(".pdf"):
            normalized_type = "application/pdf"
        else:
            raise BadRequestError(
                f"Unsupported content type '{content_type}'. Supported: plain text, markdown, PDF."
            )

    if normalized_type in ("text/plain", "text/markdown", "text/x-markdown"):
        try:
            raw_text = content.decode("utf-8")
        except UnicodeDecodeError:
            try:
                raw_text = content.decode("latin-1")
            except Exception as exc:
                raise BadRequestError("Unable to decode text document encoding.") from exc
    elif normalized_type == "application/pdf":
        raw_text = _extract_pdf_text(content)
    else:
        raise BadRequestError(f"Unsupported content type '{content_type}'.")

    sanitized = sanitize_text(raw_text)
    if not sanitized:
        raise BadRequestError("Document contains no extractable text.")

    return sanitized


def _extract_pdf_text(content: bytes) -> str:
    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            try:
                reader.decrypt("")
            except Exception as exc:
                raise BadRequestError(
                    "Password-protected PDF documents are not supported."
                ) from exc

        pages_text: list[str] = []
        for page in reader.pages:
            page_text = page.extract_text() or ""
            if page_text.strip():
                pages_text.append(page_text.strip())

        return "\n\n".join(pages_text)
    except PyPdfError as exc:
        raise BadRequestError(f"Malformed or corrupt PDF document: {exc}") from exc
    except Exception as exc:
        raise BadRequestError("Failed to parse PDF document.") from exc

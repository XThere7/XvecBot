"""
ingestion/chunker.py
Splits page text into overlapping chunks using a word-based sliding window.
Each chunk retains its source page number — this is what powers citations.

Strategy:
  - Split on whitespace (word tokens)
  - Slide a window of CHUNK_SIZE tokens forward by (CHUNK_SIZE - CHUNK_OVERLAP)
  - Each chunk joins its tokens back to a string
  - Very short pages that produce zero full chunks still emit one chunk with
    whatever text they have (avoids data loss)
"""
from dataclasses import dataclass

from ..core.config import settings
from ..core.logging import get_logger
from .pdf_loader import PageContent

log = get_logger(__name__)


@dataclass
class TextChunk:
    """A single text chunk ready for embedding."""
    page: int
    chunk_index: int      # position within the page, 0-indexed
    text: str


def chunk_page(page: PageContent) -> list[TextChunk]:
    """
    Produce overlapping chunks from a single PDF page.
    Uses token (word) count rather than character count for consistent sizing.
    """
    tokens = page.text.split()
    step = settings.chunk_size - settings.chunk_overlap

    if len(tokens) <= settings.chunk_size:
        # Page is shorter than one chunk — emit as-is
        return [TextChunk(page=page.page_number, chunk_index=0, text=page.text)]

    chunks: list[TextChunk] = []
    start = 0
    idx = 0

    while start < len(tokens):
        end = min(start + settings.chunk_size, len(tokens))
        chunk_tokens = tokens[start:end]
        text = " ".join(chunk_tokens)
        chunks.append(TextChunk(page=page.page_number, chunk_index=idx, text=text))
        idx += 1
        start += step

    log.debug(
        "Page chunked",
        page=page.page_number,
        token_count=len(tokens),
        chunks_produced=len(chunks),
    )
    return chunks


def chunk_document(pages: list[PageContent]) -> list[TextChunk]:
    """
    Chunk all pages of a document.
    Returns a flat list of TextChunk objects preserving page provenance.
    """
    all_chunks: list[TextChunk] = []
    for page in pages:
        all_chunks.extend(chunk_page(page))

    log.info(
        "Document chunked",
        total_pages=len(pages),
        total_chunks=len(all_chunks),
    )
    return all_chunks

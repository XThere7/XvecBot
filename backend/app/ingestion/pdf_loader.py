"""
ingestion/pdf_loader.py
Extracts text and metadata from PDF files using PyMuPDF (fitz).
Returns a list of PageContent objects, one per page, preserving page numbers.
Page numbers are 1-indexed (as printed in the PDF, not 0-indexed).
"""
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import pymupdf as fitz

from ..core.logging import get_logger

log = get_logger(__name__)


@dataclass
class PageContent:
    """Raw content of a single PDF page."""
    page_number: int          # 1-indexed
    text: str
    char_count: int


@dataclass
class PDFDocument:
    """All content extracted from a PDF file."""
    filename: str
    total_pages: int
    pages: list[PageContent]
    author: Optional[str] = None
    title: Optional[str] = None
    creation_date: Optional[str] = None


def load_pdf(file_path: Path) -> PDFDocument:
    """
    Open a PDF and extract text page by page.
    Skips pages with no extractable text (e.g. pure image pages).
    Raises ValueError if the file has no text content at all.
    """
    log.info("Loading PDF", path=str(file_path))
    doc = fitz.open(str(file_path))

    metadata = doc.metadata or {}
    pages: list[PageContent] = []
    total_pages = len(doc)

    for page_index in range(total_pages):
        page = doc[page_index]
        text = page.get_text("text").strip()
        if not text:
            log.debug("Skipping blank page", page=page_index + 1)
            continue
        pages.append(
            PageContent(
                page_number=page_index + 1,
                text=text,
                char_count=len(text),
            )
        )

    doc.close()

    if not pages:
        raise ValueError(
            f"No extractable text found in '{file_path.name}'. "
            "The PDF may be scanned/image-only."
        )

    total_chars = sum(p.char_count for p in pages)
    log.info(
        "PDF loaded",
        filename=file_path.name,
        total_pages=total_pages,
        pages_with_text=len(pages),
        total_chars=total_chars,
    )

    return PDFDocument(
        filename=file_path.name,
        total_pages=total_pages,
        pages=pages,
        author=metadata.get("author"),
        title=metadata.get("title"),
        creation_date=metadata.get("creationDate"),
    )


def extract_text_from_file(file_path: str, file_type: str) -> str:
    """
    Extract plain text from a file by type ('pdf' | 'txt' | 'docx').
    Returns "" on any failure (logged) so callers can mark the document failed.
    """
    try:
        if file_type == "pdf":
            pdf_doc = load_pdf(Path(file_path))
            return "\n".join(page.text for page in pdf_doc.pages)

        if file_type == "txt":
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                return f.read()

        if file_type == "docx":
            from docx import Document
            document = Document(file_path)
            return "\n".join(p.text for p in document.paragraphs)

        log.warning(
            "Unsupported file type for extraction",
            file_path=file_path,
            file_type=file_type,
        )
        return ""
    except Exception as exc:
        log.warning(
            "Text extraction failed",
            file_path=file_path,
            file_type=file_type,
            error=str(exc),
        )
        return ""

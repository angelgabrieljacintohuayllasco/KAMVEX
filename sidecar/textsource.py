"""
Turn raw text or a PDF into chunked records for the dataset builder.

PDF chunks never span a page boundary, so every chunk keeps an exact page
number — that is what powers the "p.N" citation shown in chat answers.
"""

from __future__ import annotations

import re
import zlib
from pathlib import Path


def extract_pdf_pages(pdf_path: str) -> list[tuple[int, str]]:
    """Extract text from a PDF as (page_number, text) pairs, 1-indexed.

    Tries pypdf first, falls back to raw stream parsing (one "page" per
    content stream — an approximation, but keeps page citations working
    even without pypdf installed).
    """
    path = Path(pdf_path)
    if not path.is_file():
        raise FileNotFoundError(f"PDF no encontrado: {pdf_path}")

    try:
        from pypdf import PdfReader
    except ImportError:
        return _extract_pdf_pages_raw(path)

    reader = PdfReader(str(path))
    return [(i + 1, page.extract_text() or "") for i, page in enumerate(reader.pages)]


def _extract_pdf_pages_raw(path: Path) -> list[tuple[int, str]]:
    raw = path.read_bytes()
    pages: list[tuple[int, str]] = []
    for i, match in enumerate(re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", raw, re.DOTALL)):
        data = match.group(1)
        try:
            decompressed = zlib.decompress(data)
        except zlib.error:
            continue
        text_matches = re.findall(rb"\((.*?)\)", decompressed)
        if text_matches:
            pages.append((i + 1, " ".join(t.decode("latin-1") for t in text_matches)))
    return pages


def chunk_text(text: str, chunk_size: int) -> list[str]:
    """Split text into chunks at paragraph boundaries, capped at chunk_size chars."""
    chunks: list[str] = []
    current = ""
    for para in text.split("\n"):
        para = para.strip()
        if not para:
            continue
        if len(current) + len(para) > chunk_size and current:
            chunks.append(current)
            current = para
        else:
            current = f"{current} {para}".strip() if current else para
    if current:
        chunks.append(current)
    return chunks


def records_from_text(text: str, chunk_size: int) -> tuple[str, list[dict], dict | None]:
    """Chunk raw text into records. Returns (full_text, records, extra_meta)."""
    full_text = text.strip()
    chunks = chunk_text(full_text, chunk_size)
    records = [{"id": f"chunk_{i}", "title": f"Fragmento {i + 1}", "content": c}
               for i, c in enumerate(chunks)]
    return full_text, records, None


def records_from_pdf(pdf_path: str, chunk_size: int) -> tuple[str, list[dict], dict | None]:
    """Chunk a PDF page by page. Returns (full_text, records, extra_meta)."""
    source_doc = Path(pdf_path).name
    pages = extract_pdf_pages(pdf_path)
    full_text = "\n".join(p[1] for p in pages)
    records: list[dict] = []
    n_pages = 0
    for page_no, page_text in pages:
        n_pages = max(n_pages, page_no)
        for c in chunk_text(page_text, chunk_size):
            records.append({
                "id": f"chunk_{len(records)}",
                "title": f"{source_doc} · p.{page_no}",
                "content": c,
            })
    extra = {"source_doc": source_doc, "n_pages": n_pages or None}
    return full_text, records, extra

from dataclasses import dataclass
from io import BytesIO
import re

from PyPDF2 import PdfReader


@dataclass(frozen=True)
class TextChunk:
    id: str
    text: str
    pages: list[int]


def extract_pdf_pages(content: bytes) -> list[tuple[int, str]]:
    """Extract selectable text from each page, keeping 1-based page numbers."""
    reader = PdfReader(BytesIO(content))
    return [
        (page_number, page.extract_text() or "")
        for page_number, page in enumerate(reader.pages, start=1)
    ]


def clean_page_text(text: str) -> str:
    """Remove repeating fixture headers and normalize whitespace."""
    kept_lines = []
    for line in text.replace("\r", "\n").splitlines():
        stripped = line.strip()
        if stripped.casefold() == "manual ficticio" or re.fullmatch(
            r"Pagina\s+\d+", stripped, flags=re.IGNORECASE
        ):
            continue
        if stripped:
            kept_lines.append(stripped)
    return re.sub(r"\s+", " ", " ".join(kept_lines)).strip()


def chunk_pages(
    pages: list[tuple[int, str]],
    chunk_size: int = 800,
    overlap: int = 120,
) -> list[TextChunk]:
    """Split each page into overlapping character chunks with page metadata."""
    if overlap < 0 or chunk_size <= 0 or chunk_size <= overlap:
        raise ValueError("chunk_size precisa ser maior que overlap >= 0")

    chunks: list[TextChunk] = []
    step = chunk_size - overlap
    for page_number, raw_text in pages:
        text = clean_page_text(raw_text)
        if not text:
            continue
        start = 0
        chunk_index = 0
        while start < len(text):
            chunk_text = text[start : start + chunk_size].strip()
            if chunk_text:
                chunks.append(
                    TextChunk(
                        id=f"p{page_number}-c{chunk_index}",
                        text=chunk_text,
                        pages=[page_number],
                    )
                )
                chunk_index += 1
            if start + chunk_size >= len(text):
                break
            start += step
    return chunks

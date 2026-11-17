
from pathlib import Path

from docx import Document as WordDocument
from pypdf import PdfReader


def extract_pdf(file_path: Path) -> list[dict]:
    reader = PdfReader(str(file_path))
    pages = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = page.extract_text() or ""

        if text.strip():
            pages.append({
                "page_number": page_number,
                "text": text
            })

    return pages


def extract_docx(file_path: Path) -> list[dict]:
    document = WordDocument(str(file_path))

    paragraphs = [
        paragraph.text.strip()
        for paragraph in document.paragraphs
        if paragraph.text.strip()
    ]

    if not paragraphs:
        return []

    return [{
        "page_number": None,
        "text": "\n".join(paragraphs)
    }]


def extract_document(file_path: Path, file_type: str) -> list[dict]:
    if file_type == "pdf":
        return extract_pdf(file_path)

    if file_type == "docx":
        return extract_docx(file_path)

    raise ValueError("Unsupported document type")


def split_into_chunks(
    text: str,
    chunk_size: int = 1200,
    overlap: int = 200
) -> list[str]:
    text = " ".join(text.split())

    if not text:
        return []

    chunks = []
    start = 0

    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end].strip()

        if chunk:
            chunks.append(chunk)

        if end == len(text):
            break

        start = end - overlap

    return chunks

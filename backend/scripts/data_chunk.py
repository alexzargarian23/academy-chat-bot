#!/usr/bin/env python3
"""
One-time local indexing of the Academy source documents into Neon.

Run with the project's virtualenv:
  .venv/bin/python backend/scripts/data_chunk.py

Expected source folder:
  /Users/alex/Desktop/Ai

This script only indexes the listed files. It does not change the app's
future upload/processing workflow.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
from docx import Document as DocxDocument
from pypdf import PdfReader
from sentence_transformers import SentenceTransformer
from sqlalchemy import (
    create_engine, String, Text, DateTime, ForeignKey, Integer,
    select, delete
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
from pgvector.sqlalchemy import Vector


SOURCE_DIR = Path("/Users/alex/Desktop/Ai")
BACKEND_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BACKEND_DIR.parent
ENV_FILE = BACKEND_DIR / ".env"

MODEL_NAME = "intfloat/multilingual-e5-small"
EMBEDDING_DIMENSION = 384
CHUNK_WORDS = 350
CHUNK_OVERLAP = 50
CONFIRMATION_TEXT = "INDEX NINE DOCUMENTS"

# Exact filenames, language tags, and access levels supplied by the user.
DOCUMENTS = [
    {
        "filename": "Ai class arm.docx",
        "title": "AI Class — Armenian",
        "language": "hy",
        "visibility": "public",
    },
    {
        "filename": "Ai class eng.docx",
        "title": "AI Class — English",
        "language": "en",
        "visibility": "public",
    },
    {
        "filename": "Ai class ru.docx",
        "title": "AI Class — Russian",
        "language": "ru",
        "visibility": "public",
    },
    {
        "filename": "Ai class schedule.docx",
        "title": "AI Class Schedule",
        "language": "en",
        "visibility": "student",
    },
    {
        "filename": "List of team mebers en.docx",
        "title": "List of Team Members — English",
        "language": "en",
        "visibility": "student",
    },
    {
        "filename": "List of team mebers hy.docx",
        "title": "List of Team Members — Armenian",
        "language": "hy",
        "visibility": "student",
    },
    {
        "filename": "List of team mebers ru.docx",
        "title": "List of Team Members — Russian",
        "language": "ru",
        "visibility": "student",
    },
    {
        "filename": "List of Tools and Software for Student Fellowship Program.docx",
        "title": "Tools and Software for Student Fellowship Program",
        "language": "en",
        "visibility": "admin",
    },
    {
        "filename": "The Intern Engineer’s Field Guide.pdf",
        "title": "The Intern Engineer’s Field Guide",
        "language": "en",
        "visibility": "student",
    },
]


class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_filename: Mapped[str] = mapped_column(String(255), unique=True)
    file_type: Mapped[str] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(String(10), default="en")
    visibility: Mapped[str] = mapped_column(String(30), default="public")
    status: Mapped[str] = mapped_column(String(30), default="pending")
    uploaded_by: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(
        ForeignKey("documents.id", ondelete="CASCADE")
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    embedding = mapped_column(Vector(EMBEDDING_DIMENSION), nullable=True)


def extract_docx(path: Path) -> list[tuple[str, int | None]]:
    doc = DocxDocument(str(path))
    parts: list[str] = []

    for paragraph in doc.paragraphs:
        text = paragraph.text.strip()
        if text:
            parts.append(text)

    for table in doc.tables:
        for row in table.rows:
            cells = [cell.text.strip().replace("\n", " ") for cell in row.cells]
            line = " | ".join(cell for cell in cells if cell)
            if line:
                parts.append(line)

    joined = "\n".join(parts).strip()
    return [(joined, None)] if joined else []


def extract_pdf(path: Path) -> list[tuple[str, int | None]]:
    reader = PdfReader(str(path))
    pages: list[tuple[str, int | None]] = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append((text, page_number))

    return pages


def chunk_text(text: str, page_number: int | None) -> list[dict]:
    words = text.split()
    if not words:
        return []

    chunks: list[dict] = []
    start = 0
    while start < len(words):
        end = min(start + CHUNK_WORDS, len(words))
        chunk = " ".join(words[start:end]).strip()
        if chunk:
            chunks.append({"content": chunk, "page_number": page_number})
        if end == len(words):
            break
        start = end - CHUNK_OVERLAP

    return chunks


def main() -> None:
    if not SOURCE_DIR.is_dir():
        raise SystemExit(f"Source folder not found: {SOURCE_DIR}")

    if not ENV_FILE.is_file():
        raise SystemExit(f"Backend .env file not found: {ENV_FILE}")

    load_dotenv(ENV_FILE)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL was not found in backend/.env")

    # Ensure SQLAlchemy uses psycopg 3 when DATABASE_URL is the plain postgres URL.
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://", "postgresql+psycopg://", 1
        )
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://", "postgresql+psycopg://", 1
        )

    files: list[tuple[dict, Path]] = []
    missing: list[str] = []
    for item in DOCUMENTS:
        path = SOURCE_DIR / item["filename"]
        if not path.is_file():
            missing.append(item["filename"])
        else:
            files.append((item, path))

    if missing:
        print("These expected files were not found:")
        for name in missing:
            print(f"  - {name}")
        print("\nFiles actually found in the source folder:")
        for path in sorted(SOURCE_DIR.iterdir()):
            if path.is_file():
                print(f"  - {path.name!r}")
        raise SystemExit("No database changes were made.")

    extracted: list[tuple[dict, Path, list[dict]]] = []
    print(f"Source folder: {SOURCE_DIR}")
    print("Reading documents...")

    for item, path in files:
        if path.suffix.lower() == ".docx":
            pages = extract_docx(path)
        elif path.suffix.lower() == ".pdf":
            pages = extract_pdf(path)
        else:
            raise SystemExit(f"Unsupported file type: {path.name}")

        chunks: list[dict] = []
        for page_text, page_number in pages:
            chunks.extend(chunk_text(page_text, page_number))

        if not chunks:
            raise SystemExit(
                f"No extractable text found in {path.name}. No database changes were made."
            )

        extracted.append((item, path, chunks))
        print(f"  {path.name}: {len(chunks)} chunks")

    print("\nLoading multilingual embedding model...")
    model = SentenceTransformer(MODEL_NAME)

    all_chunk_rows: list[tuple[dict, Path, list[dict]]] = []
    for item, path, chunks in extracted:
        passages = [f"passage: {chunk['content']}" for chunk in chunks]
        vectors = model.encode(
            passages,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        for chunk, vector in zip(chunks, vectors):
            chunk["embedding"] = vector.tolist()
        all_chunk_rows.append((item, path, chunks))

    engine = create_engine(database_url, pool_pre_ping=True)

    total_chunks = sum(len(chunks) for _, _, chunks in all_chunk_rows)
    print("\nReady to insert:")
    print(f"  Documents: {len(all_chunk_rows)}")
    print(f"  Chunks:    {total_chunks}")
    print("  Access levels: public / student / admin")
    print("\nThis will insert the nine listed documents and their chunks into Neon.")
    confirmation = input(f'Type exactly "{CONFIRMATION_TEXT}" to continue: ').strip()
    if confirmation != CONFIRMATION_TEXT:
        print("Cancelled. No database changes were made.")
        return

    try:
        with Session(engine) as session:
            # Prevent accidental duplicates. The user stated the documents table
            # was emptied before this one-time indexing operation.
            existing = session.execute(
                select(Document.original_filename)
            ).scalars().all()
            if existing:
                raise RuntimeError(
                    "The documents table is not empty. No rows were inserted. "
                    f"Existing filenames: {existing}"
                )

            for item, path, chunks in all_chunk_rows:
                document = Document(
                    title=item["title"],
                    original_filename=item["filename"],
                    # Mark as locally imported; this is not a real uploads/ file.
                    storage_filename=f"local-import::{item['filename']}",
                    file_type=path.suffix.lower().lstrip("."),
                    language=item["language"],
                    visibility=item["visibility"],
                    status="completed",
                    uploaded_by=None,
                )
                session.add(document)
                session.flush()

                for index, chunk in enumerate(chunks):
                    session.add(
                        DocumentChunk(
                            document_id=document.id,
                            chunk_index=index,
                            content=chunk["content"],
                            page_number=chunk["page_number"],
                            embedding=chunk["embedding"],
                        )
                    )

            session.commit()

        print("\nIndexing completed successfully.")
        print(f"Inserted {len(all_chunk_rows)} documents and {total_chunks} chunks.")
    except Exception:
        # The transaction is rolled back by the Session context manager.
        raise
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

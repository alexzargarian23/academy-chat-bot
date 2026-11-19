
#!/usr/bin/env python3

from __future__ import annotations
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

from dotenv import load_dotenv
from docx import Document as DocxDocument
from pypdf import PdfReader

from sqlalchemy import (
    create_engine,
    String,
    Text,
    DateTime,
    ForeignKey,
    Integer,
    select,
    delete,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session
from pgvector.sqlalchemy import Vector


# --------------------------------------------------
# PATHS
# --------------------------------------------------

SOURCE_DIR = Path("/Users/alex/Desktop/Ai")
BACKEND_DIR = Path(__file__).resolve().parents[1]
ENV_FILE = BACKEND_DIR / ".env"

sys.path.insert(0, str(BACKEND_DIR))

load_dotenv(ENV_FILE)

from app.services.embedding_service import (  # noqa: E402
    MODEL_NAME,
    EMBEDDING_DIMENSION,
    get_document_embeddings,
)


# --------------------------------------------------
# CONFIGURATION
# --------------------------------------------------

CHUNK_WORDS = 350
CHUNK_OVERLAP = 50
BATCH_SIZE = 16

CONFIRMATION_TEXT = "RE-EMBED NINE DOCUMENTS"


# --------------------------------------------------
# DOCUMENT LIST
# --------------------------------------------------

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


# --------------------------------------------------
# DATABASE MODELS
# --------------------------------------------------

class Base(DeclarativeBase):
    pass


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    original_filename: Mapped[str] = mapped_column(String(255))
    storage_filename: Mapped[str] = mapped_column(
        String(255), unique=True
    )
    file_type: Mapped[str] = mapped_column(String(20))
    language: Mapped[str] = mapped_column(
        String(10), default="en"
    )
    visibility: Mapped[str] = mapped_column(
        String(30), default="public"
    )
    status: Mapped[str] = mapped_column(
        String(30), default="pending"
    )
    uploaded_by: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )
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

    page_number: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )

    embedding = mapped_column(
        Vector(EMBEDDING_DIMENSION), nullable=True
    )


# --------------------------------------------------
# EXTRACT TEXT
# --------------------------------------------------

def extract_docx(path: Path) -> list[tuple[str, int | None]]:
    doc = DocxDocument(str(path))
    parts = []

    for paragraph in doc.paragraphs:
        content = paragraph.text.strip()
        if content:
            parts.append(content)

    for table in doc.tables:
        for row in table.rows:
            cells = [
                cell.text.strip().replace("\n", " ")
                for cell in row.cells
            ]

            line = " | ".join(cell for cell in cells if cell)

            if line:
                parts.append(line)

    joined = "\n".join(parts).strip()

    return [(joined, None)] if joined else []


def extract_pdf(path: Path) -> list[tuple[str, int | None]]:
    reader = PdfReader(str(path))
    pages = []

    for page_number, page in enumerate(reader.pages, start=1):
        content = (page.extract_text() or "").strip()

        if content:
            pages.append((content, page_number))

    return pages


# --------------------------------------------------
# CHUNK TEXT
# --------------------------------------------------

def chunk_text(
    content: str,
    page_number: int | None,
) -> list[dict]:

    words = content.split()

    if not words:
        return []

    chunks = []
    start = 0

    while start < len(words):
        end = min(start + CHUNK_WORDS, len(words))

        chunk = " ".join(words[start:end]).strip()

        if chunk:
            chunks.append({
                "content": chunk,
                "page_number": page_number,
            })

        if end == len(words):
            break

        start = end - CHUNK_OVERLAP

    return chunks


# --------------------------------------------------
# VERIFY DATABASE DIMENSION
# --------------------------------------------------

def check_vector_dimension(engine):

    query = text("""
        SELECT format_type(a.atttypid, a.atttypmod)
        FROM pg_attribute a
        JOIN pg_class c ON c.oid = a.attrelid
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public'
          AND c.relname = 'document_chunks'
          AND a.attname = 'embedding'
          AND a.attnum > 0
          AND NOT a.attisdropped
    """)

    with engine.connect() as connection:
        actual_type = connection.execute(query).scalar_one_or_none()

    expected_type = f"vector({EMBEDDING_DIMENSION})"

    if actual_type != expected_type:
        raise RuntimeError(
            f"Wrong database embedding dimension. "
            f"Expected {expected_type}, found {actual_type}. "
            "No documents were changed."
        )


# --------------------------------------------------
# MAIN
# --------------------------------------------------

def main():

    if not SOURCE_DIR.is_dir():
        raise SystemExit(
            f"Source folder not found: {SOURCE_DIR}"
        )

    if not ENV_FILE.is_file():
        raise SystemExit(
            f"Backend .env file not found: {ENV_FILE}"
        )

    database_url = os.getenv("DATABASE_URL")

    if not database_url:
        raise SystemExit(
            "DATABASE_URL was not found in backend/.env"
        )

    if database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg://",
            1,
        )

    elif database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql+psycopg://",
            1,
        )

    # ----------------------------------------------
    # VERIFY ALL NINE FILES EXIST
    # ----------------------------------------------

    files = []
    missing = []

    for item in DOCUMENTS:
        path = SOURCE_DIR / item["filename"]

        if path.is_file():
            files.append((item, path))
        else:
            missing.append(item["filename"])

    if missing:
        print("Missing files:")

        for filename in missing:
            print(f"  - {filename}")

        raise SystemExit(
            "No database changes were made."
        )

    # ----------------------------------------------
    # EXTRACT AND CHUNK
    # ----------------------------------------------

    extracted = []

    print("\nReading documents...")

    for item, path in files:

        if path.suffix.lower() == ".docx":
            pages = extract_docx(path)

        elif path.suffix.lower() == ".pdf":
            pages = extract_pdf(path)

        else:
            raise SystemExit(
                f"Unsupported file type: {path.name}"
            )

        chunks = []

        for page_content, page_number in pages:
            chunks.extend(
                chunk_text(page_content, page_number)
            )

        if not chunks:
            raise SystemExit(
                f"No text extracted from {path.name}. "
                "No database changes were made."
            )

        extracted.append((item, path, chunks))

        print(f"  {path.name}: {len(chunks)} chunks")

    # ----------------------------------------------
    # GENERATE GEMINI EMBEDDINGS
    # ----------------------------------------------

    print(
        f"\nGenerating embeddings using "
        f"{MODEL_NAME} ({EMBEDDING_DIMENSION} dimensions)..."
    )

    total_chunks = 0

    for item, path, chunks in extracted:

        texts = [chunk["content"] for chunk in chunks]

        for start in range(0, len(texts), BATCH_SIZE):

            batch = texts[start:start + BATCH_SIZE]

            vectors = get_document_embeddings(batch)

            if len(vectors) != len(batch):
                raise RuntimeError(
                    f"Embedding count mismatch: {path.name}"
                )

            for chunk, vector in zip(
                chunks[start:start + BATCH_SIZE],
                vectors,
            ):

                if len(vector) != EMBEDDING_DIMENSION:
                    raise RuntimeError(
                        f"Invalid vector dimensions: {path.name}"
                    )

                chunk["embedding"] = vector

        total_chunks += len(chunks)

        print(
            f"  {path.name}: {len(chunks)} embeddings generated"
        )

    # ----------------------------------------------
    # DATABASE CONNECTION
    # ----------------------------------------------

    engine = create_engine(
        database_url,
        pool_pre_ping=True,
    )

    try:

        check_vector_dimension(engine)

        print("\nDatabase vector dimension verified.")

        print("\nReady to update:")
        print(f"  Documents: {len(extracted)}")
        print(f"  Chunks: {total_chunks}")
        print(f"  Dimensions: {EMBEDDING_DIMENSION}")

        print(
            "\nOnly the nine listed documents and their chunks "
            "will be updated."
        )

        confirmation = input(
            f'\nType exactly "{CONFIRMATION_TEXT}" to continue: '
        ).strip()

        if confirmation != CONFIRMATION_TEXT:
            print("Cancelled. No database changes were made.")
            return

        # ------------------------------------------
        # UPDATE EXISTING DOCUMENTS AND CHUNKS
        # ------------------------------------------

        with Session(engine) as session:

            filenames = [
                item["filename"]
                for item, _, _ in extracted
            ]

            existing_documents = session.execute(
                select(Document).where(
                    Document.original_filename.in_(filenames)
                )
            ).scalars().all()

            documents_by_filename = {}

            for document in existing_documents:

                filename = document.original_filename

                if filename in documents_by_filename:
                    raise RuntimeError(
                        f"Duplicate database document: {filename}. "
                        "No changes were committed."
                    )

                documents_by_filename[filename] = document

            updated_count = 0
            created_count = 0

            for item, path, chunks in extracted:

                filename = item["filename"]

                document = documents_by_filename.get(filename)

                if document is None:

                    document = Document(
                        title=item["title"],
                        original_filename=filename,
                        storage_filename=f"local-import::{filename}",
                        file_type=path.suffix.lower().lstrip("."),
                        language=item["language"],
                        visibility=item["visibility"],
                        status="completed",
                        uploaded_by=None,
                    )

                    session.add(document)
                    session.flush()

                    created_count += 1

                else:

                    # Preserve document ID, storage_filename,
                    # uploaded_by, and created_at.
                    document.title = item["title"]
                    document.file_type = (
                        path.suffix.lower().lstrip(".")
                    )
                    document.language = item["language"]
                    document.visibility = item["visibility"]
                    document.status = "completed"

                    updated_count += 1

                # Delete only this document's old chunks.
                session.execute(
                    delete(DocumentChunk).where(
                        DocumentChunk.document_id == document.id
                    )
                )

                # Insert its new chunks and Gemini embeddings.
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

            # Commit all nine document updates together.
            session.commit()

        print("\nIndexing completed successfully!")
        print(f"Existing documents updated: {updated_count}")
        print(f"New documents created: {created_count}")
        print(f"Total chunks indexed: {total_chunks}")

    finally:
        engine.dispose()


if __name__ == "__main__":
    main()

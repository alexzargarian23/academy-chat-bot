
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Document, DocumentChunk
from app.services.document_processor import (
    extract_document,
    split_into_chunks,
)
from app.services.embedding_service import generate_embeddings


UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"


def process_document(document_id: int, db: Session) -> dict:
    document = db.query(Document).filter(
        Document.id == document_id
    ).first()

    if not document:
        raise ValueError("Document not found")

    if not document.storage_filename:
        raise ValueError("Document has no stored filename. Re-upload it.")

    file_path = (UPLOAD_DIR / document.storage_filename).resolve()

    # Ensure the stored path cannot escape the uploads directory.
    if file_path.parent != UPLOAD_DIR.resolve():
        raise ValueError("Invalid stored document path")

    if not file_path.is_file():
        raise ValueError("Uploaded file could not be found")

    # Mark the document as processing before starting the work.
    document.status = "processing"
    db.commit()

    try:
        pages = extract_document(file_path, document.file_type)

        chunks = []

        for page in pages:
            page_text = page.get("text", "").strip()

            if not page_text:
                continue

            page_chunks = split_into_chunks(page_text)

            for chunk in page_chunks:
                if chunk.strip():
                    chunks.append({
                        "content": chunk.strip(),
                        "page_number": page.get("page_number"),
                    })

        if not chunks:
            raise ValueError(
                "No text could be extracted. The PDF may be scanned "
                "or the document may be empty."
            )

        embeddings = generate_embeddings([
            chunk["content"] for chunk in chunks
        ])

        if len(embeddings) != len(chunks):
            raise RuntimeError(
                "The embedding service returned an unexpected number "
                "of embeddings."
            )

        # Replace the existing chunks in one database transaction.
        db.query(DocumentChunk).filter(
            DocumentChunk.document_id == document.id
        ).delete(synchronize_session=False)

        for index, (chunk, embedding) in enumerate(
            zip(chunks, embeddings)
        ):
            db.add(
                DocumentChunk(
                    document_id=document.id,
                    chunk_index=index,
                    content=chunk["content"],
                    page_number=chunk["page_number"],
                    embedding=embedding,
                )
            )

        document.status = "completed"
        db.commit()

        return {
            "document_id": document.id,
            "status": document.status,
            "chunks_created": len(chunks),
        }

    except Exception:
        db.rollback()

        # Mark the document as failed without deleting previously
        # committed chunks.
        failed_document = db.query(Document).filter(
            Document.id == document_id
        ).first()

        if failed_document:
            failed_document.status = "failed"
            db.commit()

        raise

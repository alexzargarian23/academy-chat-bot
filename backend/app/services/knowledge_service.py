from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Document


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

    # The file is safely stored, but AI indexing is disabled.
    document.status = "completed"
    db.commit()

    return {
        "document_id": document.id,
        "status": document.status,
        "chunks_created": 0,
        "indexing_enabled": False,
    }
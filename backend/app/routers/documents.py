
import uuid
from pathlib import Path

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User, Document
from app.services.knowledge_service import process_document


router = APIRouter(prefix="/documents", tags=["Documents"])

UPLOAD_DIR = Path(__file__).resolve().parents[2] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 20 * 1024 * 1024

ALLOWED_EXTENSIONS = {
    ".pdf": "application/pdf",
    ".docx": (
        "application/vnd.openxmlformats-officedocument."
        "wordprocessingml.document"
    ),
}

ALLOWED_VISIBILITY = {"public", "student", "staff", "admin"}
ALLOWED_LANGUAGES = {"en", "hy", "ru"}
ALLOWED_STATUSES = {"pending", "processing", "completed", "failed"}


def require_document_manager(user: User):
    if user.role not in {"staff", "admin"}:
        raise HTTPException(
            status_code=403,
            detail="Staff or admin access required",
        )


def get_accessible_document(
    document_id: int,
    db: Session,
    current_user: User,
) -> Document:
    query = db.query(Document).filter(
        Document.id == document_id
    )

    # Staff cannot manage documents reserved for administrators.
    if current_user.role != "admin":
        query = query.filter(Document.visibility != "admin")

    document = query.first()

    if not document:
        raise HTTPException(
            status_code=404,
            detail="Document not found",
        )

    return document


def serialize_document(document: Document) -> dict:
    return {
        "id": document.id,
        "title": document.title,
        "original_filename": document.original_filename,
        "file_type": document.file_type,
        "language": document.language,
        "visibility": document.visibility,
        "status": document.status,
        "uploaded_by": document.uploaded_by,
        "created_at": document.created_at,
        "chunks_count": len(document.chunks),
    }


def validate_upload(
    filename: str,
    content: bytes,
    visibility: str,
    language: str,
    current_user: User,
):
    extension = Path(filename).suffix.lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="Only PDF and DOCX files are supported",
        )

    if not content:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty",
        )

    if len(content) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=413,
            detail="File size cannot exceed 20 MB",
        )

    if extension == ".pdf" and not content.startswith(b"%PDF-"):
        raise HTTPException(
            status_code=400,
            detail="The file does not appear to be a valid PDF",
        )

    if extension == ".docx" and not content.startswith(b"PK"):
        raise HTTPException(
            status_code=400,
            detail="The file does not appear to be a valid DOCX",
        )

    if visibility not in ALLOWED_VISIBILITY:
        raise HTTPException(
            status_code=400,
            detail="Invalid document visibility",
        )

    if language not in ALLOWED_LANGUAGES:
        raise HTTPException(
            status_code=400,
            detail="Supported languages are en, hy, and ru",
        )

    if current_user.role != "admin" and visibility == "admin":
        raise HTTPException(
            status_code=403,
            detail="Only administrators can upload admin-only documents",
        )

    return extension


# ---------------------------------------------------------
# 1. UPLOAD DOCUMENT
# ---------------------------------------------------------

@router.post(
    "/upload",
    status_code=status.HTTP_201_CREATED,
)
def upload_document(
    file: UploadFile = File(...),
    title: str = Form(...),
    language: str = Form("en"),
    visibility: str = Form("public"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_document_manager(current_user)

    clean_title = title.strip()

    if not clean_title:
        raise HTTPException(
            status_code=400,
            detail="Document title cannot be empty",
        )

    filename = Path(file.filename or "document").name
    content = file.file.read(MAX_FILE_SIZE + 1)

    extension = validate_upload(
        filename=filename,
        content=content,
        visibility=visibility,
        language=language,
        current_user=current_user,
    )

    stored_filename = f"{uuid.uuid4().hex}{extension}"
    file_path = UPLOAD_DIR / stored_filename

    try:
        file_path.write_bytes(content)

        document = Document(
            title=clean_title,
            original_filename=filename,
            storage_filename=stored_filename,
            file_type=extension.lstrip("."),
            language=language,
            visibility=visibility,
            status="pending",
            uploaded_by=current_user.id,
        )

        db.add(document)
        db.commit()
        db.refresh(document)

    except Exception:
        db.rollback()
        file_path.unlink(missing_ok=True)

        raise HTTPException(
            status_code=500,
            detail="Could not save the uploaded document",
        )

    try:
        process_document(document.id, db)
        db.refresh(document)

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Document processing failed. Check the backend logs.",
        )

    return {
        "message": "Document uploaded and processed successfully",
        "document": serialize_document(document),
    }


# ---------------------------------------------------------
# 2. LIST DOCUMENTS
# ---------------------------------------------------------

@router.get("/")
def list_documents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=100),
    search: str | None = Query(default=None, max_length=255),
    document_status: str | None = Query(default=None, alias="status"),
    visibility: str | None = Query(default=None),
    language: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_document_manager(current_user)

    query = db.query(Document)

    if current_user.role != "admin":
        query = query.filter(Document.visibility != "admin")

    if search and search.strip():
        search_term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                Document.title.ilike(search_term),
                Document.original_filename.ilike(search_term),
            )
        )

    if document_status:
        if document_status not in ALLOWED_STATUSES:
            raise HTTPException(
                status_code=400,
                detail="Invalid document status",
            )
        query = query.filter(Document.status == document_status)

    if visibility:
        if visibility not in ALLOWED_VISIBILITY:
            raise HTTPException(
                status_code=400,
                detail="Invalid document visibility",
            )

        if current_user.role != "admin" and visibility == "admin":
            raise HTTPException(
                status_code=403,
                detail="You cannot view admin-only documents",
            )

        query = query.filter(Document.visibility == visibility)

    if language:
        if language not in ALLOWED_LANGUAGES:
            raise HTTPException(
                status_code=400,
                detail="Unsupported document language",
            )
        query = query.filter(Document.language == language)

    total = query.count()

    documents = (
        query
        .order_by(Document.created_at.desc(), Document.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )

    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "total_pages": (total + page_size - 1) // page_size,
        "documents": [
            serialize_document(document)
            for document in documents
        ],
    }


# ---------------------------------------------------------
# 3. GET DOCUMENT DETAILS
# ---------------------------------------------------------

@router.get("/{document_id}")
def get_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_document_manager(current_user)

    document = get_accessible_document(
        document_id,
        db,
        current_user,
    )

    return serialize_document(document)


# ---------------------------------------------------------
# 4. PROCESS DOCUMENT
# ---------------------------------------------------------

def run_document_processing(
    document_id: int,
    db: Session,
    current_user: User,
):
    require_document_manager(current_user)

    get_accessible_document(
        document_id,
        db,
        current_user,
    )

    try:
        return process_document(document_id, db)

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception:
        # The detailed exception is available in the backend logs.
        raise HTTPException(
            status_code=500,
            detail="Document processing failed. Check the backend logs.",
        )


@router.post("/{document_id}/process")
def process_uploaded_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return run_document_processing(
        document_id,
        db,
        current_user,
    )


# ---------------------------------------------------------
# 5. REPROCESS DOCUMENT
# ---------------------------------------------------------

@router.post("/{document_id}/reprocess")
def reprocess_uploaded_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return run_document_processing(
        document_id,
        db,
        current_user,
    )


# ---------------------------------------------------------
# 6. DELETE DOCUMENT
# ---------------------------------------------------------

@router.delete("/{document_id}")
def delete_document(
    document_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_document_manager(current_user)

    document = get_accessible_document(
        document_id,
        db,
        current_user,
    )

    stored_filename = document.storage_filename
    file_path = (
        UPLOAD_DIR / stored_filename
    ).resolve() if stored_filename else None

    if file_path and file_path.parent != UPLOAD_DIR.resolve():
        raise HTTPException(
            status_code=400,
            detail="Invalid stored document path",
        )

    try:
        db.delete(document)
        db.commit()

    except Exception:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Could not delete the document",
        )

    # The database deletion is committed first. The document's chunks
    # are deleted through the Document relationship cascade.
    if file_path:
        file_path.unlink(missing_ok=True)

    return {
        "message": "Document deleted successfully",
        "document_id": document_id,
    }

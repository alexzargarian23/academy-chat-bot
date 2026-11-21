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
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User, Document
from app.services.knowledge_service import process_document
from fastapi.responses import FileResponse, StreamingResponse
from urllib.parse import quote

from app.services.google_drive_service import download_drive_file

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
ROLE_DOCUMENT_VISIBILITY = {
    "admin": ALLOWED_VISIBILITY,
    "staff": ALLOWED_VISIBILITY,
    "student": ALLOWED_VISIBILITY,
    "guest": {"public"},
}


def require_document_manager(user: User):
    if user.role not in {"staff", "admin"}:
        raise HTTPException(
            status_code=403,
            detail="Staff or admin access required",
        )


def _allowed_visibility_for(user: User) -> set[str]:
    role = (user.role or "").strip().lower()
    return ROLE_DOCUMENT_VISIBILITY.get(role, set())


def get_accessible_document(
        document_id: int,
        db: Session,
        current_user: User,
) -> Document:
    query = db.query(Document).filter(
        Document.id == document_id
    )

    allowed_visibility = _allowed_visibility_for(current_user)
    if not allowed_visibility:
        raise HTTPException(status_code=403, detail="Document access required")
    query = query.filter(Document.visibility.in_(allowed_visibility))

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

    allowed_visibility = _allowed_visibility_for(current_user)
    query = query.filter(Document.visibility.in_(allowed_visibility))

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

        if visibility not in allowed_visibility:
            raise HTTPException(
                status_code=403,
                detail="You cannot view documents with this visibility",
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


def _document_file_response(
        document: Document,
        disposition: str,
):
    media_type = ALLOWED_EXTENSIONS.get(
        Path(document.original_filename).suffix.lower(),
        "application/octet-stream",
    )

    headers = {
        "Cache-Control": "private, no-store",
        "X-Content-Type-Options": "nosniff",
    }

    # Download from Google Drive when a Drive ID exists.
    if document.drive_file_id:
        try:
            content = download_drive_file(document.drive_file_id)

        except FileNotFoundError:
            raise HTTPException(
                status_code=404,
                detail="Document file not found in Google Drive",
            )

        except PermissionError:
            raise HTTPException(
                status_code=502,
                detail="The Academy server cannot access this Drive file",
            )

        except Exception:
            raise HTTPException(
                status_code=502,
                detail="Could not download the document from Google Drive",
            )

        filename = quote(document.original_filename)

        headers["Content-Disposition"] = (
            f"{disposition}; filename*=UTF-8''{filename}"
        )

        return StreamingResponse(
            iter([content]),
            media_type=media_type,
            headers=headers,
        )

    # Otherwise, use the existing local upload folder.
    if not document.storage_filename:
        raise HTTPException(
            status_code=404,
            detail="Document file not found",
        )

    file_path = (
            UPLOAD_DIR / document.storage_filename
    ).resolve()

    if file_path.parent != UPLOAD_DIR.resolve():
        raise HTTPException(
            status_code=400,
            detail="Invalid stored document path",
        )

    if not file_path.is_file():
        raise HTTPException(
            status_code=404,
            detail="Document file not found",
        )

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=document.original_filename,
        content_disposition_type=disposition,
        headers=headers,
    )


@router.get("/{document_id}/download")
def download_document_file(
        document_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    document = get_accessible_document(document_id, db, current_user)
    return _document_file_response(document, "attachment")


@router.get("/{document_id}/preview")
def preview_document_file(
        document_id: int,
        db: Session = Depends(get_db),
        current_user: User = Depends(get_current_user),
):
    document = get_accessible_document(document_id, db, current_user)
    return _document_file_response(document, "inline")


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


from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_roles
from app.models import User
from app.models.email_message import AcademyEmail
from app.services.email_service import create_reply_draft, send_approved_reply, sync_inbox

router = APIRouter(prefix="/email-assistant", tags=["Email assistant"])


class DraftUpdate(BaseModel):
    reply_draft: str = Field(min_length=1, max_length=30000)


@router.post("/sync")
def sync(db: Session = Depends(get_db), user: User = Depends(require_roles("staff", "admin"))):
    del user
    try:
        return sync_inbox(db)
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/messages")
def list_messages(status_filter: str | None = None, db: Session = Depends(get_db), user: User = Depends(require_roles("staff", "admin"))):
    del user
    query = db.query(AcademyEmail)
    if status_filter:
        query = query.filter(AcademyEmail.status == status_filter)
    rows = query.order_by(AcademyEmail.received_at.desc()).limit(200).all()
    return [{"id": row.id, "sender": row.sender, "recipient": row.recipient, "subject": row.subject,
             "body": row.body, "received_at": row.received_at, "reply_draft": row.reply_draft,
             "status": row.status, "staff_approved": row.staff_approved} for row in rows]


def _get_email(email_id: int, db: Session) -> AcademyEmail:
    row = db.get(AcademyEmail, email_id)
    if not row:
        raise HTTPException(status_code=404, detail="Email not found")
    return row


@router.post("/messages/{email_id}/draft")
def draft(email_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("staff", "admin"))):
    del user
    row = _get_email(email_id, db)
    try:
        row = create_reply_draft(db, row)
        return {"id": row.id, "reply_draft": row.reply_draft, "status": row.status}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"Could not generate a grounded reply: {exc}") from exc


@router.put("/messages/{email_id}/draft")
def edit_draft(email_id: int, data: DraftUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("staff", "admin"))):
    del user
    row = _get_email(email_id, db)
    if row.status == "sent":
        raise HTTPException(status_code=409, detail="Email has already been sent")
    row.reply_draft = data.reply_draft
    row.status = "drafted"
    row.staff_approved = False
    row.approved_by = None
    db.commit()
    return {"id": row.id, "status": row.status}


@router.post("/messages/{email_id}/approve")
def approve(email_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("staff", "admin"))):
    row = _get_email(email_id, db)
    if not row.reply_draft:
        raise HTTPException(status_code=404, detail="Reply draft not found")
    if row.status == "sent":
        raise HTTPException(status_code=409, detail="Email has already been sent")
    row.status = "approved"
    row.staff_approved = True
    row.approved_by = user.id
    db.commit()
    return {"id": row.id, "status": row.status, "approved_by": user.id}


@router.post("/messages/{email_id}/send")
def send(email_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("staff", "admin"))):
    del user
    row = _get_email(email_id, db)
    try:
        send_approved_reply(row)
        row.status = "sent"
        row.sent_at = datetime.now(timezone.utc)
        db.commit()
        return {"id": row.id, "status": row.status, "sent_at": row.sent_at}
    except Exception as exc:
        db.rollback()
        raise HTTPException(status_code=502, detail=f"Could not send email: {exc}") from exc

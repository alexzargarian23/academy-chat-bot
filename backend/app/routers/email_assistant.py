
import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_roles
from app.models import User
from app.models.email_message import AcademyEmail
from app.models.gmail_oauth_state import GmailOAuthState
from app.services.email_service import (
    create_reply_draft,
    send_approved_reply,
    sync_inbox,
)
from app.services.gmail_oauth_service import (
    complete_oauth,
    get_authorization_url,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/email-assistant", tags=["Email assistant"])


class DraftUpdate(BaseModel):
    reply_draft: str = Field(min_length=1, max_length=30000)


# --------------------------------------------------
# GMAIL OAUTH
# --------------------------------------------------

@router.get("/connect")
def connect_gmail(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    try:
        oauth_state = GmailOAuthState(user_id=user.id)
        db.add(oauth_state)
        db.commit()
        db.refresh(oauth_state)

        authorization_url = get_authorization_url(oauth_state.state)

        return {
            "authorization_url": authorization_url,
            "message": "Open the authorization URL to connect Gmail.",
        }

    except Exception as exc:
        db.rollback()
        logger.exception("Could not start Gmail OAuth")
        raise HTTPException(
            status_code=500,
            detail="Could not start Gmail authorization.",
        ) from exc


@router.get("/oauth/callback")
def gmail_oauth_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    db: Session = Depends(get_db),
):
    if error:
        raise HTTPException(
            status_code=400,
            detail="Google authorization was denied or cancelled.",
        )

    if not code or not state:
        raise HTTPException(
            status_code=400,
            detail="Missing Google authorization code or state.",
        )

    oauth_state = (
        db.query(GmailOAuthState)
        .filter(GmailOAuthState.state == state)
        .first()
    )

    if not oauth_state:
        raise HTTPException(
            status_code=400,
            detail="Invalid or already-used OAuth state.",
        )

    expires_at = oauth_state.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)

    if expires_at <= datetime.now(timezone.utc):
        db.delete(oauth_state)
        db.commit()
        raise HTTPException(
            status_code=400,
            detail="OAuth authorization expired. Please connect again.",
        )

    # Consume the state before exchanging the authorization code.
    db.delete(oauth_state)
    db.commit()

    try:
        connected_email = complete_oauth(code, db)

        return {
            "connected": True,
            "email": connected_email,
            "message": "Gmail connected successfully.",
        }

    except Exception as exc:
        db.rollback()
        logger.exception("Gmail OAuth callback failed")
        raise HTTPException(
            status_code=400,
            detail="Gmail connection failed. Check the backend logs.",
        ) from exc


@router.get("/connection")
def gmail_connection(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    del user

    from app.models.gmail_token import GmailToken
    import os

    account = os.getenv("GMAIL_ACCOUNT", "").lower()

    token = (
        db.query(GmailToken)
        .filter(GmailToken.account_email == account)
        .first()
    )

    return {
        "connected": token is not None,
        "email": token.account_email if token else None,
    }


# --------------------------------------------------
# EMAIL MANAGEMENT
# --------------------------------------------------

@router.post("/sync")
def sync(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    del user

    try:
        return sync_inbox(db)
    except Exception as exc:
        db.rollback()
        logger.exception("Email synchronization failed")
        raise HTTPException(
            status_code=502,
            detail="Could not synchronize inbox.",
        ) from exc


@router.get("/messages")
def list_messages(
    status_filter: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    del user

    query = db.query(AcademyEmail)

    if status_filter:
        query = query.filter(AcademyEmail.status == status_filter)

    rows = (
        query.order_by(AcademyEmail.received_at.desc())
        .limit(200)
        .all()
    )

    return [
        {
            "id": row.id,
            "sender": row.sender,
            "recipient": row.recipient,
            "subject": row.subject,
            "body": row.body,
            "received_at": row.received_at,
            "reply_draft": row.reply_draft,
            "status": row.status,
            "staff_approved": row.staff_approved,
        }
        for row in rows
    ]


def _get_email(email_id: int, db: Session) -> AcademyEmail:
    row = db.get(AcademyEmail, email_id)

    if not row:
        raise HTTPException(status_code=404, detail="Email not found")

    return row


@router.post("/messages/{email_id}/draft")
def draft(
    email_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    del user

    row = _get_email(email_id, db)

    try:
        row = create_reply_draft(db, row)

        return {
            "id": row.id,
            "reply_draft": row.reply_draft,
            "status": row.status,
        }

    except Exception as exc:
        db.rollback()
        logger.exception("Reply draft generation failed")
        raise HTTPException(
            status_code=502,
            detail="Could not generate a grounded reply.",
        ) from exc


@router.put("/messages/{email_id}/draft")
def edit_draft(
    email_id: int,
    data: DraftUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    del user

    row = _get_email(email_id, db)

    if row.status == "sent":
        raise HTTPException(
            status_code=409,
            detail="Email has already been sent",
        )

    row.reply_draft = data.reply_draft
    row.status = "drafted"
    row.staff_approved = False
    row.approved_by = None

    db.commit()

    return {"id": row.id, "status": row.status}


@router.post("/messages/{email_id}/approve")
def approve(
    email_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    row = _get_email(email_id, db)

    if not row.reply_draft:
        raise HTTPException(
            status_code=404,
            detail="Reply draft not found",
        )

    if row.status == "sent":
        raise HTTPException(
            status_code=409,
            detail="Email has already been sent",
        )

    row.status = "approved"
    row.staff_approved = True
    row.approved_by = user.id

    db.commit()

    return {
        "id": row.id,
        "status": row.status,
        "approved_by": user.id,
    }


@router.post("/messages/{email_id}/send")
def send(
    email_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("admin")),
):
    del user

    row = _get_email(email_id, db)

    try:
        send_approved_reply(db, row)

        row.status = "sent"
        row.sent_at = datetime.now(timezone.utc)

        db.commit()

        return {
            "id": row.id,
            "status": row.status,
            "sent_at": row.sent_at,
        }

    except Exception as exc:
        db.rollback()
        logger.exception("Email sending failed")
        raise HTTPException(
            status_code=502,
            detail="Could not send email.",
        ) from exc

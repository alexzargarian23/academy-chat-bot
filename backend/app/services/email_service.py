
import base64
import logging
import os
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr

from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from sqlalchemy.orm import Session

from app.models.email_message import AcademyEmail
from app.models.gmail_token import GmailToken
from app.services.gmail_oauth_service import (
    GMAIL_SCOPES,
    _encryption,
    _required_env,
)
from app.services.rag_service import answer_question

logger = logging.getLogger(__name__)


def _get_credentials(db: Session):
    from google.oauth2.credentials import Credentials

    account = _required_env("GMAIL_ACCOUNT").lower()

    token = (
        db.query(GmailToken)
        .filter(GmailToken.account_email == account)
        .first()
    )

    if not token:
        raise RuntimeError("Gmail is not connected. Connect Gmail first.")

    decrypted = _encryption().decrypt(
        token.encrypted_credentials.encode("utf-8")
    ).decode("utf-8")

    credentials = Credentials.from_authorized_user_info(
        __import__("json").loads(decrypted),
        scopes=GMAIL_SCOPES,
    )

    if credentials.expired:
        if not credentials.refresh_token:
            raise RuntimeError("Gmail refresh token is missing.")

        credentials.refresh(Request())

        token.encrypted_credentials = _encryption().encrypt(
            credentials.to_json().encode("utf-8")
        ).decode("utf-8")

        db.commit()

    return credentials


def _gmail_service(db: Session):
    credentials = _get_credentials(db)

    return build(
        "gmail",
        "v1",
        credentials=credentials,
        cache_discovery=False,
    )


def _decode_header_value(value: str | None) -> str:
    if not value:
        return ""

    from email.header import decode_header

    parts = []

    for chunk, encoding in decode_header(value):
        if isinstance(chunk, bytes):
            parts.append(
                chunk.decode(encoding or "utf-8", errors="replace")
            )
        else:
            parts.append(chunk)

    return "".join(parts)


def _headers(message: dict) -> dict:
    result = {}

    for header in message.get("payload", {}).get("headers", []):
        result[header["name"].lower()] = header["value"]

    return result


def _extract_body(payload: dict) -> str:
    mime_type = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data")

    if mime_type == "text/plain" and data:
        decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
        return decoded.decode("utf-8", errors="replace")

    for part in payload.get("parts", []):
        result = _extract_body(part)

        if result:
            return result

    return ""


def sync_inbox(db: Session, limit: int = 30) -> dict:
    gmail = _gmail_service(db)

    account = _required_env("GMAIL_ACCOUNT")

    response = (
        gmail.users()
        .messages()
        .list(
            userId="me",
            labelIds=["INBOX"],
            maxResults=min(max(limit, 1), 100),
        )
        .execute()
    )

    messages = response.get("messages", [])
    imported = 0
    skipped = 0

    for item in messages:
        gmail_id = item["id"]
        stable_id = f"gmail:{gmail_id}"

        existing = (
            db.query(AcademyEmail)
            .filter(AcademyEmail.message_id == stable_id)
            .first()
        )

        if existing:
            skipped += 1
            continue

        full_message = (
            gmail.users()
            .messages()
            .get(
                userId="me",
                id=gmail_id,
                format="full",
            )
            .execute()
        )

        headers = _headers(full_message)

        sender = parseaddr(headers.get("from", ""))[1]
        recipient = parseaddr(headers.get("to", account))[1] or account

        internal_date = full_message.get("internalDate")

        if internal_date:
            received_at = datetime.fromtimestamp(
                int(internal_date) / 1000,
                tz=timezone.utc,
            )
        else:
            received_at = datetime.now(timezone.utc)

        body = _extract_body(full_message.get("payload", {}))

        record = AcademyEmail(
            message_id=stable_id,
            gmail_thread_id=full_message.get("threadId"),
            rfc_message_id=headers.get("message-id"),
            sender=sender,
            recipient=recipient,
            subject=_decode_header_value(headers.get("subject")),
            body=body[:50000],
            received_at=received_at,
            status="received",
        )

        db.add(record)
        imported += 1

    db.commit()

    return {
        "imported": imported,
        "skipped": skipped,
        "checked": len(messages),
    }


def create_reply_draft(db: Session, record: AcademyEmail) -> AcademyEmail:
    prompt = (
        "Draft an email reply to this message. Answer using only the Academy "
        "knowledge base. If the knowledge base does not support an answer, "
        "say staff must confirm it. Do not invent facts.\n"
        f"Subject: {record.subject}\n"
        f"Email: {record.body}"
    )

    result = answer_question(prompt, db, "staff")

    record.reply_draft = result["answer"]
    record.status = "drafted"
    record.staff_approved = False
    record.approved_by = None

    db.commit()
    db.refresh(record)

    return record


def send_approved_reply(db: Session, record: AcademyEmail) -> None:
    if (
        record.status != "approved"
        or not record.staff_approved
        or not record.reply_draft
    ):
        raise RuntimeError("Only admin-approved drafts can be sent.")

    if not record.gmail_thread_id:
        raise RuntimeError("Gmail thread ID is missing for this email.")

    gmail = _gmail_service(db)

    message = EmailMessage()
    message["To"] = record.sender
    message["From"] = _required_env("GMAIL_ACCOUNT")
    message["Subject"] = (
        record.subject
        if record.subject.lower().startswith("re:")
        else f"Re: {record.subject}"
    )

    if record.rfc_message_id:
        message["In-Reply-To"] = record.rfc_message_id
        message["References"] = record.rfc_message_id

    message.set_content(record.reply_draft)

    raw_message = base64.urlsafe_b64encode(
        message.as_bytes()
    ).decode("utf-8")

    gmail.users().messages().send(
        userId="me",
        body={
            "raw": raw_message,
            "threadId": record.gmail_thread_id,
        },
    ).execute()

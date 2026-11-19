import email
import imaplib
import logging
import os
import smtplib
from datetime import datetime, timezone
from email.header import decode_header
from email.message import EmailMessage
from email.utils import parseaddr

from sqlalchemy.orm import Session

from app.models.email_message import AcademyEmail
from app.services.rag_service import answer_question

logger = logging.getLogger(__name__)


def _cfg(name: str, default: str | None = None) -> str | None:
    return os.getenv(name, default)


def _decode(value: str | None) -> str:
    if not value:
        return ""
    parts = []
    for chunk, encoding in decode_header(value):
        parts.append(chunk.decode(encoding or "utf-8", errors="replace") if isinstance(chunk, bytes) else chunk)
    return "".join(parts)


def _plain_body(message: email.message.Message) -> str:
    if message.is_multipart():
        for part in message.walk():
            if part.get_content_type() == "text/plain" and part.get_content_disposition() != "attachment":
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    payload = message.get_payload(decode=True)
    return payload.decode(message.get_content_charset() or "utf-8", errors="replace") if payload else str(message.get_payload())


def sync_inbox(db: Session, limit: int = 30) -> dict:
    host = _cfg("ACADEMY_IMAP_HOST")
    username = _cfg("ACADEMY_EMAIL_USER")
    password = _cfg("ACADEMY_EMAIL_PASSWORD")
    if not all((host, username, password)):
        raise RuntimeError("Academy IMAP settings are incomplete")
    assert host and username and password
    client = imaplib.IMAP4_SSL(host, int(_cfg("ACADEMY_IMAP_PORT", "993") or "993"))
    try:
        client.login(username, password)
        client.select(_cfg("ACADEMY_IMAP_MAILBOX", "INBOX") or "INBOX", readonly=True)
        result, data = client.search(None, "ALL")
        if result != "OK":
            raise RuntimeError("Could not search Academy inbox")
        ids = (data[0].split() if data and data[0] else [])[-limit:]
        imported = 0
        for uid in ids:
            result, parts = client.fetch(uid, "(RFC822)")
            if result != "OK":
                continue
            raw = next((part[1] for part in parts if isinstance(part, tuple)), None)
            if not raw:
                continue
            message = email.message_from_bytes(raw)
            message_id = (message.get("Message-ID") or f"imap-{uid.decode(errors='ignore')}").strip()
            if db.query(AcademyEmail).filter(AcademyEmail.message_id == message_id).first():
                continue
            received_at = email.utils.parsedate_to_datetime(message.get("Date") or "") if message.get("Date") else datetime.now(timezone.utc)
            if received_at.tzinfo is None:
                received_at = received_at.replace(tzinfo=timezone.utc)
            db.add(AcademyEmail(
                message_id=message_id,
                sender=parseaddr(message.get("From", ""))[1],
                recipient=parseaddr(message.get("To") or username)[1] or username,
                subject=_decode(message.get("Subject")),
                body=_plain_body(message)[:50000],
                received_at=received_at,
                status="received",
            ))
            imported += 1
        db.commit()
        return {"imported": imported}
    finally:
        try:
            client.logout()
        except Exception:
            logger.debug("Could not close IMAP connection", exc_info=True)


def create_reply_draft(db: Session, record: AcademyEmail) -> AcademyEmail:
    prompt = (
        "Draft an email reply to this message. Answer using only the Academy knowledge base. "
        "If the knowledge base does not support an answer, say staff must confirm it. Do not invent facts.\n"
        f"Subject: {record.subject}\nEmail: {record.body}"
    )
    result = answer_question(prompt, db, "staff")
    record.reply_draft = result["answer"]
    record.status = "drafted"
    db.commit()
    db.refresh(record)
    return record


def send_approved_reply(record: AcademyEmail) -> None:
    host = _cfg("ACADEMY_SMTP_HOST")
    username = _cfg("ACADEMY_EMAIL_USER")
    password = _cfg("ACADEMY_EMAIL_PASSWORD")
    if not all((host, username, password)):
        raise RuntimeError("Academy SMTP settings are incomplete")
    assert host and username and password
    if record.status != "approved" or not record.staff_approved or not record.reply_draft:
        raise RuntimeError("Only staff-approved drafts can be sent")
    message = EmailMessage()
    message["From"] = _cfg("ACADEMY_EMAIL_FROM", username)
    message["To"] = record.sender
    message["Subject"] = "Re: " + record.subject
    message.set_content(record.reply_draft)
    port = int(_cfg("ACADEMY_SMTP_PORT", "465") or "465")
    if (_cfg("ACADEMY_SMTP_USE_SSL", "true") or "true").lower() == "true":
        with smtplib.SMTP_SSL(host, port, timeout=30) as server:
            server.login(username, password)
            server.send_message(message)
    else:
        with smtplib.SMTP(host, port, timeout=30) as server:
            server.starttls()
            server.login(username, password)
            server.send_message(message)

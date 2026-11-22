"""Telegram Bot API and Slack Events API adapters for the shared Academy assistant.

Source files are uploaded as native Telegram/Slack attachments. Before a file is
read, the same document-visibility check used by the website is applied to the
actual Academy user linked to the messaging identity.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import mimetypes
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.core.security import hash_password, verify_password
from app.models import User, Conversation, Message, Document
from app.models.channel_identity import ChannelIdentity
from app.models.channel_event import ChannelEvent
from app.routers.documents import UPLOAD_DIR, get_accessible_document
from app.services.assistant_service import run_assistant
from app.services.google_drive_service import download_drive_file

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations", tags=["Messaging integrations"])

# Keep in sync with the website's supported upload size.
MAX_CHANNEL_DOCUMENT_BYTES = 20 * 1024 * 1024
MAX_SOURCE_ATTACHMENTS = 5


def _http_json(
    url: str,
    payload: dict[str, Any],
    headers: dict[str, str] | None = None,
) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", **(headers or {})},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = response.read().decode("utf-8")
            return json.loads(data) if data else {}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        logger.exception("Messaging provider request failed")
        raise RuntimeError("Messaging provider request failed")


def _http_json_get(url: str, headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read().decode("utf-8")
            return json.loads(data) if data else {}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        logger.exception("Messaging provider request failed")
        raise RuntimeError("Messaging provider request failed")


def _http_upload(url: str, content: bytes, content_type: str) -> None:
    request = urllib.request.Request(
        url,
        data=content,
        headers={"Content-Type": content_type},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError("File upload was rejected")
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        logger.exception("File upload request failed")
        raise RuntimeError("File upload request failed")


def _telegram_send(chat_id: int | str, text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    # Telegram sendMessage text limit is 4096 characters.
    chunks = [text[i:i + 4000] for i in range(0, max(len(text), 1), 4000)]
    for chunk in chunks:
        result = _http_json(
            f"https://api.telegram.org/bot{token}/sendMessage",
            {"chat_id": chat_id, "text": chunk},
        )
        if not result.get("ok"):
            raise RuntimeError("Telegram rejected the outgoing message")


def _telegram_send_document(
    chat_id: int | str,
    filename: str,
    content: bytes,
    mime_type: str,
    caption: str | None = None,
) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")

    boundary = f"----AcademyBot{uuid.uuid4().hex}"
    parts: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        parts.extend([
            f"--{boundary}\r\n".encode(),
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
            value.encode("utf-8"),
            b"\r\n",
        ])

    add_field("chat_id", str(chat_id))
    if caption:
        add_field("caption", caption[:900])

    safe_filename = Path(filename).name.replace('"', "") or "academy-document"
    parts.extend([
        f"--{boundary}\r\n".encode(),
        (
            f'Content-Disposition: form-data; name="document"; '
            f'filename="{safe_filename}"\r\n'
        ).encode("utf-8"),
        f"Content-Type: {mime_type}\r\n\r\n".encode(),
        content,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ])

    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendDocument",
        data=b"".join(parts),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            result = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError):
        logger.exception("Telegram document upload failed")
        raise RuntimeError("Telegram document upload failed")

    if not result.get("ok"):
        logger.error("Telegram sendDocument failed: %s", result.get("description", "unknown_error"))
        raise RuntimeError("Telegram rejected the document upload")


def _slack_send(channel: str, text: str, thread_ts: str | None = None) -> None:
    token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN is not configured")

    payload: dict[str, Any] = {"channel": channel, "text": text, "mrkdwn": True}
    if thread_ts:
        payload["thread_ts"] = thread_ts

    result = _http_json(
        "https://slack.com/api/chat.postMessage",
        payload,
        {"Authorization": f"Bearer {token}"},
    )
    if not result.get("ok"):
        logger.error("Slack chat.postMessage failed: %s", result.get("error", "unknown_error"))
        raise RuntimeError("Slack rejected the outgoing message")


def _slack_upload_documents(
    channel: str,
    documents: list[tuple[str, bytes, str]],
    thread_ts: str | None = None,
) -> None:
    """Upload files using Slack's current external-upload API (not files.upload)."""
    token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN is not configured")

    uploaded: list[dict[str, str]] = []
    auth_headers = {"Authorization": f"Bearer {token}"}

    for filename, content, mime_type in documents:
        query = urllib.parse.urlencode({"filename": filename, "length": len(content)})
        result = _http_json_get(
            f"https://slack.com/api/files.getUploadURLExternal?{query}",
            auth_headers,
        )
        if not result.get("ok") or not result.get("upload_url") or not result.get("file_id"):
            logger.error("Slack getUploadURLExternal failed: %s", result.get("error", "unknown_error"))
            raise RuntimeError("Slack could not prepare the file upload")

        _http_upload(result["upload_url"], content, mime_type)
        uploaded.append({"id": result["file_id"], "title": filename})

    if not uploaded:
        return

    payload: dict[str, Any] = {
        "files": uploaded,
        "channel_id": channel,
        "initial_comment": "Academy source document(s)",
    }
    if thread_ts:
        payload["thread_ts"] = thread_ts

    result = _http_json(
        "https://slack.com/api/files.completeUploadExternal",
        payload,
        auth_headers,
    )
    if not result.get("ok"):
        logger.error("Slack completeUploadExternal failed: %s", result.get("error", "unknown_error"))
        raise RuntimeError("Slack could not complete the file upload")


def _get_document_bytes(
    db: Session,
    user: User,
    document_id: int,
) -> tuple[Document, bytes, str]:
    """Read a document only after applying the website's role visibility check."""
    document = get_accessible_document(
        document_id=document_id,
        db=db,
        current_user=user,
    )

    if document.drive_file_id:
        content = download_drive_file(document.drive_file_id)
    else:
        if not document.storage_filename:
            raise FileNotFoundError("Document file is missing")

        file_path = (UPLOAD_DIR / document.storage_filename).resolve()
        if file_path.parent != UPLOAD_DIR.resolve():
            raise ValueError("Invalid document storage path")
        if not file_path.is_file():
            raise FileNotFoundError("Document file is missing")
        content = file_path.read_bytes()

    mime_type = mimetypes.guess_type(document.original_filename)[0] or "application/octet-stream"
    return document, content, mime_type


def _collect_source_files(
    db: Session,
    user: User,
    sources: list[dict[str, Any]] | None,
) -> list[tuple[str, bytes, str]]:
    """Resolve unique source documents; never trust source metadata as permission."""
    files: list[tuple[str, bytes, str]] = []
    seen_ids: set[int] = set()

    for source in (sources or [])[:MAX_SOURCE_ATTACHMENTS]:
        try:
            document_id = int(source.get("document_id"))
        except (TypeError, ValueError):
            continue

        if document_id in seen_ids:
            continue
        seen_ids.add(document_id)

        try:
            document, content, mime_type = _get_document_bytes(db, user, document_id)
            if len(content) > MAX_CHANNEL_DOCUMENT_BYTES:
                logger.warning("Skipping source document %s: file exceeds channel attachment size", document_id)
                continue
            files.append((document.original_filename, content, mime_type))
        except Exception:
            # A failed or unauthorized attachment must not prevent the answer
            # from reaching the user. Do not log document contents or credentials.
            logger.exception("Could not attach source document_id=%s for role=%s", document_id, user.role)

    return files


def _send_answer_and_sources(
    provider: str,
    destination: int | str,
    answer: str,
    sources: list[dict[str, Any]] | None,
    user: User | None,
    db: Session,
    thread_ts: str | None = None,
) -> None:
    source_files = _collect_source_files(db, user, sources) if user and sources else []
    message = answer
    if source_files:
        message += "\n\n📎 The referenced Academy document(s) are attached."

    if provider == "telegram":
        _telegram_send(destination, message)
        for filename, content, mime_type in source_files:
            _telegram_send_document(destination, filename, content, mime_type, caption=filename)
    elif provider == "slack":
        _slack_send(str(destination), message, thread_ts)
        if source_files:
            _slack_upload_documents(str(destination), source_files, thread_ts)


def _guest_user(db: Session, provider: str, external_id: str, display_name: str) -> User:
    suffix = hashlib.sha256(f"{provider}:{external_id}".encode()).hexdigest()[:24]
    email = f"{provider}_{suffix}@channel.invalid"
    user = db.scalar(select(User).where(User.email == email))
    if not user:
        user = User(
            full_name=(display_name or f"{provider.title()} visitor")[:150],
            email=email,
            password_hash=hash_password(os.urandom(32).hex()),
            role="guest",
        )
        db.add(user)
        db.flush()
    return user


def _new_conversation(db: Session, user: User, provider: str, language: str) -> Conversation:
    conversation = Conversation(
        user_id=user.id,
        channel=provider,
        language=(language or "en")[:10],
        status="active",
    )
    db.add(conversation)
    db.flush()
    return conversation


def _bind_identity(
    db: Session,
    identity: ChannelIdentity,
    user: User,
    provider: str,
    language: str,
    authenticated: bool,
) -> Conversation:
    conversation = _new_conversation(db, user, provider, language)
    identity.user_id = user.id
    identity.conversation_id = conversation.id
    identity.authenticated = authenticated
    identity.authenticated_at = datetime.now(timezone.utc) if authenticated else None
    identity.auth_stage = None
    identity.pending_email = None
    identity.failed_auth_attempts = 0
    return conversation


def _get_identity(
    db: Session,
    provider: str,
    external_id: str,
    display_name: str,
    language: str = "en",
    account_email: str | None = None,
) -> tuple[User, Conversation, ChannelIdentity]:
    identity = db.scalar(select(ChannelIdentity).where(
        ChannelIdentity.provider == provider,
        ChannelIdentity.external_user_id == external_id,
    ))
    registered_user = None
    if account_email:
        registered_user = db.scalar(
            select(User).where(func.lower(User.email) == account_email.lower())
        )

    if identity:
        user = db.get(User, identity.user_id)
        conversation = db.get(Conversation, identity.conversation_id) if identity.conversation_id else None
        if provider == "slack":
            if registered_user and (not identity.authenticated or identity.user_id != registered_user.id):
                conversation = _bind_identity(db, identity, registered_user, provider, language, authenticated=True)
                user = registered_user
            elif not registered_user and identity.authenticated:
                user = _guest_user(db, provider, external_id, display_name)
                conversation = _bind_identity(db, identity, user, provider, language, authenticated=False)
        if user and conversation:
            identity.display_name = display_name[:150] or identity.display_name
            return user, conversation, identity

    user = registered_user if provider == "slack" and registered_user else _guest_user(db, provider, external_id, display_name)
    conversation = _new_conversation(db, user, provider, language)
    if identity:
        identity.user_id = user.id
        identity.conversation_id = conversation.id
        identity.display_name = display_name[:150]
        identity.authenticated = bool(registered_user and provider == "slack")
        identity.authenticated_at = datetime.now(timezone.utc) if identity.authenticated else None
    else:
        identity = ChannelIdentity(
            provider=provider,
            external_user_id=external_id[:255],
            display_name=(display_name or "Guest")[:150],
            user_id=user.id,
            conversation_id=conversation.id,
        )
        db.add(identity)
    db.flush()
    return user, conversation, identity


def _slack_user_email(user_id: str) -> str | None:
    token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    if not token:
        logger.warning("SLACK_BOT_TOKEN is not configured; Slack users remain guests")
        return None
    try:
        result = _http_json_get(
            "https://slack.com/api/users.info?" + urllib.parse.urlencode({"user": user_id}),
            {"Authorization": f"Bearer {token}"},
        )
    except RuntimeError:
        return None
    if not result.get("ok"):
        logger.warning("Slack users.info failed: %s", result.get("error", "unknown_error"))
        return None
    profile = result.get("user", {}).get("profile", {})
    email = profile.get("email") or result.get("user", {}).get("email")
    return str(email).strip().lower() if email else None


def _telegram_auth_response(
    db: Session,
    identity: ChannelIdentity,
    provider: str,
    external_id: str,
    display_name: str,
    language: str,
    question: str,
) -> str | None:
    if provider != "telegram":
        return None

    command = question.strip().lower()

    if command == "/logout":
        guest = _guest_user(db, provider, external_id, display_name)
        _bind_identity(db, identity, guest, provider, language, authenticated=False)
        db.commit()
        return "You have been logged out. You can still ask about public Academy information."

    if command == "/login":
        identity.auth_stage = "email"
        identity.pending_email = None
        identity.failed_auth_attempts = 0
        db.commit()
        return "Please enter your Academy email address."

    if identity.authenticated:
        return None

    if identity.auth_stage is None or identity.auth_stage == "guest":
        return None

    if identity.auth_stage == "email":
        email = question.strip().lower()
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if not user or user.role == "guest":
            identity.pending_email = None
            identity.auth_stage = "guest"
            db.commit()
            return (
                "This email is not registered as an Academy account. "
                "You can continue using public Academy information. "
                "Send /login if you want to try again."
            )

        identity.pending_email = email
        identity.auth_stage = "password"
        identity.failed_auth_attempts = 0
        db.commit()
        return "Email found. Please enter your Academy password."

    if identity.auth_stage == "password":
        user = db.scalar(
            select(User).where(func.lower(User.email) == identity.pending_email)
        ) if identity.pending_email else None

        if not user or not verify_password(question, user.password_hash):
            identity.failed_auth_attempts += 1
            if identity.failed_auth_attempts >= 5:
                identity.auth_stage = "guest"
                identity.pending_email = None
                identity.failed_auth_attempts = 0
                db.commit()
                return (
                    "Too many failed attempts. You are still able to use public "
                    "Academy information. Send /login to try again."
                )
            db.commit()
            return "Incorrect password. Please try again."

        _bind_identity(db, identity, user, provider, language, authenticated=True)
        db.commit()
        return "You are authenticated. You can now access the data permitted for your Academy role."

    return None


def _is_handoff_response(result: dict[str, Any], answer: str) -> bool:
    """Return True when the assistant response represents a human handoff.

    Handoff responses must still be delivered to the messaging channel, but
    retrieved RAG documents should not be attached to that notification.
    Prefer explicit metadata from run_assistant; retain a text fallback for
    assistant-service versions that only return the user-facing answer.
    """
    for key in (
        "handoff_created",
        "handoff_requested",
        "requires_handoff",
        "is_handoff",
        "human_handoff",
    ):
        if result.get(key) is True:
            return True

    handoff_value = result.get("handoff")
    if handoff_value is True:
        return True
    if isinstance(handoff_value, dict) and handoff_value:
        return True

    normalized = re.sub(r"\\s+", " ", (answer or "").strip().lower())
    handoff_phrases = (
        "your handoff request has been submitted",
        "handoff request has been submitted",
        "your handoff has been submitted",
        "handoff has been submitted",
        "a handoff has been created",
        "handoff request was created",
        "a staff member will contact you",
    )
    return any(phrase in normalized for phrase in handoff_phrases)


def _process_inbound(
    db: Session,
    provider: str,
    external_id: str,
    display_name: str,
    language: str,
    event_id: str,
    question: str,
    account_email: str | None = None,
) -> dict[str, Any] | None:
    question = question.strip()
    if not question:
        return None

    event_record = db.scalar(select(ChannelEvent).where(
        ChannelEvent.provider == provider,
        ChannelEvent.event_id == event_id,
    ))
    if event_record and event_record.status == "processed":
        # Preserve webhook idempotency. The text response is replayed, but files
        # are not re-uploaded for duplicate delivery attempts.
        return {"answer": event_record.response_text, "sources": [], "user_id": None}

    if event_record is None:
        event_record = ChannelEvent(provider=provider, event_id=event_id[:255], status="received")
        db.add(event_record)
        db.flush()

    user, conversation, identity = _get_identity(
        db, provider, external_id, display_name, language, account_email
    )

    auth_response = _telegram_auth_response(
        db, identity, provider, external_id, display_name, language, question
    )
    if auth_response is not None:
        event_record.status = "processed"
        event_record.response_text = auth_response[:12000]
        db.commit()
        return {"answer": auth_response, "sources": [], "user_id": user.id}

    previous = db.scalars(
        select(Message)
        .where(Message.conversation_id == conversation.id)
        .order_by(Message.id.desc())
        .limit(10)
    ).all()
    history = [
        {"sender": message.sender, "content": message.content}
        for message in reversed(previous)
        if message.sender in {"user", "assistant"}
    ]

    event_record.status = "processing"
    db.add(Message(conversation_id=conversation.id, sender="user", content=question[:8000]))
    db.flush()

    result = run_assistant(question[:2000], db, user, conversation, history)
    answer = result.get("answer") or "I'm sorry, I couldn't prepare a response. Please contact Academy staff."
    sources = result.get("sources") or []
    suppress_source_attachments = _is_handoff_response(result, answer)

    db.add(Message(
        conversation_id=conversation.id,
        sender="assistant",
        content=answer[:12000],
        sources=sources or None,
    ))
    event_record.status = "processed"
    event_record.response_text = answer[:12000]
    db.commit()

    return {
        "answer": answer,
        "sources": sources,
        "user_id": user.id,
        "suppress_source_attachments": suppress_source_attachments,
    }


def _process_slack_event_background(payload: dict[str, Any], event_id: str) -> None:
    db = SessionLocal()
    event = payload.get("event") or {}
    channel_id = str(event.get("channel") or "")
    thread_ts = event.get("thread_ts") or event.get("ts")

    try:
        sender_id = str(event.get("user") or "")
        message_text = re.sub(r"<@[^>]+>", "", event.get("text", "")).strip()
        if not sender_id or not channel_id or not message_text:
            return

        team_id = str(payload.get("team_id") or "workspace")
        external_id = f"{team_id}:{sender_id}"
        response = _process_inbound(
            db,
            "slack",
            external_id,
            f"Slack user {sender_id}",
            "en",
            event_id,
            message_text,
            _slack_user_email(sender_id),
        )

        if response:
            user = db.get(User, response.get("user_id")) if response.get("user_id") else None
            _send_answer_and_sources(
                "slack",
                channel_id,
                response.get("answer") or "",
                [] if response.get("suppress_source_attachments") else (response.get("sources") or []),
                user,
                db,
                str(thread_ts) if thread_ts else None,
            )

    except Exception:
        db.rollback()
        logger.exception("Background Slack event processing failed")
        if channel_id:
            try:
                _slack_send(
                    channel_id,
                    "Sorry, I couldn't prepare an answer right now. Please try again in a minute or contact Academy staff.",
                    str(thread_ts) if thread_ts else None,
                )
            except Exception:
                logger.exception("Failed to send Slack fallback message")
    finally:
        db.close()


def _verify_slack_signature(
    body: bytes,
    timestamp: str | None,
    signature: str | None,
) -> bool:
    secret = os.getenv("SLACK_SIGNING_SECRET", "").strip()
    if not secret or not timestamp or not signature:
        return False
    try:
        request_time = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - request_time) > 60 * 5:
        return False
    base = b"v0:" + timestamp.encode() + b":" + body
    expected = "v0=" + hmac.new(secret.encode(), base, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/telegram/webhook")
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    expected_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if not expected_secret or not hmac.compare_digest(
        expected_secret, x_telegram_bot_api_secret_token or ""
    ):
        raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret")

    payload = await request.json()
    message = payload.get("message") or payload.get("edited_message")
    if not message or not message.get("from") or not message.get("chat"):
        return {"ok": True, "ignored": True}

    text = message.get("text") or message.get("caption") or ""
    sender = message["from"]
    external_id = str(sender.get("id"))
    display_name = " ".join(filter(None, [sender.get("first_name"), sender.get("last_name")])) or f"Telegram user {external_id}"
    update_id = str(payload.get("update_id", f"{message.get('message_id')}:{external_id}"))

    try:
        response = _process_inbound(
            db,
            "telegram",
            external_id,
            display_name,
            sender.get("language_code", "en"),
            update_id,
            text,
        )
        if response:
            user = db.get(User, response.get("user_id")) if response.get("user_id") else None
            _send_answer_and_sources(
                "telegram",
                message["chat"]["id"],
                response.get("answer") or "",
                [] if response.get("suppress_source_attachments") else (response.get("sources") or []),
                user,
                db,
            )
    except Exception:
        db.rollback()
        logger.exception("Telegram update processing failed")
        raise HTTPException(status_code=503, detail="Telegram message processing failed")

    return {"ok": True}


@router.post("/slack/events")
async def slack_events(
    request: Request,
    background_tasks: BackgroundTasks,
    x_slack_request_timestamp: str | None = Header(default=None),
    x_slack_signature: str | None = Header(default=None),
    db: Session = Depends(get_db),
):
    body = await request.body()
    if not _verify_slack_signature(body, x_slack_request_timestamp, x_slack_signature):
        raise HTTPException(status_code=401, detail="Invalid Slack request signature")

    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if payload.get("type") == "url_verification":
        return {"challenge": payload.get("challenge", "")}
    if payload.get("type") != "event_callback":
        return {"ok": True}

    event = payload.get("event") or {}
    event_type = event.get("type")
    if event_type not in {"message", "app_mention"} or event.get("bot_id") or event.get("subtype"):
        return {"ok": True, "ignored": True}

    sender_id = event.get("user")
    channel_id = event.get("channel")
    text = event.get("text", "")
    if not sender_id or not channel_id or not text:
        return {"ok": True, "ignored": True}

    # Only respond in direct messages or when explicitly mentioned in a channel.
    if event_type == "message" and event.get("channel_type") != "im":
        return {"ok": True, "ignored": True}

    event_id = str(payload.get("event_id") or f"{event.get('ts')}:{sender_id}")
    existing = db.scalar(select(ChannelEvent).where(
        ChannelEvent.provider == "slack",
        ChannelEvent.event_id == event_id,
    ))
    if existing is None:
        db.add(ChannelEvent(provider="slack", event_id=event_id[:255], status="queued"))
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            return {"ok": True, "duplicate": True}
        background_tasks.add_task(_process_slack_event_background, payload, event_id)

    return {"ok": True}


"""Telegram Bot API and Slack Events API adapters for the shared Academy assistant."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db, SessionLocal
from app.core.security import hash_password, verify_password
from app.models import User, Conversation, Message
from app.models.channel_identity import ChannelIdentity
from app.models.channel_event import ChannelEvent
from app.services.assistant_service import run_assistant

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations", tags=["Messaging integrations"])


def _http_json(url: str, payload: dict[str, Any], headers: dict[str, str] | None = None) -> dict:
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json", **(headers or {})}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read().decode("utf-8")
            return json.loads(data) if data else {}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        logger.exception("Messaging provider request failed")
        raise RuntimeError("Messaging provider request failed") from exc


def _http_json_get(url: str, headers: dict[str, str] | None = None) -> dict:
    request = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = response.read().decode("utf-8")
            return json.loads(data) if data else {}
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        logger.exception("Messaging provider request failed")
        raise RuntimeError("Messaging provider request failed") from exc


def _telegram_send(chat_id: int | str, text: str) -> None:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not configured")
    # Telegram sendMessage text limit is 4096 characters.
    chunks = [text[i:i + 4000] for i in range(0, max(len(text), 1), 4000)]
    for chunk in chunks:
        result = _http_json(f"https://api.telegram.org/bot{token}/sendMessage", {"chat_id": chat_id, "text": chunk})
        if not result.get("ok"):
            raise RuntimeError("Telegram rejected the outgoing message")


def _slack_send(channel: str, text: str, thread_ts: str | None = None) -> None:
    token = os.getenv("SLACK_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("SLACK_BOT_TOKEN is not configured")
    payload: dict[str, Any] = {"channel": channel, "text": text, "mrkdwn": True}
    if thread_ts:
        payload["thread_ts"] = thread_ts
    result = _http_json("https://slack.com/api/chat.postMessage", payload, {"Authorization": f"Bearer {token}"})
    if not result.get("ok"):
        logger.error("Slack chat.postMessage failed: %s", result.get("error", "unknown_error"))
        raise RuntimeError("Slack rejected the outgoing message")


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
    conversation = Conversation(user_id=user.id, channel=provider, language=(language or "en")[:10], status="active")
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
        registered_user = db.scalar(select(User).where(func.lower(User.email) == account_email.lower()))
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
        identity = ChannelIdentity(provider=provider, external_user_id=external_id[:255], display_name=(display_name or "Guest")[:150], user_id=user.id, conversation_id=conversation.id)
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
    if identity.auth_stage == "guest":
        return None
    if identity.auth_stage is None:
        identity.auth_stage = "email"
        db.commit()
        return "To access registered account data, please enter your Academy email address."
    if identity.auth_stage == "email":
        email = question.strip().lower()
        user = db.scalar(select(User).where(func.lower(User.email) == email))
        if not user or user.role == "guest":
            identity.pending_email = None
            identity.auth_stage = "guest"
            db.commit()
            return "That email is not registered. You may continue with public Academy information, but private data is unavailable. Send /login if you want to try another account."
        identity.pending_email = email
        identity.auth_stage = "password"
        identity.failed_auth_attempts = 0
        db.commit()
        return "Email found. Please enter your Academy password."
    if identity.auth_stage == "password":
        user = db.scalar(select(User).where(func.lower(User.email) == identity.pending_email)) if identity.pending_email else None
        if not user or not verify_password(question, user.password_hash):
            identity.failed_auth_attempts += 1
            if identity.failed_auth_attempts >= 5:
                identity.auth_stage = "email"
                identity.pending_email = None
                identity.failed_auth_attempts = 0
                response = "Too many failed attempts. Please start again with your Academy email."
            else:
                response = "Incorrect password. Please try again."
            db.commit()
            return response
        _bind_identity(db, identity, user, provider, language, authenticated=True)
        db.commit()
        return "You are authenticated. You can now access the data permitted for your Academy role."
    identity.auth_stage = None
    identity.pending_email = None
    db.commit()
    return "Please enter your Academy email address to authenticate."


def _process_inbound(db: Session, provider: str, external_id: str, display_name: str, language: str, event_id: str, question: str, account_email: str | None = None) -> str | None:
    question = question.strip()
    if not question:
        return None
    event_record = db.scalar(select(ChannelEvent).where(
        ChannelEvent.provider == provider, ChannelEvent.event_id == event_id
    ))
    if event_record and event_record.status == "processed":
        return event_record.response_text
    if event_record is None:
        event_record = ChannelEvent(provider=provider, event_id=event_id[:255], status="received")
        db.add(event_record)
        db.flush()
    user, conversation, identity = _get_identity(db, provider, external_id, display_name, language, account_email)
    auth_response = _telegram_auth_response(db, identity, provider, external_id, display_name, language, question)
    if auth_response is not None:
        event_record.status = "processed"
        event_record.response_text = auth_response[:12000]
        db.commit()
        return auth_response
    previous = db.scalars(select(Message).where(Message.conversation_id == conversation.id).order_by(Message.id.desc()).limit(10)).all()
    history = [{"sender": m.sender, "content": m.content} for m in reversed(previous) if m.sender in {"user", "assistant"}]
    event_record.status = "processing"
    db.add(Message(conversation_id=conversation.id, sender="user", content=question[:8000]))
    db.flush()
    result = run_assistant(question[:2000], db, user, conversation, history)
    answer = result.get("answer") or "I'm sorry, I couldn't prepare a response. Please contact Academy staff."
    db.add(Message(
        conversation_id=conversation.id,
        sender="assistant",
        content=answer[:12000],
        sources=result.get("sources") or None,
    ))
    event_record.status = "processed"
    event_record.response_text = answer[:12000]
    db.commit()
    return answer


def _process_slack_event_background(payload: dict[str, Any], event_id: str) -> None:
    """Process Slack events outside the 3-second Events API acknowledgement window."""
    db = SessionLocal()
    try:
        event = payload.get("event") or {}
        sender_id = str(event.get("user") or "")
        channel_id = str(event.get("channel") or "")
        text = re.sub(r"<@[^>]+>", "", event.get("text", "")).strip()
        if not sender_id or not channel_id or not text:
            return
        team_id = str(payload.get("team_id") or "workspace")
        external_id = f"{team_id}:{sender_id}"
        answer = _process_inbound(
            db, "slack", external_id, f"Slack user {sender_id}", "en", event_id, text,
            _slack_user_email(sender_id),
        )
        if answer:
            thread_ts = event.get("thread_ts") or event.get("ts")
            _slack_send(channel_id, answer, str(thread_ts) if thread_ts else None)
    except Exception:
        db.rollback()
        logger.exception("Background Slack event processing failed")
    finally:
        db.close()


def _verify_slack_signature(body: bytes, timestamp: str | None, signature: str | None) -> bool:
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
    if not expected_secret or not hmac.compare_digest(expected_secret, x_telegram_bot_api_secret_token or ""):
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
        answer = _process_inbound(db, "telegram", external_id, display_name, sender.get("language_code", "en"), update_id, text)
        if answer:
            _telegram_send(message["chat"]["id"], answer)
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
    # Slack requires an acknowledgement within approximately 3 seconds. Persist
    # the event first, then process Gemini and the outbound Slack API call in the
    # response background task.
    existing = db.scalar(select(ChannelEvent).where(
        ChannelEvent.provider == "slack", ChannelEvent.event_id == event_id
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

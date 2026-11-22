from __future__ import annotations
from sqlalchemy.orm import Session
from app.models import Conversation, Message, Handoff, User

CATEGORY_RULES = {
    "admissions": ("admission", "apply", "application", "enroll", "enrol", "eligibility", "applicant"),
    "payments": ("payment", "tuition", "fee", "invoice", "refund", "balance"),
    "programs": ("program", "course", "curriculum", "degree", "class"),
    "schedule": ("schedule", "timetable", "class time", "calendar", "appointment"),
    "student_records": ("grade", "attendance", "student record", "certificate", "transcript"),
    "technical_support": ("login", "password", "account", "website", "error", "technical"),
}
# Armenian/Russian topic cues for multilingual handoff categorization.
CATEGORY_RULES["admissions"] += ("ընդունելություն", "դիմում", "поступление", "заявление")
CATEGORY_RULES["payments"] += ("ուսման վարձ", "վճար", "оплата", "стоимость")
CATEGORY_RULES["programs"] += ("ծրագիր", "դասընթաց", "программа", "курс")
CATEGORY_RULES["schedule"] += ("դասացուցակ", "расписание")
CATEGORY_RULES["student_records"] += ("ուսանող", "քննություն", "студент", "экзамен")

SUGGESTED_ACTIONS = {
    "admissions": "Admissions staff should review the enquiry and contact the applicant with verified eligibility and application guidance.",
    "payments": "Finance staff should review the relevant invoice or payment record and respond through the approved Academy process.",
    "programs": "Academic staff should verify the programme information and provide the user with the current official details.",
    "schedule": "The responsible coordinator should check the current timetable or appointment availability and follow up.",
    "student_records": "Authorized student services staff should review the user's record and respond through the approved channel.",
    "technical_support": "Technical support should investigate the account or platform issue and contact the user with next steps.",
    "other": "Review the conversation, identify the responsible Academy team, and follow up with the user.",
}


def classify_handoff(text: str) -> str:
    value = (text or "").lower()
    for category, words in CATEGORY_RULES.items():
        if any(word in value for word in words):
            return category
    return "other"


def create_handoff(
    conversation: Conversation,
    db: Session,
    requested_by_user_id: int | None,
    reason: str,
    *,
    trigger_type: str = "user_requested",
    question: str | None = None,
    ai_summary: str | None = None,
    suggested_action: str | None = None,
    channel: str | None = None,
) -> Handoff:
    # One active ticket per conversation. Reuse an open ticket rather than spamming staff.
    existing = (
        db.query(Handoff)
        .filter(Handoff.conversation_id == conversation.id, Handoff.status.in_(["pending", "assigned"]))
        .order_by(Handoff.created_at.desc())
        .first()
    )
    if existing:
        # Upgrade metadata when a later explicit request adds context.
        if trigger_type == "user_requested":
            existing.trigger_type = trigger_type
            existing.reason = (reason or existing.reason)[:255]
        if question and not existing.ai_summary:
            existing.ai_summary = ai_summary or f"The user needs assistance with: {question[:700]}"
        db.flush()
        return existing

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation.id)
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )
    context = [{"sender": m.sender, "content": m.content, "created_at": m.created_at.isoformat() if m.created_at else None} for m in messages]
    latest_question = question or next((m.content for m in reversed(messages) if m.sender == "user"), "")
    category = classify_handoff(f"{latest_question} {reason}")
    ticket = Handoff(
        conversation_id=conversation.id,
        requested_by_user_id=requested_by_user_id,
        reason=(reason or "The assistant could not answer confidently")[:255],
        category=category,
        trigger_type=trigger_type,
        ai_summary=(ai_summary or (f"The user needs help with: {latest_question[:700]}" if latest_question else reason))[:5000],
        suggested_action=(suggested_action or SUGGESTED_ACTIONS[category])[:2000],
        channel=channel or getattr(conversation, "channel", None) or "website",
        status="pending",
        conversation_context=context,
    )
    db.add(ticket)
    db.flush()
    ticket.reference_code = f"HO-{ticket.created_at.year if ticket.created_at else '2026'}-{ticket.id:06d}"
    db.flush()
    return ticket


def create_automatic_handoff(conversation: Conversation, db: Session, user: User, question: str, reason: str = "Insufficient verified Academy information") -> Handoff:
    summary = f"The assistant could not verify an answer from the available Academy knowledge. User question: {question[:700]}"
    return create_handoff(conversation, db, user.id, reason, trigger_type="insufficient_information", question=question, ai_summary=summary)


from sqlalchemy.orm import Session

from app.models import Conversation, Message, Handoff


def create_handoff(
    conversation: Conversation,
    db: Session,
    requested_by_user_id: int | None,
    reason: str
) -> Handoff:

    # Avoid creating duplicate pending handoffs
    existing = (
        db.query(Handoff)
        .filter(
            Handoff.conversation_id == conversation.id,
            Handoff.status.in_(["pending", "assigned"])
        )
        .first()
    )

    if existing:
        return existing

    # Capture the full conversation up to this point
    messages = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation.id
        )
        .order_by(Message.created_at.asc(), Message.id.asc())
        .all()
    )

    context = [
        {
            "sender": message.sender,
            "content": message.content,
            "created_at": message.created_at.isoformat()
        }
        for message in messages
    ]

    handoff = Handoff(
        conversation_id=conversation.id,
        requested_by_user_id=requested_by_user_id,
        reason=reason,
        status="pending",
        conversation_context=context
    )

    db.add(handoff)

    return handoff

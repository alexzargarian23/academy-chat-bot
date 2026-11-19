
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User, Conversation, Message, ApplicantLead
from app.services.assistant_service import run_assistant

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ai", tags=["AI"])


def conversation_title(question: str) -> str:
    normalized = " ".join(question.split())
    return normalized if len(normalized) <= 120 else f"{normalized[:117].rstrip()}..."


class ChatRequest(BaseModel):
    conversation_id: int
    question: str = Field(min_length=2, max_length=2000)


@router.post("/chat")
def chat(
    data: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = db.query(Conversation).filter(
        Conversation.id == data.conversation_id,
        Conversation.user_id == current_user.id,
    ).first()

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    try:
        if conversation.applicant_lead_id is None:
            lead = db.query(ApplicantLead).filter(
                ApplicantLead.user_id == current_user.id
            ).first()

            if lead:
                conversation.applicant_lead_id = lead.id

        previous = (
            db.query(Message)
            .filter(Message.conversation_id == conversation.id)
            .order_by(Message.id.desc())
            .limit(10)
            .all()
        )

        history = [
            {"sender": m.sender, "content": m.content}
            for m in reversed(previous)
            if m.sender in ["user", "assistant"]
        ]

        if conversation.title is None and not any(m.sender == "user" for m in previous):
            conversation.title = conversation_title(data.question)

        db.add(
            Message(
                conversation_id=conversation.id,
                sender="user",
                content=data.question,
            )
        )
        db.flush()

        result = run_assistant(
            data.question,
            db,
            current_user,
            conversation,
            history,
        )

        db.add(
            Message(
                conversation_id=conversation.id,
                sender="assistant",
                content=result["answer"],
                sources=result.get("sources") or None,
            )
        )

        db.commit()

        return {
            "conversation_id": conversation.id,
            "answer": result["answer"],
            "sources": result.get("sources", []),
            "handoff_required": result.get("handoff_required", False),
            "handoff_reason": result.get("handoff_reason"),
            "actions": result.get("actions", []),
        }

    except Exception:
        db.rollback()
        logger.exception("Unified AI chat request failed")

        raise HTTPException(
            status_code=502,
            detail="The AI assistant is temporarily unavailable",
        )

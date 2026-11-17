
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User, Conversation, Message
from app.services.gemini_service import generate_response
from app.services.rag_service import answer_question
from app.services.handoff_service import create_handoff

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI"])


class ChatRequest(BaseModel):
    conversation_id: int
    question: str = Field(min_length=2, max_length=2000)


class LegacyChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=2000)


@router.post("/test", deprecated=True)
def test_ai(
    data: LegacyChatRequest,
    current_user: User = Depends(get_current_user),
):
    """Authenticated Gemini smoke test kept for older clients."""
    del current_user

    try:
        answer = generate_response(data.message)
        return {"response": answer}

    except Exception:
        logger.exception("Gemini compatibility request failed")

        raise HTTPException(
            status_code=502,
            detail="The AI assistant is temporarily unavailable",
        )


@router.post("/chat")
def chat(
    data: ChatRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    conversation = db.query(Conversation).filter(
        Conversation.id == data.conversation_id,
        Conversation.user_id == current_user.id
    ).first()

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found"
        )

    try:
        # 1. Retrieve the previous 10 messages.
        previous_messages = (
            db.query(Message)
            .filter(
                Message.conversation_id == conversation.id
            )
            .order_by(Message.id.desc())
            .limit(10)
            .all()
        )

        conversation_history = [
            {
                "sender": message.sender,
                "content": message.content
            }
            for message in reversed(previous_messages)
            if message.sender in ["user", "assistant"]
        ]

        # 2. Save the current user message.
        user_message = Message(
            conversation_id=conversation.id,
            sender="user",
            content=data.question
        )

        db.add(user_message)
        db.flush()

        # 3. Generate the RAG response.
        result = answer_question(
            question=data.question,
            db=db,
            user_role=current_user.role,
            conversation_history=conversation_history
        )
        # Create a staff handoff if RAG cannot find relevant information
        if result.get("handoff_required"):
            create_handoff(
                conversation=conversation,
                db=db,
                requested_by_user_id=current_user.id,
                reason=result.get(
                    "handoff_reason",
                    "The assistant could not answer confidently"
                )
            )

        # 4. Save the assistant response.
        assistant_message = Message(
            conversation_id=conversation.id,
            sender="assistant",
            content=result["answer"]
        )

        db.add(assistant_message)
        db.commit()

        # 5. Return the answer, sources, and handoff information.
        return {
            "conversation_id": conversation.id,
            "answer": result["answer"],
            "sources": result["sources"],
            "handoff_required": result["handoff_required"],
            "handoff_reason": result["handoff_reason"]
        }

    except Exception:
        db.rollback()

        logger.exception("RAG chat request failed")

        raise HTTPException(
            status_code=502,
            detail="The AI assistant is temporarily unavailable"
        )

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User, Handoff, Conversation, Message
from app.services.handoff_service import create_handoff

router = APIRouter(prefix="/handoffs", tags=["Human Handoff"])


class ResolveHandoffRequest(BaseModel):
    staff_notes: str | None = Field(default=None, max_length=5000)


class AssignHandoffRequest(BaseModel):
    staff_user_id: int


class HandoffNoteRequest(BaseModel):
    staff_notes: str = Field(min_length=1, max_length=5000)


class StaffReplyRequest(BaseModel):
    content: str = Field(min_length=1, max_length=10000)


def require_staff(user: User):
    if user.role not in ["staff", "admin"]:
        raise HTTPException(status_code=403, detail="Staff access required")


def serialize_handoff(handoff: Handoff, db: Session) -> dict:
    requester = db.query(User).filter(User.id == handoff.requested_by_user_id).first() if handoff.requested_by_user_id else None
    assignee = db.query(User).filter(User.id == handoff.assigned_to_user_id).first() if handoff.assigned_to_user_id else None
    return {
        "id": handoff.id,
        "reference_code": handoff.reference_code or f"HO-{handoff.id:06d}",
        "conversation_id": handoff.conversation_id,
        "requested_by_user_id": handoff.requested_by_user_id,
        "requester_name": requester.full_name if requester else "Guest",
        "requester_email": requester.email if requester else None,
        "requester_role": requester.role if requester else "guest",
        "assigned_to_user_id": handoff.assigned_to_user_id,
        "assigned_to_name": assignee.full_name if assignee else None,
        "reason": handoff.reason,
        "category": handoff.category,
        "trigger_type": handoff.trigger_type,
        "ai_summary": handoff.ai_summary,
        "suggested_action": handoff.suggested_action,
        "channel": handoff.channel,
        "status": handoff.status,
        "conversation_context": handoff.conversation_context or [],
        "staff_notes": handoff.staff_notes,
        "created_at": handoff.created_at,
        "resolved_at": handoff.resolved_at,
    }


@router.post("/conversations/{conversation_id}")
def request_handoff(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    handoff = create_handoff(
        conversation, db, current_user.id,
        "User requested assistance from Academy staff",
        trigger_type="user_requested",
    )
    db.commit()
    db.refresh(handoff)
    return serialize_handoff(handoff, db)


@router.get("/")
def list_handoffs(
    status: str = "pending",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_staff(current_user)
    if status not in ["pending", "assigned", "resolved", "all"]:
        raise HTTPException(status_code=400, detail="Invalid handoff status")
    query = db.query(Handoff)
    if status != "all":
        query = query.filter(Handoff.status == status)
    rows = query.order_by(Handoff.created_at.desc()).limit(250).all()
    return [serialize_handoff(row, db) for row in rows]


@router.get("/stats")
def handoff_stats(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_staff(current_user)
    return {s: db.query(Handoff).filter(Handoff.status == s).count() for s in ["pending", "assigned", "resolved"]}


@router.get("/staff")
def list_staff(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_staff(current_user)
    return [
        {"id": u.id, "full_name": u.full_name, "email": u.email}
        for u in db.query(User).filter(User.role.in_(["staff", "admin"])).order_by(User.full_name).all()
    ]


@router.get("/{handoff_id}")
def get_handoff(handoff_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_staff(current_user)
    row = db.query(Handoff).filter(Handoff.id == handoff_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Handoff not found")
    return serialize_handoff(row, db)


@router.patch("/{handoff_id}/assign")
def assign_handoff(handoff_id: int, data: AssignHandoffRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_staff(current_user)
    row = db.query(Handoff).filter(Handoff.id == handoff_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Handoff not found")
    if row.status == "resolved":
        raise HTTPException(status_code=400, detail="Resolved handoffs cannot be reassigned")
    staff = db.query(User).filter(User.id == data.staff_user_id, User.role.in_(["staff", "admin"])).first()
    if not staff:
        raise HTTPException(status_code=404, detail="Staff member not found")
    row.assigned_to_user_id = staff.id
    row.status = "assigned"
    db.commit()
    db.refresh(row)
    return serialize_handoff(row, db)


@router.patch("/{handoff_id}/notes")
def add_handoff_notes(handoff_id: int, data: HandoffNoteRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_staff(current_user)
    row = db.query(Handoff).filter(Handoff.id == handoff_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Handoff not found")
    if row.status == "resolved":
        raise HTTPException(status_code=400, detail="Cannot modify a resolved handoff")
    row.staff_notes = data.staff_notes
    db.commit()
    db.refresh(row)
    return serialize_handoff(row, db)


@router.post("/{handoff_id}/reply")
def reply_to_handoff(handoff_id: int, data: StaffReplyRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Send a staff message to the user's original conversation."""
    require_staff(current_user)
    row = db.query(Handoff).filter(Handoff.id == handoff_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Handoff not found")
    conversation = db.query(Conversation).filter(Conversation.id == row.conversation_id).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    now = datetime.now(timezone.utc)
    message = Message(conversation_id=conversation.id, sender="staff", content=data.content.strip())
    conversation.last_response_at = now
    db.add(message)
    db.flush()
    row.conversation_context = list(row.conversation_context or []) + [{
        "sender": "staff", "content": data.content.strip(), "created_at": now.isoformat()
    }]
    db.commit()
    db.refresh(message)
    return {"id": message.id, "conversation_id": message.conversation_id, "sender": message.sender, "content": message.content, "created_at": message.created_at}


@router.patch("/{handoff_id}/resolve")
def resolve_handoff(handoff_id: int, data: ResolveHandoffRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Resolve the support ticket without injecting a generic message into the chat."""
    require_staff(current_user)
    row = db.query(Handoff).filter(Handoff.id == handoff_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Handoff not found")
    if row.status == "resolved":
        raise HTTPException(status_code=400, detail="Handoff is already resolved")

    row.status = "resolved"
    row.assigned_to_user_id = current_user.id
    if data.staff_notes is not None:
        row.staff_notes = data.staff_notes
    row.resolved_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(row)
    return serialize_handoff(row, db)

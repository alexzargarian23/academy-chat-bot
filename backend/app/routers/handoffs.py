
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User, Handoff, Conversation
from app.services.handoff_service import create_handoff

router = APIRouter(prefix="/handoffs", tags=["Human Handoff"])


class ResolveHandoffRequest(BaseModel):
    staff_notes: str | None = Field(default=None, max_length=5000)


class AssignHandoffRequest(BaseModel):
    staff_user_id: int


class HandoffNoteRequest(BaseModel):
    staff_notes: str = Field(min_length=1, max_length=5000)


def require_staff(user: User):
    if user.role not in ["staff", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="Staff access required"
        )


def serialize_handoff(handoff: Handoff) -> dict:
    return {
        "id": handoff.id,
        "conversation_id": handoff.conversation_id,
        "requested_by_user_id": handoff.requested_by_user_id,
        "assigned_to_user_id": handoff.assigned_to_user_id,
        "reason": handoff.reason,
        "status": handoff.status,
        "conversation_context": handoff.conversation_context,
        "staff_notes": handoff.staff_notes,
        "created_at": handoff.created_at,
        "resolved_at": handoff.resolved_at
    }


# 1. Student requests human assistance
@router.post("/conversations/{conversation_id}")
def request_handoff(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id
    ).first()

    if not conversation:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found"
        )

    handoff = create_handoff(
        conversation=conversation,
        db=db,
        requested_by_user_id=current_user.id,
        reason="User requested assistance from Academy staff"
    )

    db.commit()
    db.refresh(handoff)

    return serialize_handoff(handoff)


# 2. Staff views handoff requests
@router.get("/")
def list_handoffs(
    status: str = "pending",
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_staff(current_user)

    if status not in ["pending", "assigned", "resolved", "all"]:
        raise HTTPException(
            status_code=400,
            detail="Invalid handoff status"
        )

    query = db.query(Handoff)

    if status != "all":
        query = query.filter(Handoff.status == status)

    handoffs = query.order_by(
        Handoff.created_at.desc()
    ).all()

    return [
        serialize_handoff(handoff)
        for handoff in handoffs
    ]


# 3. Staff views one handoff in detail
@router.get("/{handoff_id}")
def get_handoff(
    handoff_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_staff(current_user)

    handoff = db.query(Handoff).filter(
        Handoff.id == handoff_id
    ).first()

    if not handoff:
        raise HTTPException(
            status_code=404,
            detail="Handoff not found"
        )

    return serialize_handoff(handoff)


# 4. Assign a handoff to a staff member
@router.patch("/{handoff_id}/assign")
def assign_handoff(
    handoff_id: int,
    data: AssignHandoffRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_staff(current_user)

    handoff = db.query(Handoff).filter(
        Handoff.id == handoff_id
    ).first()

    if not handoff:
        raise HTTPException(
            status_code=404,
            detail="Handoff not found"
        )

    if handoff.status == "resolved":
        raise HTTPException(
            status_code=400,
            detail="Resolved handoffs cannot be reassigned"
        )

    staff_member = db.query(User).filter(
        User.id == data.staff_user_id,
        User.role.in_(["staff", "admin"])
    ).first()

    if not staff_member:
        raise HTTPException(
            status_code=404,
            detail="Staff member not found"
        )

    handoff.assigned_to_user_id = staff_member.id
    handoff.status = "assigned"

    db.commit()
    db.refresh(handoff)

    return serialize_handoff(handoff)


# 5. Add internal staff notes
@router.patch("/{handoff_id}/notes")
def add_handoff_notes(
    handoff_id: int,
    data: HandoffNoteRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_staff(current_user)

    handoff = db.query(Handoff).filter(
        Handoff.id == handoff_id
    ).first()

    if not handoff:
        raise HTTPException(
            status_code=404,
            detail="Handoff not found"
        )

    if handoff.status == "resolved":
        raise HTTPException(
            status_code=400,
            detail="Cannot modify a resolved handoff"
        )

    handoff.staff_notes = data.staff_notes

    db.commit()
    db.refresh(handoff)

    return serialize_handoff(handoff)


# 6. Resolve a handoff
@router.patch("/{handoff_id}/resolve")
def resolve_handoff(
    handoff_id: int,
    data: ResolveHandoffRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_staff(current_user)

    handoff = db.query(Handoff).filter(
        Handoff.id == handoff_id
    ).first()

    if not handoff:
        raise HTTPException(
            status_code=404,
            detail="Handoff not found"
        )

    if handoff.status == "resolved":
        raise HTTPException(
            status_code=400,
            detail="Handoff is already resolved"
        )

    handoff.status = "resolved"
    handoff.assigned_to_user_id = current_user.id

    if data.staff_notes is not None:
        handoff.staff_notes = data.staff_notes

    handoff.resolved_at = datetime.now(timezone.utc)

    db.commit()
    db.refresh(handoff)

    return serialize_handoff(handoff)

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_roles
from app.models import ApplicantLead, Program, User, Conversation, Message
from app.models.appointment import Appointment
from app.schemas.applicant import ApplicantLeadCreate, ApplicantLeadResponse, ApplicantLeadStatusUpdate

router = APIRouter(prefix="/applicants", tags=["Applicants"])
ALLOWED_STATUSES = {"new", "contacted", "qualified", "converted", "rejected"}


@router.post("/register", response_model=ApplicantLeadResponse, status_code=201)
def register_applicant(data: ApplicantLeadCreate, db: Session = Depends(get_db)):
    if data.interested_program_id is not None:
        program = db.query(Program).filter(
            Program.id == data.interested_program_id, Program.is_active.is_(True)
        ).first()
        if not program:
            raise HTTPException(status_code=404, detail="Selected program was not found")

    email = str(data.email).lower()
    existing = db.query(ApplicantLead).filter(ApplicantLead.email == email).first()
    if existing:
        # Enrich an existing lead instead of creating duplicates.
        existing.full_name = data.full_name
        if data.phone:
            existing.phone = data.phone
        if data.interested_program_id is not None:
            existing.interested_program_id = data.interested_program_id
        if data.message:
            existing.message = data.message
        db.commit()
        db.refresh(existing)
        return existing

    account = db.query(User).filter(User.email == email).first()
    applicant = ApplicantLead(
        user_id=account.id if account else None,
        full_name=data.full_name,
        email=email,
        phone=data.phone or "",
        interested_program_id=data.interested_program_id,
        message=data.message,
        source="website_application",
        status="new",
    )
    db.add(applicant)
    db.commit()
    db.refresh(applicant)
    return applicant


@router.get("/", response_model=list[ApplicantLeadResponse])
def get_applicants(db: Session = Depends(get_db), current_user: User = Depends(require_roles("admin"))):
    return db.query(ApplicantLead).order_by(ApplicantLead.created_at.desc()).all()


@router.patch("/{applicant_id}/status")
def update_applicant_status(
    applicant_id: int,
    data: ApplicantLeadStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin")),
):
    if data.status not in ALLOWED_STATUSES:
        raise HTTPException(status_code=400, detail="Invalid applicant status")
    applicant = db.query(ApplicantLead).filter(ApplicantLead.id == applicant_id).first()
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")
    applicant.status = data.status
    db.commit()
    return {"message": "Applicant status updated", "applicant_id": applicant.id, "status": applicant.status}


@router.get("/{applicant_id}/context")
def get_applicant_context(
    applicant_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("staff", "admin")),
):
    del current_user
    applicant = db.query(ApplicantLead).filter(ApplicantLead.id == applicant_id).first()
    if not applicant:
        raise HTTPException(status_code=404, detail="Applicant not found")
    conversations = db.query(Conversation).filter(
        Conversation.applicant_lead_id == applicant.id
    ).order_by(Conversation.created_at.desc()).all()
    conversation_data = []
    for conversation in conversations:
        messages = db.query(Message).filter(
            Message.conversation_id == conversation.id
        ).order_by(Message.created_at.asc()).all()
        conversation_data.append({
            "id": conversation.id,
            "channel": conversation.channel,
            "language": conversation.language,
            "created_at": conversation.created_at,
            "messages": [{"sender": m.sender, "content": m.content, "created_at": m.created_at} for m in messages],
        })
    bookings = db.query(Appointment).filter(Appointment.applicant_lead_id == applicant.id).all()
    return {
        "applicant": ApplicantLeadResponse.model_validate(applicant),
        "conversations": conversation_data,
        "appointments": [{"id": a.id, "slot_id": a.slot_id, "status": a.status, "reason": a.reason} for a in bookings],
    }

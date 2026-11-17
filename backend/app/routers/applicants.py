
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.permissions import require_roles
from app.models import ApplicantLead, Program, User
from app.schemas.applicant import (
    ApplicantLeadCreate,
    ApplicantLeadResponse,
    ApplicantLeadStatusUpdate
)


router = APIRouter(prefix="/applicants", tags=["Applicants"])

ALLOWED_STATUSES = {
    "new",
    "contacted",
    "qualified",
    "converted",
    "rejected"
}


# Public endpoint: prospective students submit their details
@router.post(
    "/register",
    response_model=ApplicantLeadResponse,
    status_code=201
)
def register_applicant(
    data: ApplicantLeadCreate,
    db: Session = Depends(get_db)
):
    if data.interested_program_id is not None:
        program = db.query(Program).filter(
            Program.id == data.interested_program_id,
            Program.is_active.is_(True)
        ).first()

        if not program:
            raise HTTPException(
                status_code=404,
                detail="Selected program was not found"
            )

    applicant = ApplicantLead(
        **data.model_dump(),
        status="new"
    )

    db.add(applicant)
    db.commit()
    db.refresh(applicant)

    return applicant


# Admin endpoint: view all applicant leads
@router.get(
    "/",
    response_model=list[ApplicantLeadResponse]
)
def get_applicants(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin"))
):
    return db.query(ApplicantLead).order_by(
        ApplicantLead.created_at.desc()
    ).all()


# Admin endpoint: update an applicant's status
@router.patch("/{applicant_id}/status")
def update_applicant_status(
    applicant_id: int,
    data: ApplicantLeadStatusUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles("admin"))
):
    if data.status not in ALLOWED_STATUSES:
        raise HTTPException(
            status_code=400,
            detail="Invalid applicant status"
        )

    applicant = db.query(ApplicantLead).filter(
        ApplicantLead.id == applicant_id
    ).first()

    if not applicant:
        raise HTTPException(
            status_code=404,
            detail="Applicant not found"
        )

    applicant.status = data.status
    db.commit()

    return {
        "message": "Applicant status updated",
        "applicant_id": applicant.id,
        "status": applicant.status
    }


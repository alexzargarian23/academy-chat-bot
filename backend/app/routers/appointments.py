from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User, StudentProfile
from app.models.appointment import Appointment, AppointmentSlot
from app.schemas.appointment import AppointmentSlotCreate, AppointmentBook, AppointmentStaffUpdate

router = APIRouter(prefix="/appointments", tags=["Appointments"])

def staff_only(user: User):
    if user.role not in ["staff", "admin"]:
        raise HTTPException(status_code=403, detail="Staff or admin access required")

def my_student(db: Session, user: User):
    student = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    if not student: raise HTTPException(status_code=404, detail="Student profile not found")
    return student

def slot_dict(slot: AppointmentSlot):
    return {"id": slot.id, "appointment_type": slot.appointment_type, "starts_at": slot.starts_at,
            "ends_at": slot.ends_at, "staff_user_id": slot.staff_user_id,
            "staff_name": slot.staff.full_name if slot.staff else None,
            "location": slot.location, "status": slot.status}

def appointment_dict(item: Appointment):
    slot = item.slot; student = item.student_profile
    return {"id": item.id, "slot_id": slot.id, "student_profile_id": student.id,
            "student_number": student.student_number, "student_name": student.user.full_name,
            "appointment_type": slot.appointment_type, "starts_at": slot.starts_at,
            "ends_at": slot.ends_at, "staff_name": slot.staff.full_name if slot.staff else None,
            "location": slot.location, "status": item.status, "reason": item.reason,
            "staff_notes": item.staff_notes, "created_at": item.created_at}

@router.post("/slots", response_model=dict, status_code=status.HTTP_201_CREATED)
def create_slot(data: AppointmentSlotCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    staff_only(user)
    starts = data.starts_at.astimezone(timezone.utc); ends = data.ends_at.astimezone(timezone.utc)
    if starts <= datetime.now(timezone.utc): raise HTTPException(status_code=422, detail="Appointment slots must be in the future")
    if data.staff_user_id:
        staff = db.get(User, data.staff_user_id)
        if not staff or staff.role not in ["staff", "admin"]: raise HTTPException(status_code=404, detail="Staff member not found")
        overlap = db.scalar(select(AppointmentSlot).where(
            AppointmentSlot.staff_user_id == data.staff_user_id,
            AppointmentSlot.status.in_(["available", "booked"]),
            AppointmentSlot.starts_at < ends, AppointmentSlot.ends_at > starts,
        ))
        if overlap: raise HTTPException(status_code=409, detail="This staff member already has an overlapping slot")
    slot = AppointmentSlot(appointment_type=data.appointment_type.strip(), starts_at=starts, ends_at=ends,
                           staff_user_id=data.staff_user_id, location=data.location, status="available", created_by=user.id)
    db.add(slot); db.commit(); db.refresh(slot)
    return slot_dict(slot)

@router.get("/slots", response_model=list[dict])
def list_slots(from_date: datetime | None = None, until: datetime | None = None,
               appointment_type: str | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    now = datetime.now(timezone.utc)
    start = from_date.astimezone(timezone.utc) if from_date and from_date.tzinfo else now
    end = until.astimezone(timezone.utc) if until and until.tzinfo else None
    if from_date and from_date.tzinfo is None or until and until.tzinfo is None:
        raise HTTPException(status_code=422, detail="Date filters must include timezone offsets")
    query = select(AppointmentSlot).options(joinedload(AppointmentSlot.staff)).where(
        AppointmentSlot.status == "available", AppointmentSlot.starts_at >= start)
    if end: query = query.where(AppointmentSlot.starts_at <= end)
    if appointment_type: query = query.where(AppointmentSlot.appointment_type.ilike(f"%{appointment_type.strip()}%"))
    return [slot_dict(x) for x in db.scalars(query.order_by(AppointmentSlot.starts_at).limit(100)).unique().all()]

@router.post("/book", response_model=dict, status_code=status.HTTP_201_CREATED)
def book_slot(data: AppointmentBook, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    student = my_student(db, user)
    slot = db.scalar(select(AppointmentSlot).where(AppointmentSlot.id == data.slot_id).with_for_update())
    if not slot: raise HTTPException(status_code=404, detail="Appointment slot not found")
    if slot.status != "available" or slot.starts_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=409, detail="This appointment slot is no longer available")
    slot.status = "booked"
    item = Appointment(slot_id=slot.id, student_profile_id=student.id, status="booked", reason=data.reason, created_by=user.id)
    db.add(item); db.commit(); db.refresh(item)
    item = db.scalar(select(Appointment).options(joinedload(Appointment.slot).joinedload(AppointmentSlot.staff),
        joinedload(Appointment.student_profile).joinedload(StudentProfile.user)).where(Appointment.id == item.id))
    if item is None:
        raise HTTPException(status_code=500, detail="Appointment could not be loaded after booking")
    return appointment_dict(item)

@router.get("/me", response_model=list[dict])
def my_appointments(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    student = my_student(db, user)
    query = select(Appointment).options(joinedload(Appointment.slot).joinedload(AppointmentSlot.staff),
        joinedload(Appointment.student_profile).joinedload(StudentProfile.user)).where(
        Appointment.student_profile_id == student.id).order_by(Appointment.created_at.desc())
    return [appointment_dict(x) for x in db.scalars(query).unique().all()]

@router.post("/{appointment_id}/cancel", response_model=dict)
def cancel_appointment(appointment_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    student = my_student(db, user)
    item = db.scalar(select(Appointment).options(joinedload(Appointment.slot)).where(
        Appointment.id == appointment_id, Appointment.student_profile_id == student.id).with_for_update())
    if not item: raise HTTPException(status_code=404, detail="Appointment not found")
    if item.status != "booked": raise HTTPException(status_code=409, detail="Only booked appointments can be cancelled")
    item.status = "cancelled"; item.slot.status = "available"
    db.commit()
    return {"cancelled": True, "appointment_id": item.id}

@router.get("/", response_model=list[dict])
def staff_list_appointments(status_filter: str | None = Query(default=None, alias="status"),
                            db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    staff_only(user)
    query = select(Appointment).options(joinedload(Appointment.slot).joinedload(AppointmentSlot.staff),
        joinedload(Appointment.student_profile).joinedload(StudentProfile.user))
    if status_filter:
        if status_filter not in ["booked", "cancelled", "completed", "no_show"]: raise HTTPException(status_code=422, detail="Invalid appointment status")
        query = query.where(Appointment.status == status_filter)
    return [appointment_dict(x) for x in db.scalars(query.order_by(Appointment.created_at.desc())).unique().all()]

@router.patch("/{appointment_id}", response_model=dict)
def staff_update_appointment(appointment_id: int, data: AppointmentStaffUpdate,
                             db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    staff_only(user)
    item = db.scalar(select(Appointment).options(joinedload(Appointment.slot),
        joinedload(Appointment.student_profile).joinedload(StudentProfile.user)).where(Appointment.id == appointment_id))
    if not item: raise HTTPException(status_code=404, detail="Appointment not found")
    updates = data.model_dump(exclude_unset=True)
    if not updates: raise HTTPException(status_code=400, detail="No update fields provided")
    if "status" in updates:
        if updates["status"] is None: raise HTTPException(status_code=422, detail="Status cannot be null")
        if updates["status"] == "cancelled" and item.status == "booked": item.slot.status = "available"
        elif updates["status"] in ["completed", "no_show"]: item.slot.status = "booked"
        item.status = updates["status"]
    if "staff_notes" in updates: item.staff_notes = updates["staff_notes"]
    db.commit(); db.refresh(item)
    return appointment_dict(item)

@router.delete("/slots/{slot_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_slot(slot_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    staff_only(user)
    slot = db.get(AppointmentSlot, slot_id)
    if not slot: raise HTTPException(status_code=404, detail="Slot not found")
    if slot.status == "booked": raise HTTPException(status_code=409, detail="A booked slot cannot be deactivated")
    slot.status = "inactive"; db.commit()
    return None

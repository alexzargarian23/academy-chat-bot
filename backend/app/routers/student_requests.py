from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User, StudentProfile
from app.models.student_request import StudentRequest
from app.schemas.student_request import StudentRequestCreate, StudentRequestStaffUpdate

router = APIRouter(prefix="/student-requests", tags=["Student Requests"])
STATUSES = {"pending", "in_review", "approved", "rejected", "completed", "cancelled"}

def staff_only(user: User):
    if user.role not in ["staff", "admin"]: raise HTTPException(status_code=403, detail="Staff or admin access required")

def serialize(item: StudentRequest):
    return {"id": item.id, "student_profile_id": item.student_profile_id,
            "student_number": item.student_profile.student_number,
            "student_name": item.student_profile.user.full_name,
            "category": item.category, "subject": item.subject, "description": item.description,
            "status": item.status, "staff_notes": item.staff_notes,
            "assigned_to": item.assigned_to,
            "assigned_to_name": item.assignee.full_name if item.assignee else None,
            "created_at": item.created_at, "updated_at": item.updated_at}

def load_request(db: Session, request_id: int):
    item = db.scalar(select(StudentRequest).options(
        joinedload(StudentRequest.student_profile).joinedload(StudentProfile.user),
        joinedload(StudentRequest.assignee)).where(StudentRequest.id == request_id))
    if not item: raise HTTPException(status_code=404, detail="Student request not found")
    return item

@router.post("/", status_code=status.HTTP_201_CREATED)
def create_request(data: StudentRequestCreate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    student = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    if not student: raise HTTPException(status_code=404, detail="Student profile not found")
    item = StudentRequest(student_profile_id=student.id, category=data.category.strip().lower(),
                          subject=data.subject.strip(), description=data.description.strip(), status="pending")
    db.add(item); db.commit(); db.refresh(item)
    return serialize(load_request(db, item.id))

@router.get("/me")
def my_requests(status_filter: str | None = Query(default=None, alias="status"),
                db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    student = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    if not student: raise HTTPException(status_code=404, detail="Student profile not found")
    query = select(StudentRequest).options(joinedload(StudentRequest.student_profile).joinedload(StudentProfile.user),
        joinedload(StudentRequest.assignee)).where(StudentRequest.student_profile_id == student.id)
    if status_filter:
        if status_filter not in STATUSES: raise HTTPException(status_code=422, detail="Invalid status")
        query = query.where(StudentRequest.status == status_filter)
    return [serialize(x) for x in db.scalars(query.order_by(StudentRequest.created_at.desc())).unique().all()]

@router.get("/")
def all_requests(status_filter: str | None = Query(default=None, alias="status"),
                 student_profile_id: int | None = None, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    staff_only(user)
    query = select(StudentRequest).options(joinedload(StudentRequest.student_profile).joinedload(StudentProfile.user), joinedload(StudentRequest.assignee))
    if status_filter:
        if status_filter not in STATUSES: raise HTTPException(status_code=422, detail="Invalid status")
        query = query.where(StudentRequest.status == status_filter)
    if student_profile_id: query = query.where(StudentRequest.student_profile_id == student_profile_id)
    return [serialize(x) for x in db.scalars(query.order_by(StudentRequest.created_at.desc())).unique().all()]

@router.get("/{request_id}")
def get_request(request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    item = load_request(db, request_id)
    if user.role not in ["staff", "admin"] and item.student_profile.user_id != user.id:
        raise HTTPException(status_code=403, detail="You can only view your own requests")
    return serialize(item)

@router.patch("/{request_id}")
def update_request(request_id: int, data: StudentRequestStaffUpdate, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    staff_only(user); item = load_request(db, request_id)
    updates = data.model_dump(exclude_unset=True)
    if not updates: raise HTTPException(status_code=400, detail="No update fields provided")
    if "status" in updates and updates["status"] is None: raise HTTPException(status_code=422, detail="Status cannot be null")
    if updates.get("assigned_to") is not None:
        assignee = db.get(User, updates["assigned_to"])
        if not assignee or assignee.role not in ["staff", "admin"]: raise HTTPException(status_code=404, detail="Staff member not found")
    for key, value in updates.items(): setattr(item, key, value)
    db.commit(); return serialize(load_request(db, item.id))

@router.post("/{request_id}/cancel")
def cancel_request(request_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    student = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    if not student: raise HTTPException(status_code=404, detail="Student profile not found")
    item = load_request(db, request_id)
    if item.student_profile_id != student.id: raise HTTPException(status_code=403, detail="You can only cancel your own requests")
    if item.status != "pending": raise HTTPException(status_code=409, detail="Only pending requests can be cancelled")
    item.status = "cancelled"; db.commit(); return serialize(load_request(db, item.id))

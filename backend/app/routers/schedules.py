from datetime import date
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User, Program, StudentProfile, ClassSchedule
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate, ScheduleResponse

router = APIRouter(prefix="/schedules", tags=["Schedules"])

def require_staff_or_admin(user: User):
    if user.role not in ["staff", "admin"]:
        raise HTTPException(status_code=403, detail="Staff or admin access required")

def serialize(schedule: ClassSchedule):
    return {
        "id": schedule.id, "program_id": schedule.program_id,
        "program_name": schedule.program.name, "course_name": schedule.course_name,
        "description": schedule.description, "academic_year": schedule.academic_year,
        "day_of_week": schedule.day_of_week, "start_time": schedule.start_time,
        "end_time": schedule.end_time, "instructor": schedule.instructor,
        "room": schedule.room, "effective_from": schedule.effective_from,
        "effective_until": schedule.effective_until, "is_active": schedule.is_active,
        "created_at": schedule.created_at,
    }

@router.post("/", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
def create_schedule(data: ScheduleCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_staff_or_admin(current_user)
    if not db.get(Program, data.program_id):
        raise HTTPException(status_code=404, detail="Program not found")
    item = ClassSchedule(**data.model_dump())
    db.add(item); db.commit(); db.refresh(item)
    return serialize(item)

@router.get("/", response_model=list[ScheduleResponse])
def list_schedules(program_id: int | None = Query(default=None, gt=0), academic_year: str | None = None,
                   db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_staff_or_admin(current_user)
    query = select(ClassSchedule).options(joinedload(ClassSchedule.program))
    if program_id is not None: query = query.where(ClassSchedule.program_id == program_id)
    if academic_year: query = query.where(ClassSchedule.academic_year == academic_year)
    return [serialize(x) for x in db.scalars(query.order_by(ClassSchedule.day_of_week, ClassSchedule.start_time)).unique().all()]

@router.get("/me", response_model=list[ScheduleResponse])
def my_schedule(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    student = db.scalar(select(StudentProfile).where(StudentProfile.user_id == current_user.id))
    if not student: raise HTTPException(status_code=404, detail="Student profile not found")
    if not student.program_id or not student.academic_year: return []
    today = date.today()
    query = select(ClassSchedule).options(joinedload(ClassSchedule.program)).where(
        ClassSchedule.program_id == student.program_id, ClassSchedule.academic_year == student.academic_year,
        ClassSchedule.is_active.is_(True), ClassSchedule.effective_from <= today,
        (ClassSchedule.effective_until.is_(None) | (ClassSchedule.effective_until >= today)),
    ).order_by(ClassSchedule.day_of_week, ClassSchedule.start_time)
    return [serialize(x) for x in db.scalars(query).unique().all()]

@router.get("/{schedule_id}", response_model=ScheduleResponse)
def get_schedule(schedule_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    item = db.scalar(select(ClassSchedule).options(joinedload(ClassSchedule.program)).where(ClassSchedule.id == schedule_id))
    if not item: raise HTTPException(status_code=404, detail="Schedule not found")
    if current_user.role not in ["staff", "admin"]:
        student = db.scalar(select(StudentProfile).where(StudentProfile.user_id == current_user.id))
        if not student or student.program_id != item.program_id or student.academic_year != item.academic_year or not item.is_active:
            raise HTTPException(status_code=403, detail="You cannot access this schedule")
    return serialize(item)

@router.patch("/{schedule_id}", response_model=ScheduleResponse)
def update_schedule(schedule_id: int, data: ScheduleUpdate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_staff_or_admin(current_user)
    item = db.scalar(select(ClassSchedule).options(joinedload(ClassSchedule.program)).where(ClassSchedule.id == schedule_id))
    if not item: raise HTTPException(status_code=404, detail="Schedule not found")
    updates = data.model_dump(exclude_unset=True)
    for required in ["program_id", "course_name", "academic_year", "day_of_week", "start_time", "end_time", "effective_from", "is_active"]:
        if required in updates and updates[required] is None:
            raise HTTPException(status_code=422, detail=f"{required} cannot be null")
    if "program_id" in updates and not db.get(Program, updates["program_id"]):
        raise HTTPException(status_code=404, detail="Program not found")
    start = updates.get("start_time", item.start_time); end = updates.get("end_time", item.end_time)
    if end <= start: raise HTTPException(status_code=422, detail="end_time must be later than start_time")
    effective_from = updates.get("effective_from", item.effective_from)
    effective_until = updates.get("effective_until", item.effective_until)
    if effective_until and effective_until < effective_from: raise HTTPException(status_code=422, detail="effective_until cannot be before effective_from")
    for key, value in updates.items(): setattr(item, key, value)
    db.commit(); db.refresh(item)
    return serialize(item)

@router.delete("/{schedule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(schedule_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    require_staff_or_admin(current_user)
    item = db.get(ClassSchedule, schedule_id)
    if not item: raise HTTPException(status_code=404, detail="Schedule not found")
    item.is_active = False
    db.commit()
    return None

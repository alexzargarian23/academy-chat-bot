
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User, Program, StudentProfile, ClassSchedule
from app.schemas.schedule import (
    ScheduleCreate,
    ScheduleUpdate,
    ScheduleResponse
)


router = APIRouter(prefix="/schedules", tags=["Schedules"])


def require_staff_or_admin(user: User):
    if user.role not in ["staff", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="Staff or admin access required"
        )


def build_schedule_response(schedule: ClassSchedule):
    return {
        "id": schedule.id,
        "program_id": schedule.program_id,
        "program_name": schedule.program.name,
        "course_name": schedule.course_name,
        "description": schedule.description,
        "academic_year": schedule.academic_year,
        "day_of_week": schedule.day_of_week,
        "start_time": schedule.start_time,
        "end_time": schedule.end_time,
        "instructor": schedule.instructor,
        "room": schedule.room,
        "effective_from": schedule.effective_from,
        "effective_until": schedule.effective_until,
        "is_active": schedule.is_active,
        "created_at": schedule.created_at
    }


@router.post(
    "/",
    response_model=ScheduleResponse,
    status_code=status.HTTP_201_CREATED
)
def create_schedule(
    data: ScheduleCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_staff_or_admin(current_user)

    program = db.query(Program).filter(
        Program.id == data.program_id
    ).first()

    if not program:
        raise HTTPException(
            status_code=404,
            detail="Program not found"
        )

    schedule = ClassSchedule(**data.model_dump())

    db.add(schedule)
    db.commit()
    db.refresh(schedule)

    return build_schedule_response(schedule)


@router.get(
    "/",
    response_model=list[ScheduleResponse]
)
def list_schedules(
    program_id: int | None = Query(default=None, gt=0),
    academic_year: str | None = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_staff_or_admin(current_user)

    query = db.query(ClassSchedule)

    if program_id is not None:
        query = query.filter(
            ClassSchedule.program_id == program_id
        )

    if academic_year:
        query = query.filter(
            ClassSchedule.academic_year == academic_year
        )

    schedules = query.order_by(
        ClassSchedule.day_of_week,
        ClassSchedule.start_time
    ).all()

    return [
        build_schedule_response(item)
        for item in schedules
    ]


@router.get(
    "/me",
    response_model=list[ScheduleResponse]
)
def get_my_schedule(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    student = db.query(StudentProfile).filter(
        StudentProfile.user_id == current_user.id
    ).first()

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student profile not found"
        )

    if not student.program_id or not student.academic_year:
        return []

    schedules = db.query(ClassSchedule).filter(
        ClassSchedule.program_id == student.program_id,
        ClassSchedule.academic_year == student.academic_year,
        ClassSchedule.is_active.is_(True),
        (
            ClassSchedule.effective_until.is_(None)
            | (ClassSchedule.effective_until >= date.today())
        )
    ).order_by(
        ClassSchedule.day_of_week,
        ClassSchedule.start_time
    ).all()

    return [
        build_schedule_response(item)
        for item in schedules
    ]


@router.get(
    "/{schedule_id}",
    response_model=ScheduleResponse
)
def get_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    schedule = db.query(ClassSchedule).filter(
        ClassSchedule.id == schedule_id
    ).first()

    if not schedule:
        raise HTTPException(
            status_code=404,
            detail="Schedule not found"
        )

    if current_user.role not in ["staff", "admin"]:
        student = db.query(StudentProfile).filter(
            StudentProfile.user_id == current_user.id
        ).first()

        if (
            not student
            or student.program_id != schedule.program_id
            or student.academic_year != schedule.academic_year
            or not schedule.is_active
        ):
            raise HTTPException(
                status_code=403,
                detail="You cannot access this schedule"
            )

    return build_schedule_response(schedule)


@router.patch(
    "/{schedule_id}",
    response_model=ScheduleResponse
)
def update_schedule(
    schedule_id: int,
    data: ScheduleUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_staff_or_admin(current_user)

    schedule = db.query(ClassSchedule).filter(
        ClassSchedule.id == schedule_id
    ).first()

    if not schedule:
        raise HTTPException(
            status_code=404,
            detail="Schedule not found"
        )

    updates = data.model_dump(exclude_unset=True)

    if "program_id" in updates:
        if updates["program_id"] is None:
            raise HTTPException(
                status_code=400,
                detail="Program ID cannot be null"
            )

        program = db.query(Program).filter(
            Program.id == updates["program_id"]
        ).first()

        if not program:
            raise HTTPException(
                status_code=404,
                detail="Program not found"
            )

    proposed_start = updates.get(
        "start_time", schedule.start_time
    )
    proposed_end = updates.get(
        "end_time", schedule.end_time
    )

    if proposed_end <= proposed_start:
        raise HTTPException(
            status_code=400,
            detail="End time must be later than start time"
        )

    proposed_from = updates.get(
        "effective_from", schedule.effective_from
    )
    proposed_until = updates.get(
        "effective_until", schedule.effective_until
    )

    if (
        proposed_until is not None
        and proposed_until < proposed_from
    ):
        raise HTTPException(
            status_code=400,
            detail="End date cannot be before start date"
        )

    for field, value in updates.items():
        setattr(schedule, field, value)

    db.commit()
    db.refresh(schedule)

    return build_schedule_response(schedule)


@router.delete("/{schedule_id}")
def delete_schedule(
    schedule_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_staff_or_admin(current_user)

    schedule = db.query(ClassSchedule).filter(
        ClassSchedule.id == schedule_id
    ).first()

    if not schedule:
        raise HTTPException(
            status_code=404,
            detail="Schedule not found"
        )

    db.delete(schedule)
    db.commit()

    return {
        "message": "Schedule deleted successfully"
    }

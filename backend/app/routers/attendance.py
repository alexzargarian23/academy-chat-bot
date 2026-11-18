
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user

from app.models.user import User
from app.models.student import StudentProfile
from app.models.schedule import ClassSchedule
from app.models.attendance import AttendanceRecord

from app.schemas.attendance import (
    AttendanceCreate,
    AttendanceUpdate,
    AttendanceResponse,
    AttendanceSummary,
)


router = APIRouter(
    prefix="/attendance",
    tags=["Attendance"],
)


def require_staff_or_admin(current_user: User):
    if current_user.role not in ["staff", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff and administrators can perform this action.",
        )


def build_attendance_response(
    record: AttendanceRecord,
) -> AttendanceResponse:
    student = record.student_profile
    schedule = record.schedule

    return AttendanceResponse(
        id=record.id,
        student_profile_id=student.id,
        student_number=student.student_number,
        student_name=student.user.full_name,
        schedule_id=schedule.id,
        course_name=schedule.course_name,
        program_name=schedule.program.name,
        academic_year=schedule.academic_year,
        attendance_date=record.attendance_date,
        status=record.status,
        notes=record.notes,
        recorded_by=record.recorded_by,
        recorded_by_name=record.recorder.full_name,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def get_student_profile(
    db: Session,
    user_id: int,
) -> StudentProfile:
    profile = db.scalar(
        select(StudentProfile).where(
            StudentProfile.user_id == user_id
        )
    )

    if not profile:
        raise HTTPException(
            status_code=404,
            detail="Student profile not found.",
        )

    return profile


def validate_student_schedule(
    student: StudentProfile,
    schedule: ClassSchedule,
    attendance_date: date,
):
    if student.program_id != schedule.program_id:
        raise HTTPException(
            status_code=400,
            detail="The student is not enrolled in this schedule's program.",
        )

    if student.academic_year != schedule.academic_year:
        raise HTTPException(
            status_code=400,
            detail="The student's academic year does not match the schedule.",
        )

    if not schedule.is_active:
        raise HTTPException(
            status_code=400,
            detail="This schedule is inactive.",
        )

    if attendance_date < schedule.effective_from:
        raise HTTPException(
            status_code=400,
            detail="The attendance date is before the schedule's effective date.",
        )

    if (
        schedule.effective_until is not None
        and attendance_date > schedule.effective_until
    ):
        raise HTTPException(
            status_code=400,
            detail="The attendance date is after the schedule's effective period.",
        )

    weekday = attendance_date.strftime("%A").lower()

    if weekday != schedule.day_of_week.lower():
        raise HTTPException(
            status_code=400,
            detail=(
                f"This class is scheduled for {schedule.day_of_week}, "
                f"not {weekday}."
            ),
        )


def build_student_summary(
    db: Session,
    student: StudentProfile,
) -> AttendanceSummary:
    counts = {
        "present": 0,
        "absent": 0,
        "late": 0,
        "excused": 0,
    }

    rows = db.execute(
        select(
            AttendanceRecord.status,
            func.count(AttendanceRecord.id),
        )
        .where(
            AttendanceRecord.student_profile_id == student.id
        )
        .group_by(AttendanceRecord.status)
    ).all()

    for attendance_status, count in rows:
        if attendance_status in counts:
            counts[attendance_status] = count

    total = sum(counts.values())

    # Excused records are excluded from the attendance percentage.
    eligible_records = (
        counts["present"] + counts["absent"] + counts["late"]
    )

    if eligible_records:
        percentage = round(
            (
                counts["present"] + counts["late"]
            ) / eligible_records * 100,
            2,
        )
    else:
        percentage = 0.0

    return AttendanceSummary(
        student_profile_id=student.id,
        student_number=student.student_number,
        student_name=student.user.full_name,
        total_records=total,
        present=counts["present"],
        absent=counts["absent"],
        late=counts["late"],
        excused=counts["excused"],
        attendance_percentage=percentage,
    )


# ---------------------------------------------------------
# CREATE ATTENDANCE
# Staff/admin only
# ---------------------------------------------------------

@router.post(
    "/",
    response_model=AttendanceResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_attendance(
    payload: AttendanceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_staff_or_admin(current_user)

    student = db.get(StudentProfile, payload.student_profile_id)

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student profile not found.",
        )

    schedule = db.get(ClassSchedule, payload.schedule_id)

    if not schedule:
        raise HTTPException(
            status_code=404,
            detail="Class schedule not found.",
        )

    validate_student_schedule(
        student,
        schedule,
        payload.attendance_date,
    )

    existing = db.scalar(
        select(AttendanceRecord).where(
            AttendanceRecord.student_profile_id == student.id,
            AttendanceRecord.schedule_id == schedule.id,
            AttendanceRecord.attendance_date == payload.attendance_date,
        )
    )

    if existing:
        raise HTTPException(
            status_code=409,
            detail="Attendance has already been recorded for this student and class on this date.",
        )

    record = AttendanceRecord(
        student_profile_id=student.id,
        schedule_id=schedule.id,
        attendance_date=payload.attendance_date,
        status=payload.status,
        notes=payload.notes,
        recorded_by=current_user.id,
    )

    db.add(record)

    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An attendance record already exists for this student, class, and date.",
        )

    db.refresh(record)

    return build_attendance_response(record)


# ---------------------------------------------------------
# STUDENT: VIEW OWN ATTENDANCE
# ---------------------------------------------------------

@router.get(
    "/me",
    response_model=list[AttendanceResponse],
)
def get_my_attendance(
    date_from: date | None = None,
    date_to: date | None = None,
    attendance_status: str | None = Query(
        default=None,
        alias="status",
        pattern="^(present|absent|late|excused)$",
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    student = get_student_profile(db, current_user.id)

    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=400,
            detail="date_from cannot be later than date_to.",
        )

    query = select(AttendanceRecord).where(
        AttendanceRecord.student_profile_id == student.id
    )

    if date_from:
        query = query.where(
            AttendanceRecord.attendance_date >= date_from
        )

    if date_to:
        query = query.where(
            AttendanceRecord.attendance_date <= date_to
        )

    if attendance_status:
        query = query.where(
            AttendanceRecord.status == attendance_status
        )

    records = db.scalars(
        query.order_by(
            AttendanceRecord.attendance_date.desc(),
            AttendanceRecord.id.desc(),
        )
        .offset(skip)
        .limit(limit)
    ).all()

    return [
        build_attendance_response(record)
        for record in records
    ]


# ---------------------------------------------------------
# STUDENT: VIEW OWN ATTENDANCE SUMMARY
# ---------------------------------------------------------

@router.get(
    "/me/summary",
    response_model=AttendanceSummary,
)
def get_my_attendance_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    student = get_student_profile(db, current_user.id)

    return build_student_summary(db, student)


# ---------------------------------------------------------
# STAFF: VIEW ALL ATTENDANCE
# ---------------------------------------------------------

@router.get(
    "/",
    response_model=list[AttendanceResponse],
)
def get_all_attendance(
    student_profile_id: int | None = Query(default=None, gt=0),
    schedule_id: int | None = Query(default=None, gt=0),
    attendance_date: date | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    attendance_status: str | None = Query(
        default=None,
        alias="status",
        pattern="^(present|absent|late|excused)$",
    ),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_staff_or_admin(current_user)

    if date_from and date_to and date_from > date_to:
        raise HTTPException(
            status_code=400,
            detail="date_from cannot be later than date_to.",
        )

    query = select(AttendanceRecord)

    if student_profile_id:
        query = query.where(
            AttendanceRecord.student_profile_id == student_profile_id
        )

    if schedule_id:
        query = query.where(
            AttendanceRecord.schedule_id == schedule_id
        )

    if attendance_date:
        query = query.where(
            AttendanceRecord.attendance_date == attendance_date
        )

    if date_from:
        query = query.where(
            AttendanceRecord.attendance_date >= date_from
        )

    if date_to:
        query = query.where(
            AttendanceRecord.attendance_date <= date_to
        )

    if attendance_status:
        query = query.where(
            AttendanceRecord.status == attendance_status
        )

    records = db.scalars(
        query.order_by(
            AttendanceRecord.attendance_date.desc(),
            AttendanceRecord.id.desc(),
        )
        .offset(skip)
        .limit(limit)
    ).all()

    return [
        build_attendance_response(record)
        for record in records
    ]


# ---------------------------------------------------------
# STAFF: VIEW A STUDENT'S ATTENDANCE SUMMARY
# ---------------------------------------------------------

@router.get(
    "/students/{student_profile_id}/summary",
    response_model=AttendanceSummary,
)
def get_student_attendance_summary(
    student_profile_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_staff_or_admin(current_user)

    student = db.get(StudentProfile, student_profile_id)

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student profile not found.",
        )

    return build_student_summary(db, student)


# ---------------------------------------------------------
# VIEW ONE ATTENDANCE RECORD
# Student owner or staff/admin
# ---------------------------------------------------------

@router.get(
    "/{attendance_id}",
    response_model=AttendanceResponse,
)
def get_attendance(
    attendance_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    record = db.get(AttendanceRecord, attendance_id)

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Attendance record not found.",
        )

    if current_user.role not in ["staff", "admin"]:
        if record.student_profile.user_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You can only view your own attendance records.",
            )

    return build_attendance_response(record)


# ---------------------------------------------------------
# UPDATE ATTENDANCE
# Staff/admin only
# ---------------------------------------------------------

@router.patch(
    "/{attendance_id}",
    response_model=AttendanceResponse,
)
def update_attendance(
    attendance_id: int,
    payload: AttendanceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_staff_or_admin(current_user)

    record = db.get(AttendanceRecord, attendance_id)

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Attendance record not found.",
        )

    updates = payload.model_dump(exclude_unset=True)

    if not updates:
        raise HTTPException(
            status_code=400,
            detail="No update fields provided.",
        )

    for field, value in updates.items():
        setattr(record, field, value)

    db.commit()
    db.refresh(record)

    return build_attendance_response(record)

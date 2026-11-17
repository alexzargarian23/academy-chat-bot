
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User, Program, StudentProfile
from app.schemas.student import (
    StudentProfileCreate,
    StudentProfileUpdate,
    StudentProfileResponse
)

router = APIRouter(prefix="/students", tags=["Students"])


def require_staff_or_admin(current_user: User):
    if current_user.role not in ["staff", "admin"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Staff or admin access required"
        )


def build_student_response(student: StudentProfile):
    return {
        "id": student.id,
        "user_id": student.user_id,
        "student_number": student.student_number,
        "program_id": student.program_id,
        "phone": student.phone,
        "academic_year": student.academic_year,
        "enrollment_status": student.enrollment_status,
        "enrollment_date": student.enrollment_date,
        "created_at": student.created_at,
        "full_name": student.user.full_name,
        "email": student.user.email,
        "program_name": (
            student.program.name if student.program else None
        )
    }


@router.post(
    "/",
    response_model=StudentProfileResponse,
    status_code=status.HTTP_201_CREATED
)
def create_student(
    data: StudentProfileCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_staff_or_admin(current_user)

    user = db.query(User).filter(User.id == data.user_id).first()

    if not user:
        raise HTTPException(
            status_code=404,
            detail="User not found"
        )

    if user.role != "student":
        raise HTTPException(
            status_code=400,
            detail="Only users with the student role can have student profiles"
        )

    existing_profile = db.query(StudentProfile).filter(
        StudentProfile.user_id == data.user_id
    ).first()

    if existing_profile:
        raise HTTPException(
            status_code=409,
            detail="This user already has a student profile"
        )

    existing_number = db.query(StudentProfile).filter(
        StudentProfile.student_number == data.student_number
    ).first()

    if existing_number:
        raise HTTPException(
            status_code=409,
            detail="Student number already exists"
        )

    if data.program_id is not None:
        program = db.query(Program).filter(
            Program.id == data.program_id
        ).first()

        if not program:
            raise HTTPException(
                status_code=404,
                detail="Program not found"
            )

    student = StudentProfile(**data.model_dump())

    db.add(student)
    db.commit()
    db.refresh(student)

    return build_student_response(student)


@router.get("/me", response_model=StudentProfileResponse)
def get_my_student_profile(
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

    return build_student_response(student)


@router.get("/", response_model=list[StudentProfileResponse])
def list_students(
    search: str | None = Query(default=None, min_length=1),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_staff_or_admin(current_user)

    query = db.query(StudentProfile).join(
        User,
        StudentProfile.user_id == User.id
    ).outerjoin(
        Program,
        StudentProfile.program_id == Program.id
    )

    if search:
        term = f"%{search.strip()}%"
        query = query.filter(
            or_(
                User.full_name.ilike(term),
                User.email.ilike(term),
                StudentProfile.student_number.ilike(term)
            )
        )

    students = query.order_by(
        StudentProfile.id.desc()
    ).offset(skip).limit(limit).all()

    return [
        build_student_response(student)
        for student in students
    ]


@router.get("/{student_id}", response_model=StudentProfileResponse)
def get_student(
    student_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    student = db.query(StudentProfile).filter(
        StudentProfile.id == student_id
    ).first()

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student profile not found"
        )

    if current_user.role not in ["staff", "admin"]:
        if student.user_id != current_user.id:
            raise HTTPException(
                status_code=403,
                detail="You cannot access another student's profile"
            )

    return build_student_response(student)


@router.patch(
    "/{student_id}",
    response_model=StudentProfileResponse
)
def update_student(
    student_id: int,
    data: StudentProfileUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_staff_or_admin(current_user)

    student = db.query(StudentProfile).filter(
        StudentProfile.id == student_id
    ).first()

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student profile not found"
        )

    updates = data.model_dump(exclude_unset=True)

    if "student_number" in updates and updates["student_number"] is not None:
        existing = db.query(StudentProfile).filter(
            StudentProfile.student_number == updates["student_number"],
            StudentProfile.id != student_id
        ).first()

        if existing:
            raise HTTPException(
                status_code=409,
                detail="Student number already exists"
            )

    if "program_id" in updates and updates["program_id"] is not None:
        program = db.query(Program).filter(
            Program.id == updates["program_id"]
        ).first()

        if not program:
            raise HTTPException(
                status_code=404,
                detail="Program not found"
            )

    allowed_statuses = [
        "active",
        "graduated",
        "suspended",
        "withdrawn"
    ]

    if (
        "enrollment_status" in updates
        and updates["enrollment_status"] not in allowed_statuses
    ):
        raise HTTPException(
            status_code=400,
            detail="Invalid enrollment status"
        )

    for field, value in updates.items():
        setattr(student, field, value)

    db.commit()
    db.refresh(student)

    return build_student_response(student)

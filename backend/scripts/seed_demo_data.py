"""Create the demo AI student, staff account, records, and document visibility."""
from __future__ import annotations

import secrets
import sys
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import (
    ApplicantLead,
    AttendanceRecord,
    ClassSchedule,
    Document,
    Program,
    StudentInvoice,
    StudentPayment,
    StudentGrade,
    StudentProfile,
    User,
)


STUDENT_EMAIL = "ai.demo.student@example.com"
STUDENT_NAME = "AI Demo Student"
STUDENT_NUMBER = "AI-DEMO-001"
STAFF_EMAIL = "vardan@example.com"
STAFF_NAME = "Vardan Grigoryan"
ACADEMIC_YEAR = "2026-2027"
PAYMENT_DUE_DATE = date(2026, 11, 30)
INVOICE_DESCRIPTION = "Next tuition payment (mock)"


def _get_or_create_user(db, email: str, full_name: str, role: str) -> tuple[User, str | None]:
    user = db.scalar(select(User).where(func.lower(User.email) == email.lower()))
    generated_password = None
    if user is None:
        generated_password = secrets.token_urlsafe(15)
        user = User(
            full_name=full_name,
            email=email,
            password_hash=hash_password(generated_password),
            role=role,
        )
        db.add(user)
        db.flush()
    else:
        user.full_name = full_name
        user.role = role
    return user, generated_password


def _get_or_create_student_profile(
    db,
    user: User,
    program: Program,
    student_number: str = STUDENT_NUMBER,
) -> StudentProfile:
    profile = db.scalar(select(StudentProfile).where(StudentProfile.user_id == user.id))
    conflicting_profile = db.scalar(
        select(StudentProfile).where(
            StudentProfile.student_number == student_number,
            StudentProfile.user_id != user.id,
        )
    )
    if conflicting_profile:
        raise RuntimeError(f"Student number {student_number} belongs to another user")
    if profile is None:
        profile = StudentProfile(
            user_id=user.id,
            student_number=student_number,
            program_id=program.id,
            academic_year=ACADEMIC_YEAR,
            enrollment_status="active",
            enrollment_date=datetime.now(timezone.utc),
        )
        db.add(profile)
        db.flush()
    else:
        profile.student_number = student_number
        profile.program_id = program.id
        profile.academic_year = ACADEMIC_YEAR
        profile.enrollment_status = "active"
    return profile


def _ensure_lead(db, user: User) -> None:
    lead = db.scalar(select(ApplicantLead).where(ApplicantLead.user_id == user.id))
    if lead is None:
        db.add(ApplicantLead(
            user_id=user.id,
            full_name=user.full_name,
            email=user.email,
            phone="",
            source="demo_seed",
            status="new",
            contact_consent=False,
            message="Demo student account created for testing.",
        ))


def _ensure_invoice(
    db,
    profile: StudentProfile,
    staff: User,
    description: str = INVOICE_DESCRIPTION,
    total_amount: Decimal = Decimal("500.00"),
) -> StudentInvoice:
    invoice = db.scalar(select(StudentInvoice).where(
        StudentInvoice.student_profile_id == profile.id,
        StudentInvoice.description == description,
    ))
    if invoice is None:
        invoice = StudentInvoice(
            student_profile_id=profile.id,
            description=description,
            academic_year=ACADEMIC_YEAR,
            total_amount=total_amount,
            currency="USD",
            due_date=PAYMENT_DUE_DATE,
            status="unpaid",
            created_by=staff.id,
        )
        db.add(invoice)
        db.flush()
    return invoice


def _ensure_payment(
    db,
    invoice: StudentInvoice,
    staff: User,
    amount: Decimal,
    reference: str,
) -> StudentPayment | None:
    payment = db.scalar(select(StudentPayment).where(
        StudentPayment.invoice_id == invoice.id,
        StudentPayment.reference == reference,
    ))
    if payment is None and amount > 0:
        payment = StudentPayment(
            invoice_id=invoice.id,
            amount=amount,
            method="bank_transfer",
            reference=reference,
            received_by=staff.id,
        )
        db.add(payment)
        db.flush()
    paid = Decimal("0.00")
    for item in invoice.payments:
        paid += Decimal(str(item.amount or 0))
    balance = invoice.total_amount - paid
    invoice.status = "paid" if balance <= 0 else "partially_paid" if paid > 0 else "unpaid"
    return payment


def _ensure_grade(
    db,
    profile: StudentProfile,
    schedule: ClassSchedule,
    staff: User,
    assessment_name: str,
    score: Decimal,
    max_score: Decimal,
    letter_grade: str,
    feedback: str,
) -> StudentGrade:
    grade = db.scalar(select(StudentGrade).where(
        StudentGrade.student_profile_id == profile.id,
        StudentGrade.schedule_id == schedule.id,
        StudentGrade.assessment_name == assessment_name,
    ))
    if grade is None:
        grade = StudentGrade(
            student_profile_id=profile.id,
            schedule_id=schedule.id,
            assessment_name=assessment_name,
            score=score,
            max_score=max_score,
            letter_grade=letter_grade,
            academic_year=ACADEMIC_YEAR,
            feedback=feedback,
            graded_at=date(2026, 11, 10),
            graded_by=staff.id,
        )
        db.add(grade)
    else:
        grade.score = score
        grade.max_score = max_score
        grade.letter_grade = letter_grade
        grade.feedback = feedback
        grade.graded_by = staff.id
    return grade


def _ensure_staff_demo_students(db, staff: User, program: Program) -> list[tuple[User, str | None]]:
    schedules = db.scalars(select(ClassSchedule).where(
        ClassSchedule.program_id == program.id,
        ClassSchedule.academic_year == ACADEMIC_YEAR,
        ClassSchedule.is_active.is_(True),
    ).order_by(ClassSchedule.id)).all()
    if not schedules:
        raise RuntimeError("No active AI schedules exist for demo grades")
    schedule = schedules[0]
    specs = [
        ("ai.demo.student@example.com", "AI Demo Student", "AI-DEMO-001", Decimal("500.00"), "paid", Decimal("500.00")),
        ("ai.demo.student2@example.com", "AI Demo Student Two", "AI-DEMO-002", Decimal("600.00"), "partially_paid", Decimal("300.00")),
        ("ai.demo.student3@example.com", "AI Demo Student Three", "AI-DEMO-003", Decimal("450.00"), "unpaid", Decimal("0.00")),
    ]
    results = []
    for email, name, student_number, total, expected_status, paid_amount in specs:
        user, generated_password = _get_or_create_user(db, email, name, "student")
        profile = _get_or_create_student_profile(db, user, program, student_number)
        _ensure_lead(db, user)
        invoice = _ensure_invoice(db, profile, staff, f"November tuition ({expected_status} demo)", total)
        _ensure_payment(db, invoice, staff, paid_amount, f"demo-{student_number}-november")
        _ensure_grade(db, profile, schedule, staff, "Midterm project", Decimal("88"), Decimal("100"), "B+", "Strong work on the retrieval pipeline.")
        _ensure_grade(db, profile, schedule, staff, "Final assessment", Decimal("92"), Decimal("100"), "A-", "Clear explanation and reliable implementation.")
        results.append((user, generated_password))
    return results


def _schedule_weekday(schedule: ClassSchedule) -> int | None:
    weekdays = {
        "monday": 0, "tuesday": 1, "wednesday": 2,
        "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6,
    }
    return weekdays.get(schedule.day_of_week.strip().lower())


def _ensure_attendance(db, profile: StudentProfile, staff: User, program: Program) -> int:
    schedules = db.scalars(select(ClassSchedule).where(
        ClassSchedule.program_id == program.id,
        ClassSchedule.academic_year == ACADEMIC_YEAR,
        ClassSchedule.is_active.is_(True),
    ).order_by(ClassSchedule.id)).all()
    if not schedules:
        raise RuntimeError("No active AI schedules exist for academic year 2026-2027")

    existing = db.scalars(select(AttendanceRecord).where(
        AttendanceRecord.student_profile_id == profile.id,
    )).all()
    for record in existing:
        record.status = "present"
        record.recorded_by = staff.id
    existing_keys = {(record.schedule_id, record.attendance_date) for record in existing}

    today = date.today()
    next_date = today
    added = 0
    while len(existing) + added < 100 and next_date >= today - timedelta(days=3650):
        for schedule in schedules:
            weekday = _schedule_weekday(schedule)
            if weekday is None or next_date.weekday() != weekday:
                continue
            if next_date < schedule.effective_from:
                continue
            if schedule.effective_until is not None and next_date > schedule.effective_until:
                continue
            key = (schedule.id, next_date)
            if key in existing_keys:
                continue
            db.add(AttendanceRecord(
                student_profile_id=profile.id,
                schedule_id=schedule.id,
                attendance_date=next_date,
                status="present",
                notes="Demo attendance record",
                recorded_by=staff.id,
            ))
            existing_keys.add(key)
            added += 1
            if len(existing) + added >= 100:
                break
        next_date -= timedelta(days=1)

    if len(existing) + added < 100:
        raise RuntimeError("Could not create 100 valid attendance records from available AI schedules")
    return added


def _set_document_visibility(db) -> tuple[int, int | None]:
    documents = db.scalars(select(Document)).all()
    document_7 = next((document for document in documents if document.id == 7), None)
    if document_7 is None:
        return len(documents), None
    for document in documents:
        document.visibility = "admin" if document.id == 7 else "student"
    return len(documents), document_7.id


def main() -> None:
    db = SessionLocal()
    try:
        program = db.scalar(select(Program).where(
            func.lower(Program.name) == "ai",
            Program.is_active.is_(True),
        ))
        if program is None:
            raise RuntimeError("Active program named AI was not found")

        staff, staff_password = _get_or_create_user(db, STAFF_EMAIL, STAFF_NAME, "staff")
        demo_students = _ensure_staff_demo_students(db, staff, program)
        student, student_password = demo_students[0]
        profile = _get_or_create_student_profile(db, student, program, STUDENT_NUMBER)
        attendance_added = _ensure_attendance(db, profile, staff, program)
        document_count, protected_document_id = _set_document_visibility(db)
        db.commit()

        print(f"Seeded student: {student.email} (id={student.id}, profile_id={profile.id})")
        if student_password:
            print(f"Student password: {student_password}")
        else:
            print("Student password: existing password retained")
        print(f"Seeded staff: {staff.email} (id={staff.id})")
        if staff_password:
            print(f"Staff password: {staff_password}")
        else:
            print("Staff password: existing password retained")
        for demo_student, generated_password in demo_students:
            if generated_password:
                print(f"Demo student password ({demo_student.email}): {generated_password}")
        visibility_note = (
            f"document {protected_document_id} set to admin-only"
            if protected_document_id is not None
            else "document 7 not present; existing document visibility preserved"
        )
        print(f"AI program: {program.id}; attendance rows added: {attendance_added}; documents found: {document_count}; {visibility_note}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()

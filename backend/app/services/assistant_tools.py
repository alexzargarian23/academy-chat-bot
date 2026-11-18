"""Authenticated, narrowly-scoped tools available to the Academy assistant."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import (
    User, StudentProfile, ClassSchedule, StudentInvoice,
    AttendanceRecord,
)
from app.models.student_request import StudentRequest
from app.models.appointment import Appointment, AppointmentSlot
from app.services.retrieval_service import search_knowledge
from app.services.handoff_service import create_handoff


def _student_profile(db: Session, user: User) -> StudentProfile | None:
    return db.scalar(
        select(StudentProfile)
        .options(joinedload(StudentProfile.user), joinedload(StudentProfile.program))
        .where(StudentProfile.user_id == user.id)
    )


def _money(value: Decimal | int | float | None) -> float:
    return float(value or 0)


def tool_get_my_profile(db: Session, user: User, args: dict) -> dict:
    del args
    student = _student_profile(db, user)
    if not student:
        return {"found": False, "message": "No student profile is linked to this account."}
    return {
        "found": True,
        "student_number": student.student_number,
        "full_name": student.user.full_name,
        "email": student.user.email,
        "program": student.program.name if student.program else None,
        "academic_year": student.academic_year,
        "enrollment_status": student.enrollment_status,
        "enrollment_date": student.enrollment_date.isoformat() if student.enrollment_date else None,
    }


def tool_get_my_schedule(db: Session, user: User, args: dict) -> dict:
    del args
    student = _student_profile(db, user)
    if not student:
        return {"found": False, "message": "No student profile is linked to this account."}
    if not student.program_id or not student.academic_year:
        return {"found": True, "classes": [], "message": "The student profile has no program or academic year assigned."}
    today = date.today()
    rows = db.scalars(
        select(ClassSchedule)
        .options(joinedload(ClassSchedule.program))
        .where(
            ClassSchedule.program_id == student.program_id,
            ClassSchedule.academic_year == student.academic_year,
            ClassSchedule.is_active.is_(True),
            ClassSchedule.effective_from <= today,
            (ClassSchedule.effective_until.is_(None) | (ClassSchedule.effective_until >= today)),
        )
        .order_by(ClassSchedule.day_of_week, ClassSchedule.start_time)
    ).all()
    return {"found": True, "classes": [{
        "course": row.course_name,
        "day": row.day_of_week,
        "start_time": row.start_time.isoformat(),
        "end_time": row.end_time.isoformat(),
        "instructor": row.instructor,
        "room": row.room,
        "academic_year": row.academic_year,
    } for row in rows]}


def tool_get_my_payments(db: Session, user: User, args: dict) -> dict:
    del args
    student = _student_profile(db, user)
    if not student:
        return {"found": False, "message": "No student profile is linked to this account."}
    invoices = db.scalars(
        select(StudentInvoice)
        .options(joinedload(StudentInvoice.payments))
        .where(StudentInvoice.student_profile_id == student.id)
        .order_by(StudentInvoice.created_at.desc())
    ).unique().all()
    items = []
    total_due = Decimal("0.00")
    for invoice in invoices:
        paid = Decimal("0.00")
        for payment in invoice.payments:
            paid += payment.amount
        balance = invoice.total_amount - paid
        if invoice.status != "cancelled":
            total_due += balance
        items.append({
            "description": invoice.description,
            "academic_year": invoice.academic_year,
            "total_amount": _money(invoice.total_amount),
            "paid_amount": _money(paid),
            "balance": _money(balance),
            "currency": invoice.currency,
            "due_date": invoice.due_date.isoformat() if invoice.due_date else None,
            "status": invoice.status,
        })
    currencies = sorted({i.currency for i in invoices if i.status != "cancelled"})
    return {
        "found": True,
        "invoices": items,
        "total_outstanding": _money(total_due),
        "currency_note": "Outstanding total is meaningful as one amount only when invoices use the same currency.",
        "currencies": currencies,
    }


def tool_get_my_attendance(db: Session, user: User, args: dict) -> dict:
    del args
    student = _student_profile(db, user)
    if not student:
        return {"found": False, "message": "No student profile is linked to this account."}
    rows = db.execute(
        select(AttendanceRecord.status, func.count(AttendanceRecord.id))
        .where(AttendanceRecord.student_profile_id == student.id)
        .group_by(AttendanceRecord.status)
    ).all()
    counts = {"present": 0, "absent": 0, "late": 0, "excused": 0}
    for status_name, count in rows:
        if status_name in counts:
            counts[status_name] = int(count)
    denominator = counts["present"] + counts["absent"] + counts["late"]
    percentage = round((counts["present"] + counts["late"]) * 100 / denominator, 2) if denominator else None
    return {"found": True, **counts, "total_records": sum(counts.values()), "attendance_percentage": percentage,
            "percentage_note": "Late is counted as attended; excused records are excluded."}


def tool_get_my_requests(db: Session, user: User, args: dict) -> dict:
    del args
    student = _student_profile(db, user)
    if not student:
        return {"found": False, "message": "No student profile is linked to this account."}
    rows = db.scalars(
        select(StudentRequest)
        .where(StudentRequest.student_profile_id == student.id)
        .order_by(StudentRequest.created_at.desc()).limit(20)
    ).all()
    return {"found": True, "requests": [{
        "id": r.id, "category": r.category, "subject": r.subject,
        "status": r.status, "created_at": r.created_at.isoformat(),
        "staff_notes": r.staff_notes,
    } for r in rows]}


def tool_search_academy_knowledge(db: Session, user: User, args: dict) -> dict:
    query = str(args.get("query", "")).strip()
    if len(query) < 2:
        return {"results": [], "message": "A more specific search question is needed."}
    results = search_knowledge(query, db, user.role, limit=6)
    return {"results": [{
        "source_id": i + 1,
        "document_id": r["document_id"],
        "chunk_id": r["chunk_id"],
        "title": r["document_title"],
        "page": r["page_number"],
        "content": r["content"],
        "similarity": r["similarity"],
    } for i, r in enumerate(results)]}


def tool_list_appointment_slots(db: Session, user: User, args: dict) -> dict:
    del user
    now = datetime.now(timezone.utc)
    days = max(1, min(int(args.get("days", 14)), 45))
    rows = db.scalars(
        select(AppointmentSlot)
        .options(joinedload(AppointmentSlot.staff))
        .where(
            AppointmentSlot.status == "available",
            AppointmentSlot.starts_at >= now,
            AppointmentSlot.starts_at <= now + timedelta(days=days),
        )
        .order_by(AppointmentSlot.starts_at)
        .limit(20)
    ).all()
    return {"available_slots": [{
        "slot_id": slot.id,
        "appointment_type": slot.appointment_type,
        "starts_at": slot.starts_at.isoformat(),
        "ends_at": slot.ends_at.isoformat(),
        "staff_member": slot.staff.full_name if slot.staff else None,
        "location": slot.location,
    } for slot in rows]}


def tool_book_appointment(db: Session, user: User, args: dict) -> dict:
    student = _student_profile(db, user)
    if not student:
        return {"booked": False, "message": "No student profile is linked to this account."}
    if args.get("confirmed") is not True:
        return {"booked": False, "message": "Booking requires explicit confirmation from the student."}
    slot_id = int(args.get("slot_id", 0))
    slot = db.scalar(
        select(AppointmentSlot)
        .where(AppointmentSlot.id == slot_id)
        .with_for_update()
    )
    if not slot or slot.status != "available" or slot.starts_at <= datetime.now(timezone.utc):
        return {"booked": False, "message": "That appointment slot is no longer available. Please check available slots again."}
    appointment = Appointment(
        slot_id=slot.id,
        student_profile_id=student.id,
        status="booked",
        reason=str(args.get("reason", "Student appointment"))[:1000],
        created_by=user.id,
    )
    slot.status = "booked"
    db.add(appointment)
    db.flush()
    return {"booked": True, "appointment_id": appointment.id,
            "appointment_type": slot.appointment_type,
            "starts_at": slot.starts_at.isoformat(), "ends_at": slot.ends_at.isoformat(),
            "location": slot.location}


def tool_cancel_appointment(db: Session, user: User, args: dict) -> dict:
    student = _student_profile(db, user)
    if not student:
        return {"cancelled": False, "message": "No student profile is linked to this account."}
    appointment_id = int(args.get("appointment_id", 0))
    appointment = db.scalar(
        select(Appointment)
        .options(joinedload(Appointment.slot))
        .where(Appointment.id == appointment_id, Appointment.student_profile_id == student.id)
        .with_for_update()
    )
    if not appointment:
        return {"cancelled": False, "message": "Appointment not found."}
    if appointment.status != "booked":
        return {"cancelled": False, "message": f"This appointment is {appointment.status} and cannot be cancelled."}
    appointment.status = "cancelled"
    appointment.slot.status = "available"
    db.flush()
    return {"cancelled": True, "appointment_id": appointment.id,
            "message": "Your appointment has been cancelled."}


def tool_create_student_request(db: Session, user: User, args: dict) -> dict:
    student = _student_profile(db, user)
    if not student:
        return {"created": False, "message": "No student profile is linked to this account."}
    category = str(args.get("category", "general")).strip().lower()[:50]
    subject = str(args.get("subject", "")).strip()[:200]
    description = str(args.get("description", "")).strip()[:5000]
    if len(subject) < 3 or len(description) < 5:
        return {"created": False, "message": "The request needs a subject and a little more detail."}
    request = StudentRequest(student_profile_id=student.id, category=category,
                             subject=subject, description=description, status="pending")
    db.add(request)
    db.flush()
    return {"created": True, "request_id": request.id, "status": request.status,
            "message": "Your request has been submitted."}


def tool_request_human(db: Session, user: User, conversation: Any, args: dict) -> dict:
    reason = str(args.get("reason", "Student requested Academy staff assistance"))[:255]
    handoff = create_handoff(conversation, db, user.id, reason)
    db.flush()
    return {"created": True, "handoff_id": handoff.id, "status": handoff.status,
            "message": "Your request for staff assistance has been sent."}


TOOL_DECLARATIONS = [
    {"name": "get_my_profile", "description": "Retrieve the authenticated student's own profile, program, academic year, and enrollment status. Never use for another person.", "parameters": {"type": "OBJECT", "properties": {}, "required": []}},
    {"name": "get_my_schedule", "description": "Retrieve the authenticated student's current class schedule.", "parameters": {"type": "OBJECT", "properties": {}, "required": []}},
    {"name": "get_my_payments", "description": "Retrieve the authenticated student's own invoices, payments, and balances.", "parameters": {"type": "OBJECT", "properties": {}, "required": []}},
    {"name": "get_my_attendance", "description": "Retrieve the authenticated student's own attendance summary.", "parameters": {"type": "OBJECT", "properties": {}, "required": []}},
    {"name": "get_my_requests", "description": "Retrieve the authenticated student's own administrative requests.", "parameters": {"type": "OBJECT", "properties": {}, "required": []}},
    {"name": "search_academy_knowledge", "description": "Search Academy documents for general Academy facts, policies, admission information, programs, fees, and FAQs. Use this for Academy knowledge, not personal student records.", "parameters": {"type": "OBJECT", "properties": {"query": {"type": "STRING", "description": "A standalone search query with enough context."}}, "required": ["query"]}},
    {"name": "list_appointment_slots", "description": "List upcoming available appointment slots. Use when the student asks about appointment availability.", "parameters": {"type": "OBJECT", "properties": {"days": {"type": "INTEGER", "description": "Number of days ahead, from 1 to 45."}}, "required": []}},
    {"name": "book_appointment", "description": "Book an available appointment slot ONLY after the student has explicitly asked to book and confirmed the specific slot. Set confirmed=true only when the student's message clearly confirms the booking.", "parameters": {"type": "OBJECT", "properties": {"slot_id": {"type": "INTEGER"}, "reason": {"type": "STRING"}, "confirmed": {"type": "BOOLEAN"}}, "required": ["slot_id", "confirmed"]}},
    {"name": "cancel_appointment", "description": "Cancel an appointment belonging to the authenticated student. Only call when the student explicitly asks to cancel.", "parameters": {"type": "OBJECT", "properties": {"appointment_id": {"type": "INTEGER"}}, "required": ["appointment_id"]}},
    {"name": "create_student_request", "description": "Submit an administrative request for the authenticated student, such as an enrollment certificate. Only call when the student clearly asks to submit/create a request.", "parameters": {"type": "OBJECT", "properties": {"category": {"type": "STRING"}, "subject": {"type": "STRING"}, "description": {"type": "STRING"}}, "required": ["category", "subject", "description"]}},
    {"name": "request_human_assistance", "description": "Create a staff handoff when the student explicitly asks for a human or when the issue requires staff intervention. Do not claim handoff succeeded unless this tool returns created=true.", "parameters": {"type": "OBJECT", "properties": {"reason": {"type": "STRING"}}, "required": ["reason"]}},
]


TOOL_HANDLERS = {
    "get_my_profile": tool_get_my_profile,
    "get_my_schedule": tool_get_my_schedule,
    "get_my_payments": tool_get_my_payments,
    "get_my_attendance": tool_get_my_attendance,
    "get_my_requests": tool_get_my_requests,
    "search_academy_knowledge": tool_search_academy_knowledge,
    "list_appointment_slots": tool_list_appointment_slots,
    "book_appointment": tool_book_appointment,
    "cancel_appointment": tool_cancel_appointment,
    "create_student_request": tool_create_student_request,
}

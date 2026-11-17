
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User, StudentProfile, StudentInvoice, StudentPayment
from app.schemas.payment import (
    InvoiceCreate,
    InvoiceResponse,
    PaymentCreate,
    PaymentResponse
)


router = APIRouter(prefix="/payments", tags=["Payments"])


def require_staff_or_admin(user: User):
    if user.role not in ["staff", "admin"]:
        raise HTTPException(
            status_code=403,
            detail="Staff or admin access required"
        )


def build_invoice_response(invoice: StudentInvoice):
    paid_amount = sum(
        (payment.amount for payment in invoice.payments),
        Decimal("0.00")
    )

    balance = invoice.total_amount - paid_amount

    return {
        "id": invoice.id,
        "student_profile_id": invoice.student_profile_id,
        "student_number": invoice.student_profile.student_number,
        "student_name": invoice.student_profile.user.full_name,
        "description": invoice.description,
        "academic_year": invoice.academic_year,
        "total_amount": invoice.total_amount,
        "currency": invoice.currency,
        "due_date": invoice.due_date,
        "status": invoice.status,
        "paid_amount": paid_amount,
        "balance": balance,
        "created_at": invoice.created_at,
        "payments": invoice.payments
    }


def get_invoice_or_404(invoice_id: int, db: Session):
    invoice = db.query(StudentInvoice).filter(
        StudentInvoice.id == invoice_id
    ).first()

    if not invoice:
        raise HTTPException(
            status_code=404,
            detail="Invoice not found"
        )

    return invoice


def check_invoice_access(invoice: StudentInvoice, user: User):
    if user.role in ["staff", "admin"]:
        return

    if invoice.student_profile.user_id != user.id:
        raise HTTPException(
            status_code=403,
            detail="You cannot access another student's invoice"
        )


@router.post(
    "/invoices",
    response_model=InvoiceResponse,
    status_code=status.HTTP_201_CREATED
)
def create_invoice(
    data: InvoiceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_staff_or_admin(current_user)

    student = db.query(StudentProfile).filter(
        StudentProfile.id == data.student_profile_id
    ).first()

    if not student:
        raise HTTPException(
            status_code=404,
            detail="Student profile not found"
        )

    invoice = StudentInvoice(
        **data.model_dump(),
        created_by=current_user.id
    )

    db.add(invoice)
    db.commit()
    db.refresh(invoice)

    return build_invoice_response(invoice)


@router.get(
    "/invoices",
    response_model=list[InvoiceResponse]
)
def list_invoices(
    student_profile_id: int | None = Query(default=None, gt=0),
    invoice_status: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_staff_or_admin(current_user)

    query = db.query(StudentInvoice)

    if student_profile_id is not None:
        query = query.filter(
            StudentInvoice.student_profile_id == student_profile_id
        )

    if invoice_status:
        allowed_statuses = [
            "unpaid",
            "partially_paid",
            "paid",
            "cancelled"
        ]

        if invoice_status not in allowed_statuses:
            raise HTTPException(
                status_code=400,
                detail="Invalid invoice status"
            )

        query = query.filter(
            StudentInvoice.status == invoice_status
        )

    invoices = query.order_by(
        StudentInvoice.created_at.desc()
    ).all()

    return [
        build_invoice_response(invoice)
        for invoice in invoices
    ]


@router.get(
    "/me",
    response_model=list[InvoiceResponse]
)
def get_my_payments(
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

    invoices = db.query(StudentInvoice).filter(
        StudentInvoice.student_profile_id == student.id
    ).order_by(
        StudentInvoice.created_at.desc()
    ).all()

    return [
        build_invoice_response(invoice)
        for invoice in invoices
    ]


@router.get(
    "/invoices/{invoice_id}",
    response_model=InvoiceResponse
)
def get_invoice(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    invoice = get_invoice_or_404(invoice_id, db)

    check_invoice_access(invoice, current_user)

    return build_invoice_response(invoice)


@router.post(
    "/invoices/{invoice_id}/payments",
    response_model=InvoiceResponse
)
def record_payment(
    invoice_id: int,
    data: PaymentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    require_staff_or_admin(current_user)

    invoice = get_invoice_or_404(invoice_id, db)

    if invoice.status == "cancelled":
        raise HTTPException(
            status_code=400,
            detail="Cannot record payment for a cancelled invoice"
        )

    paid_amount = sum(
        (payment.amount for payment in invoice.payments),
        Decimal("0.00")
    )

    balance = invoice.total_amount - paid_amount

    if balance <= 0:
        raise HTTPException(
            status_code=400,
            detail="This invoice has already been paid"
        )

    if data.amount > balance:
        raise HTTPException(
            status_code=400,
            detail=f"Payment exceeds outstanding balance of {balance}"
        )

    payment = StudentPayment(
        invoice_id=invoice.id,
        amount=data.amount,
        method=data.method,
        reference=data.reference,
        received_by=current_user.id
    )

    db.add(payment)

    new_paid_amount = paid_amount + data.amount

    if new_paid_amount == invoice.total_amount:
        invoice.status = "paid"
    else:
        invoice.status = "partially_paid"

    db.commit()
    db.refresh(invoice)

    return build_invoice_response(invoice)


@router.get(
    "/invoices/{invoice_id}/transactions",
    response_model=list[PaymentResponse]
)
def get_invoice_transactions(
    invoice_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    invoice = get_invoice_or_404(invoice_id, db)

    check_invoice_access(invoice, current_user)

    return invoice.payments
